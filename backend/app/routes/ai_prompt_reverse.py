import time
import traceback
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.app.task_store import (
    create_task,
    get_task,
    get_prompt_reverse_archive,
    list_prompt_reverse_archives,
    save_prompt_reverse_archive,
    update_task,
)
from integrations.ai_prompt_reverse.adapter import DEFAULT_REVERSE_PROMPT, AiPromptReverseAdapter
from backend.app.ai_provider_state import active_ai_provider
from backend.app.video_task_limiter import video_task_concurrency_limit, video_task_semaphore
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline

from .douyin import read_env_map, write_env_values

router = APIRouter(prefix="/api/tools/ai-prompt-reverse", tags=["ai-prompt-reverse"])


class PromptReverseRequest(BaseModel):
    video: dict[str, Any] = Field(..., description="Collected video item")
    provider: str | None = Field(default=None, description="mock | gemini")


class PromptReverseConfigPayload(BaseModel):
    output_dir: str = Field(default="./data/runtime/ai_prompt_reverse")
    pipeline_mode: str = Field(default="evidence")
    max_segments: int = Field(default=18, ge=1, le=100)
    reverse_prompt: str = Field(default=DEFAULT_REVERSE_PROMPT)


def adapter() -> AiPromptReverseAdapter:
    return AiPromptReverseAdapter()


def video_title(video: dict[str, Any]) -> str:
    return str(video.get("desc") or video.get("title") or video.get("aweme_id") or video.get("id") or "未命名视频")


def run_prompt_reverse_task(task_id: str, video: dict[str, Any], provider: str | None = None) -> None:
    def report(progress: int, message: str) -> None:
        update_task(task_id, status="running", progress=progress, message=message)

    semaphore = video_task_semaphore()
    limit = video_task_concurrency_limit()
    acquired = False
    try:
        report(1, f"等待 AI 视频任务执行名额：最大并发 {limit}")
        semaphore.acquire()
        acquired = True
        report(5, "后台任务已启动")
        job = adapter().create_job(video=video, provider=provider, job_id=task_id, progress=report)
        if not get_task(task_id):
            return
        update_task(
            task_id,
            status="done" if job.get("status") == "done" else "running",
            progress=100 if job.get("status") == "done" else 70,
            message="提示词反推完成" if job.get("status") == "done" else "等待外部模型继续处理",
            provider=job.get("provider", provider or ""),
            result_json=job.get("result") or {},
            error=None,
        )
    except Exception as exc:
        traceback.print_exc()
        update_task(
            task_id,
            status="failed",
            progress=100,
            message="提示词反推失败",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if acquired:
            semaphore.release()


@router.get("/status")
def status() -> dict[str, Any]:
    instance = adapter()
    errors = instance.validate_config()
    pipeline = VideoEvidencePipeline(output_dir=instance.output_dir).dependency_status()
    return {
        "id": instance.manifest.id,
        "name": instance.manifest.name,
        "ready": not errors and pipeline.get("ffmpeg_ready") and pipeline.get("ffprobe_ready") and pipeline.get("transcriber_ready"),
        "errors": errors,
        "provider": instance.provider,
        "output_dir": str(instance.output_dir),
        "pipeline": pipeline,
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "output_dir": env.get("AI_PROMPT_REVERSE_OUTPUT_DIR", "./data/runtime/ai_prompt_reverse"),
        "pipeline_mode": env.get("AI_PROMPT_REVERSE_PIPELINE_MODE", "evidence"),
        "max_segments": int(env.get("AI_PROMPT_REVERSE_MAX_SEGMENTS", env.get("AI_VIDEO_MAX_SEGMENTS", "18")) or 18),
        "reverse_prompt": env.get("AI_PROMPT_REVERSE_PROMPT", DEFAULT_REVERSE_PROMPT),
        "gemini_access_mode": env.get("GEMINI_ACCESS_MODE", "official"),
        "gemini_relay_base_url": env.get("GEMINI_RELAY_BASE_URL", "https://jeniya.top"),
        "has_gemini_relay_api_key": bool(env.get("GEMINI_RELAY_API_KEY", "")),
    }


@router.post("/config")
def save_config(payload: PromptReverseConfigPayload) -> dict[str, Any]:
    try:
        write_env_values(
            {
                "AI_PROMPT_REVERSE_OUTPUT_DIR": payload.output_dir,
                "AI_PROMPT_REVERSE_PIPELINE_MODE": payload.pipeline_mode,
                "AI_PROMPT_REVERSE_MAX_SEGMENTS": str(payload.max_segments),
                "AI_PROMPT_REVERSE_PROMPT": payload.reverse_prompt,
            }
        )
        return {"status": "ok", "config": get_config()}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Unable to save AI prompt reverse config.",
            },
        ) from exc


@router.post("/jobs")
def create_prompt_reverse_job(payload: PromptReverseRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        instance = adapter()
        provider = payload.provider or active_ai_provider(instance.provider)
        task_id = f"prompt-reverse-{payload.video.get('aweme_id') or payload.video.get('id') or uuid4().hex}-{int(time.time())}"
        task = create_task(
            task_id=task_id,
            task_type="ai_prompt_reverse",
            title=video_title(payload.video),
            provider=provider,
            payload={"video": payload.video},
            message="已创建，等待后台执行",
        )
        background_tasks.add_task(run_prompt_reverse_task, task_id, payload.video, payload.provider)
        return task
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Check AI prompt reverse provider config.",
            },
        ) from exc


@router.post("/jobs/{task_id}/retry")
def retry_prompt_reverse_job(task_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("type") != "ai_prompt_reverse":
        raise HTTPException(status_code=400, detail="Only AI prompt reverse tasks can be retried here")
    if task.get("status") not in {"failed", "error"}:
        raise HTTPException(status_code=409, detail="Only failed AI prompt reverse tasks can be retried")

    video = (task.get("payload") or {}).get("video") or {}
    if not video:
        raise HTTPException(status_code=400, detail="Retry requires the original video payload")

    retried = update_task(
        task_id,
        status="pending",
        progress=0,
        message="已重新加入提示词反推队列",
        result_json=None,
        error=None,
    )
    background_tasks.add_task(run_prompt_reverse_task, task_id, video, task.get("provider") or None)
    return {"status": "ok", "task": retried}


@router.get("/archives")
def archives(
    limit: int = 100,
    include_result: bool = False,
) -> list[dict[str, Any]]:
    return list_prompt_reverse_archives(limit=limit, include_result=include_result)


@router.get("/archives/{archive_id}")
def archive_detail(archive_id: str) -> dict[str, Any]:
    archive = get_prompt_reverse_archive(archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Prompt reverse archive not found")
    return archive
