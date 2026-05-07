import time
import traceback
import os
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.app.task_store import (
    create_task,
    get_task,
    get_analysis_archive,
    list_analysis_archives,
    save_analysis_archive,
    update_task,
)
from .douyin import read_env_map, write_env_values
from integrations.ai_video_analysis.adapter import DEFAULT_ANALYSIS_PROMPT, AiVideoAnalysisAdapter
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from backend.app.ai_provider_state import active_ai_provider
from backend.app.video_task_limiter import video_task_concurrency_limit, video_task_semaphore

router = APIRouter(prefix="/api/tools/ai-video-analysis", tags=["ai-video-analysis"])


class BreakdownRequest(BaseModel):
    video: dict[str, Any] = Field(..., description="Collected video item")
    provider: str | None = Field(default=None, description="mock | gemini | openai | local")


class AiVideoConfigPayload(BaseModel):
    output_dir: str = Field(default="./data/runtime/ai_video_analysis")
    pipeline_mode: str = Field(default="evidence")
    transcriber: str = Field(default="auto")
    transcribe_model: str = Field(default="small")
    transcribe_language: str = Field(default="zh")
    transcribe_device: str = Field(default="cpu")
    transcribe_compute_type: str = Field(default="int8")
    segment_seconds: int = Field(default=90, ge=30, le=600)
    silent_segment_seconds: int = Field(default=6, ge=2, le=30)
    keyframe_interval_seconds: int = Field(default=30, ge=5, le=300)
    max_segments: int = Field(default=18, ge=1, le=100)
    max_concurrent_tasks: int = Field(default=1, ge=1, le=4)
    resume_enabled: bool = Field(default=True)
    highlight_screenshots: bool = Field(default=True)
    grid_columns: int = Field(default=3, ge=1, le=6)
    grid_max_frames: int = Field(default=9, ge=1, le=24)
    grid_cell_width: int = Field(default=320, ge=120, le=960)
    grid_cell_height: int = Field(default=180, ge=90, le=720)
    ffmpeg_binary: str = Field(default="ffmpeg")
    ffprobe_binary: str = Field(default="ffprobe")
    analysis_prompt: str = Field(default=DEFAULT_ANALYSIS_PROMPT)


def adapter() -> AiVideoAnalysisAdapter:
    return AiVideoAnalysisAdapter()


def video_title(video: dict[str, Any]) -> str:
    return str(video.get("desc") or video.get("title") or video.get("aweme_id") or video.get("id") or "未命名视频")


def run_breakdown_task(task_id: str, video: dict[str, Any], provider: str | None = None) -> None:
    def report(progress: int, message: str) -> None:
        update_task(task_id, status="running", progress=progress, message=message)

    semaphore = video_task_semaphore()
    limit = video_task_concurrency_limit()
    acquired = False
    try:
        report(1, f"等待 AI 视频拆解执行名额：最大并发 {limit}")
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
            message="拆解完成" if job.get("status") == "done" else "等待外部模型继续处理",
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
            message="拆解失败",
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
        "ready": not errors,
        "errors": errors,
        "provider": instance.provider,
        "output_dir": str(instance.output_dir),
        "pipeline": pipeline,
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "output_dir": env.get("AI_VIDEO_OUTPUT_DIR", "./data/runtime/ai_video_analysis"),
        "pipeline_mode": env.get("AI_VIDEO_PIPELINE_MODE", "evidence"),
        "transcriber": env.get("AI_VIDEO_TRANSCRIBER", "auto"),
        "transcribe_model": env.get("AI_VIDEO_TRANSCRIBE_MODEL", "small"),
        "transcribe_language": env.get("AI_VIDEO_TRANSCRIBE_LANGUAGE", "zh"),
        "transcribe_device": env.get("AI_VIDEO_TRANSCRIBE_DEVICE", "cpu"),
        "transcribe_compute_type": env.get("AI_VIDEO_TRANSCRIBE_COMPUTE_TYPE", "int8"),
        "segment_seconds": int(env.get("AI_VIDEO_SEGMENT_SECONDS", "90") or 90),
        "silent_segment_seconds": int(env.get("AI_VIDEO_SILENT_SEGMENT_SECONDS", "6") or 6),
        "keyframe_interval_seconds": int(env.get("AI_VIDEO_KEYFRAME_INTERVAL_SECONDS", "30") or 30),
        "max_segments": int(env.get("AI_VIDEO_MAX_SEGMENTS", "18") or 18),
        "max_concurrent_tasks": int(env.get("AI_VIDEO_MAX_CONCURRENT_TASKS", "1") or 1),
        "resume_enabled": (env.get("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}),
        "highlight_screenshots": (env.get("AI_VIDEO_HIGHLIGHT_SCREENSHOTS", "true").lower() not in {"0", "false", "no"}),
        "grid_columns": int(env.get("AI_VIDEO_GRID_COLUMNS", "3") or 3),
        "grid_max_frames": int(env.get("AI_VIDEO_GRID_MAX_FRAMES", "9") or 9),
        "grid_cell_width": int(env.get("AI_VIDEO_GRID_CELL_WIDTH", "320") or 320),
        "grid_cell_height": int(env.get("AI_VIDEO_GRID_CELL_HEIGHT", "180") or 180),
        "ffmpeg_binary": env.get("FFMPEG_BINARY", "ffmpeg"),
        "ffprobe_binary": env.get("FFPROBE_BINARY", "ffprobe"),
        "analysis_prompt": env.get("AI_VIDEO_ANALYSIS_PROMPT", DEFAULT_ANALYSIS_PROMPT),
    }


@router.post("/config")
def save_config(payload: AiVideoConfigPayload) -> dict[str, Any]:
    try:
        write_env_values(
            {
                "AI_VIDEO_OUTPUT_DIR": payload.output_dir,
                "AI_VIDEO_PIPELINE_MODE": payload.pipeline_mode,
                "AI_VIDEO_TRANSCRIBER": payload.transcriber,
                "AI_VIDEO_TRANSCRIBE_MODEL": payload.transcribe_model,
                "AI_VIDEO_TRANSCRIBE_LANGUAGE": payload.transcribe_language,
                "AI_VIDEO_TRANSCRIBE_DEVICE": payload.transcribe_device,
                "AI_VIDEO_TRANSCRIBE_COMPUTE_TYPE": payload.transcribe_compute_type,
                "AI_VIDEO_SEGMENT_SECONDS": str(payload.segment_seconds),
                "AI_VIDEO_SILENT_SEGMENT_SECONDS": str(payload.silent_segment_seconds),
                "AI_VIDEO_KEYFRAME_INTERVAL_SECONDS": str(payload.keyframe_interval_seconds),
                "AI_VIDEO_MAX_SEGMENTS": str(payload.max_segments),
                "AI_VIDEO_MAX_CONCURRENT_TASKS": str(payload.max_concurrent_tasks),
                "AI_VIDEO_RESUME_ENABLED": "true" if payload.resume_enabled else "false",
                "AI_VIDEO_HIGHLIGHT_SCREENSHOTS": "true" if payload.highlight_screenshots else "false",
                "AI_VIDEO_GRID_COLUMNS": str(payload.grid_columns),
                "AI_VIDEO_GRID_MAX_FRAMES": str(payload.grid_max_frames),
                "AI_VIDEO_GRID_CELL_WIDTH": str(payload.grid_cell_width),
                "AI_VIDEO_GRID_CELL_HEIGHT": str(payload.grid_cell_height),
                "FFMPEG_BINARY": payload.ffmpeg_binary,
                "FFPROBE_BINARY": payload.ffprobe_binary,
                "AI_VIDEO_ANALYSIS_PROMPT": payload.analysis_prompt,
            }
        )
        return {"status": "ok", "config": get_config()}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Unable to save AI video analysis config.",
            },
        ) from exc


@router.get("/archives")
def archives(limit: int = 100) -> list[dict[str, Any]]:
    return list_analysis_archives(limit=limit)


@router.get("/archives/{archive_id}")
def archive_detail(archive_id: str) -> dict[str, Any]:
    archive = get_analysis_archive(archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Analysis archive not found")
    return archive


@router.post("/jobs")
def create_breakdown_job(payload: BreakdownRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        instance = adapter()
        provider = payload.provider or active_ai_provider(instance.provider)
        task_id = f"video-breakdown-{payload.video.get('aweme_id') or payload.video.get('id') or uuid4().hex}-{int(time.time())}"
        task = create_task(
            task_id=task_id,
            task_type="ai_video_analysis",
            title=video_title(payload.video),
            provider=provider,
            payload={"video": payload.video},
            message="已创建，等待后台执行",
        )
        background_tasks.add_task(run_breakdown_task, task_id, payload.video, payload.provider)
        return task
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Check AI video analysis provider config.",
            },
        ) from exc
