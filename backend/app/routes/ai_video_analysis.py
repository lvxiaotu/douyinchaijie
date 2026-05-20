import time
import traceback
import os
import json
from uuid import uuid4
from typing import Any
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.task_store import (
    create_task,
    delete_task,
    get_task,
    get_analysis_archive,
    list_tasks,
    list_analysis_archives,
    save_analysis_archive,
    update_task,
)
from backend.app.ai_video_comment_service import (
    collect_comments_for_ai_task,
    merge_comment_context_into_result,
    merge_comment_state_into_payload,
    merge_comment_state_into_task_result,
)
from backend.app.short_video_analysis_store import (
    get_analysis_dataset,
    list_remake_exports,
    persist_analysis_result,
    save_remake_export,
)
from .douyin import read_env_map, write_env_values
from integrations.ai_video_analysis.relay_clients import DeepSeekChatClient
from integrations.ai_video_analysis.adapter import DEFAULT_ANALYSIS_PROMPT, AiVideoAnalysisAdapter
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from integrations.video_pipeline.script_schema import NaturalLanguageScriptRequest
from backend.app.routes.video_script import generate_script_from_natural_language
from backend.app.ai_provider_state import active_ai_provider
from backend.app.tiktok_target_store import update_target_task_by_ai_task_id
from backend.app.video_analysis_queue import (
    cancel_ai_video_job,
    delete_ai_video_job,
    enqueue_ai_video_job,
    get_ai_video_job,
    list_ai_model_runs,
    queue_stats,
    queue_snapshot,
    retry_ai_video_job,
)
from backend.app.video_analysis_worker import coordinator as ai_video_coordinator
from backend.app.video_task_limiter import video_task_concurrency_limit, video_task_semaphore

router = APIRouter(prefix="/api/tools/ai-video-analysis", tags=["ai-video-analysis"])
ROOT_DIR = Path(__file__).resolve().parents[3]


class BreakdownRequest(BaseModel):
    video: dict[str, Any] = Field(..., description="Collected video item")
    provider: str | None = Field(default=None, description="mock | gemini | openai | local")
    comment_collection: dict[str, Any] | None = Field(default=None, description="Comment collection options for AI breakdown")


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
    max_concurrent_tasks: int = Field(default=3, ge=1, le=3)
    resume_enabled: bool = Field(default=True)
    highlight_screenshots: bool = Field(default=True)
    grid_columns: int = Field(default=3, ge=1, le=6)
    grid_max_frames: int = Field(default=9, ge=1, le=24)
    grid_cell_width: int = Field(default=320, ge=120, le=960)
    grid_cell_height: int = Field(default=180, ge=90, le=720)
    ffmpeg_binary: str = Field(default="ffmpeg")
    ffprobe_binary: str = Field(default="ffprobe")
    asr_upload_mode: str = Field(default="url")
    asr_publisher: str = Field(default="local")
    asr_public_base_url: str = Field(default="")
    asr_public_dir: str = Field(default="")
    summary_provider: str = Field(default="")
    summary_model: str = Field(default="deepseek-v4-flash")
    summary_fallback_provider: str = Field(default="vision")
    analysis_prompt: str = Field(default=DEFAULT_ANALYSIS_PROMPT)


class RemakeExportPayload(BaseModel):
    run_id: str = Field(default="")
    task_id: str = Field(default="")
    title: str = Field(default="")
    genre: str = Field(default="")
    target_genre: str = Field(default="")
    markdown: str = Field(default="")
    result: dict[str, Any] = Field(default_factory=dict)
    rewritten: dict[str, Any] = Field(default_factory=dict)
    export_type: str = Field(default="remake_package")


class RemakeRewritePayload(BaseModel):
    run_id: str = Field(default="")
    task_id: str = Field(default="")
    title: str = Field(default="")
    source_genre: str = Field(default="")
    target_genre: str = Field(default="")
    markdown: str = Field(default="")
    result: dict[str, Any] = Field(default_factory=dict)


class RemakeScriptPayload(RemakeRewritePayload):
    duration_seconds: int = Field(default=60, ge=5, le=600)
    scene_count: int = Field(default=6, ge=1, le=30)
    provider: str | None = Field(default=None)


def adapter() -> AiVideoAnalysisAdapter:
    return AiVideoAnalysisAdapter()


def video_title(video: dict[str, Any]) -> str:
    return str(video.get("desc") or video.get("title") or video.get("aweme_id") or video.get("id") or "未命名视频")


def attach_model_runs(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    runs = list_ai_model_runs(task_id)
    if not runs:
        return result
    return {**result, "model_runs": runs}


def _resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _analysis_roots() -> list[Path]:
    instance = adapter()
    output_dir = instance.output_dir
    if not output_dir.is_absolute():
        output_dir = ROOT_DIR / output_dir
    return [
        output_dir.resolve(),
        (ROOT_DIR / "data" / "runtime" / "ai_video_analysis").resolve(),
    ]


def _is_allowed_analysis_path(path: Path) -> bool:
    return any(path == root or root in path.parents for root in _analysis_roots())


def _safe_existing_analysis_path(value: Any) -> Path | None:
    if not value:
        return None
    try:
        path = _resolve_repo_path(str(value))
    except Exception:
        return None
    if not path.exists() or not _is_allowed_analysis_path(path):
        return None
    return path


def _result_evidence_path(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    return str(evidence.get("evidence_path") or result.get("evidence_path") or "")


def _fallback_evidence_path(task_id: str) -> Path | None:
    for root in _analysis_roots():
        candidate = root / "evidence" / task_id / "analysis_evidence.json"
        if candidate.exists() and _is_allowed_analysis_path(candidate):
            return candidate
    return None


def _evidence_path_for_task(task_id: str) -> Path | None:
    task = get_task(task_id)
    if task:
        path = _safe_existing_analysis_path(_result_evidence_path(task.get("result")))
        if path:
            return path

    archive = get_analysis_archive(task_id)
    if archive:
        path = _safe_existing_analysis_path(_result_evidence_path(archive.get("result")))
        if path:
            return path

    dataset = get_analysis_dataset(task_id)
    if dataset:
        run = dataset.get("run") or {}
        path = _safe_existing_analysis_path(run.get("evidence_path"))
        if path:
            return path

    return _fallback_evidence_path(task_id)


def _read_evidence_for_task(task_id: str) -> tuple[dict[str, Any], Path]:
    evidence_path = _evidence_path_for_task(task_id)
    if not evidence_path:
        raise HTTPException(status_code=404, detail="Evidence package not found")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evidence package read failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(evidence, dict):
        raise HTTPException(status_code=500, detail="Evidence package is not a JSON object")
    evidence["evidence_path"] = str(evidence_path)
    return evidence, evidence_path


def _evidence_file_path(evidence: dict[str, Any], evidence_path: Path, kind: str) -> Path | None:
    metadata = evidence.get("metadata") if isinstance(evidence.get("metadata"), dict) else {}
    checkpoints = evidence.get("checkpoints") if isinstance(evidence.get("checkpoints"), dict) else {}
    if kind == "video":
        value = metadata.get("video_path")
    elif kind == "audio":
        value = metadata.get("audio_path") or checkpoints.get("audio_path")
    elif kind == "transcript":
        value = checkpoints.get("transcript_path")
    else:
        value = ""
    path = _safe_existing_analysis_path(value)
    if path:
        return path
    fallback_name = {
        "audio": "audio.wav",
        "transcript": "transcript.json",
    }.get(kind)
    if kind == "video":
        candidates = list(evidence_path.parent.glob("*.mp4"))
        return candidates[0] if candidates else None
    if fallback_name:
        fallback = evidence_path.parent / fallback_name
        if fallback.exists() and _is_allowed_analysis_path(fallback.resolve()):
            return fallback.resolve()
    return None


def _media_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".webm":
        return "video/webm"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"


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
        task = get_task(task_id) or {}
        if task:
            comment_state, patched_video = collect_comments_for_ai_task(task, progress=report)
            payload = merge_comment_state_into_payload(task.get("payload") or {}, video=patched_video, comment_state=comment_state)
            update_task(task_id, payload_json=payload)
            video = patched_video or video
            if comment_state.get("status") == "failed":
                report(30, f"评论数据获取失败，继续拆解：{comment_state.get('error') or 'unknown'}")
            elif comment_state.get("status") == "done":
                report(
                    30,
                    f"评论数据已补全：评论 {comment_state.get('comment_saved_count') or 0} 条 / 回复 {comment_state.get('reply_saved_count') or 0} 条",
                )
            else:
                report(30, "评论数据跳过，继续拆解")
        else:
            comment_state = {"status": "skipped", "reason": "task_not_found"}

        def analysis_report(progress: int, message: str) -> None:
            report(30 + int(max(0, min(100, progress)) * 0.7), message)

        job = adapter().create_job(video=video, provider=provider, job_id=task_id, progress=analysis_report)
        if not get_task(task_id):
            return
        result = attach_model_runs(task_id, job.get("result") or {})
        result = merge_comment_context_into_result(result, video=video, comment_state=comment_state)
        update_task(
            task_id,
            status="done" if job.get("status") == "done" else "running",
            progress=100 if job.get("status") == "done" else 70,
            message="拆解完成" if job.get("status") == "done" else "等待外部模型继续处理",
            provider=job.get("provider", provider or ""),
            result_json=result,
            error=None,
        )
        if job.get("status") == "done":
            persist_analysis_result(
                task_id=task_id,
                video=video,
                result=result,
                provider=job.get("provider", provider or ""),
                job_path=job.get("job_path") or "",
            )
            update_target_task_by_ai_task_id({"id": task_id, "status": "done", "result": result, "error": ""})
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
        "max_concurrent_tasks": int(env.get("AI_VIDEO_MAX_CONCURRENT_TASKS", "3") or 3),
        "resume_enabled": (env.get("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}),
        "highlight_screenshots": (env.get("AI_VIDEO_HIGHLIGHT_SCREENSHOTS", "true").lower() not in {"0", "false", "no"}),
        "grid_columns": int(env.get("AI_VIDEO_GRID_COLUMNS", "3") or 3),
        "grid_max_frames": int(env.get("AI_VIDEO_GRID_MAX_FRAMES", "9") or 9),
        "grid_cell_width": int(env.get("AI_VIDEO_GRID_CELL_WIDTH", "320") or 320),
        "grid_cell_height": int(env.get("AI_VIDEO_GRID_CELL_HEIGHT", "180") or 180),
        "ffmpeg_binary": env.get("FFMPEG_BINARY", "ffmpeg"),
        "ffprobe_binary": env.get("FFPROBE_BINARY", "ffprobe"),
        "asr_upload_mode": env.get("AI_VIDEO_ASR_UPLOAD_MODE", "url"),
        "asr_publisher": env.get("AI_VIDEO_ASR_PUBLISHER", "local"),
        "asr_public_base_url": env.get("AI_VIDEO_ASR_PUBLIC_BASE_URL", ""),
        "asr_public_dir": env.get("AI_VIDEO_ASR_PUBLIC_DIR", ""),
        "summary_provider": env.get("AI_VIDEO_SUMMARY_PROVIDER", ""),
        "summary_model": env.get("AI_VIDEO_SUMMARY_MODEL", env.get("DEEPSEEK_MODEL", "deepseek-v4-flash")),
        "summary_fallback_provider": env.get("AI_VIDEO_SUMMARY_FALLBACK_PROVIDER", "vision"),
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
                "AI_VIDEO_ASR_UPLOAD_MODE": payload.asr_upload_mode,
                "AI_VIDEO_ASR_PUBLISHER": payload.asr_publisher,
                "AI_VIDEO_ASR_PUBLIC_BASE_URL": payload.asr_public_base_url,
                "AI_VIDEO_ASR_PUBLIC_DIR": payload.asr_public_dir,
                "AI_VIDEO_SUMMARY_PROVIDER": payload.summary_provider,
                "AI_VIDEO_SUMMARY_MODEL": payload.summary_model,
                "AI_VIDEO_SUMMARY_FALLBACK_PROVIDER": payload.summary_fallback_provider,
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
def archives(
    limit: int = 100,
    include_result: bool = False,
) -> list[dict[str, Any]]:
    return list_analysis_archives(limit=limit, include_result=include_result)


@router.get("/archives/{archive_id}")
def archive_detail(archive_id: str) -> dict[str, Any]:
    archive = get_analysis_archive(archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Analysis archive not found")
    return archive


@router.get("/datasets/{run_id}")
def analysis_dataset(run_id: str) -> dict[str, Any]:
    dataset = get_analysis_dataset(run_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Analysis dataset not found")
    return dataset


@router.get("/jobs/{task_id}/evidence")
def job_evidence(task_id: str) -> dict[str, Any]:
    evidence, evidence_path = _read_evidence_for_task(task_id)
    metadata = evidence.get("metadata") if isinstance(evidence.get("metadata"), dict) else {}
    checkpoints = evidence.get("checkpoints") if isinstance(evidence.get("checkpoints"), dict) else {}
    video_file = _evidence_file_path(evidence, evidence_path, "video")
    audio_file = _evidence_file_path(evidence, evidence_path, "audio")
    transcript = evidence.get("transcript") if isinstance(evidence.get("transcript"), dict) else {}
    return {
        "status": "ok",
        "task_id": task_id,
        "evidence_path": str(evidence_path),
        "metadata": metadata,
        "transcript": transcript,
        "asr": evidence.get("asr") if isinstance(evidence.get("asr"), dict) else {},
        "analysis_segments": evidence.get("analysis_segments") if isinstance(evidence.get("analysis_segments"), list) else [],
        "keyframes": evidence.get("keyframes") if isinstance(evidence.get("keyframes"), list) else [],
        "checkpoints": checkpoints,
        "media": {
            "video_available": bool(video_file),
            "audio_available": bool(audio_file),
            "video_url": f"/api/tools/ai-video-analysis/jobs/{task_id}/evidence-file?kind=video" if video_file else "",
            "audio_url": f"/api/tools/ai-video-analysis/jobs/{task_id}/evidence-file?kind=audio" if audio_file else "",
        },
    }


@router.get("/jobs/{task_id}/evidence-file")
def job_evidence_file(task_id: str, kind: str = Query(default="video")):
    if kind not in {"video", "audio", "transcript"}:
        raise HTTPException(status_code=400, detail="Unsupported evidence file kind")
    evidence, evidence_path = _read_evidence_for_task(task_id)
    file_path = _evidence_file_path(evidence, evidence_path, kind)
    if not file_path:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(file_path, media_type=_media_type_for_path(file_path), filename=file_path.name)


@router.post("/datasets/backfill")
def backfill_analysis_datasets(limit: int = 200) -> dict[str, Any]:
    tasks = list_tasks(task_type="ai_video_analysis", limit=limit, include_result=True, include_events=False)
    persisted = []
    target_synced = []
    errors = []
    for task in tasks:
        if task.get("status") != "done" or not isinstance(task.get("result"), dict):
            continue
        try:
            payload = task.get("payload") or {}
            video = payload.get("video") or {}
            result = task.get("result") or {}
            saved = persist_analysis_result(
                task_id=task["id"],
                video=video,
                result=result,
                provider=task.get("provider") or "",
                job_path=str(result.get("checkpoint_path") or ""),
            )
            persisted.append({"task_id": task["id"], "video_id": saved.get("video", {}).get("id")})
            synced = update_target_task_by_ai_task_id(
                {
                    "id": task["id"],
                    "status": task.get("status") or "done",
                    "result": result,
                    "error": task.get("error") or "",
                }
            )
            if synced:
                target_synced.append({"task_id": task["id"], "target_task_id": synced["id"], "video_id": synced["video_id"]})
        except Exception as exc:
            errors.append({"task_id": task.get("id"), "error": f"{type(exc).__name__}: {exc}"})
    return {
        "status": "ok",
        "persisted_count": len(persisted),
        "target_synced_count": len(target_synced),
        "persisted": persisted,
        "target_synced": target_synced,
        "errors": errors,
    }


@router.get("/remake-exports")
def remake_exports(run_id: str = "", limit: int = 100) -> dict[str, Any]:
    exports = list_remake_exports(run_id=run_id, limit=limit)
    return {"status": "ok", "exports": exports, "count": len(exports)}


@router.post("/remake-exports")
def save_remake_export_route(payload: RemakeExportPayload) -> dict[str, Any]:
    export = save_remake_export(
        run_id=payload.run_id or payload.task_id,
        task_id=payload.task_id or payload.run_id,
        title=payload.title,
        genre=payload.genre,
        target_genre=payload.target_genre,
        markdown=payload.markdown,
        source=payload.result,
        rewritten=payload.rewritten,
        export_type=payload.export_type,
        status="saved",
    )
    return {"status": "ok", "export": export}


@router.get("/jobs/{task_id}/remake-exports")
def get_remake_exports(task_id: str, limit: int = 100) -> dict[str, Any]:
    exports = list_remake_exports(run_id=task_id, limit=limit)
    return {"status": "ok", "exports": exports, "count": len(exports)}


def _rewrite_prompt(payload: RemakeRewritePayload) -> str:
    return f"""
你是泛赛道短视频脚本改写专家。请只返回合法 JSON，不要 Markdown。

任务：把一个已经脱敏的短视频爆款结构，改写成目标赛道可直接拍摄的标准脚本。

源赛道：{payload.source_genre or ''}
目标赛道：{payload.target_genre or 'generic'}
标题：{payload.title}

原复刻包 Markdown：
{payload.markdown[:12000]}

原拆解 JSON：
{json.dumps(payload.result, ensure_ascii=False)[:16000]}

输出 JSON：
{{
  "target_genre": "{payload.target_genre or 'generic'}",
  "title": "新脚本标题",
  "hook": "3秒开头钩子",
  "script": "可直接口播/字幕的完整脚本，使用目标赛道语言",
  "scene_plan": [
    {{"time_range": "00:00-00:03", "visual": "画面", "audio": "口播/音效", "purpose": "留存机制"}}
  ],
  "cta": "行动号召",
  "risk_notes": ["平台风险和安全改写建议"],
  "source_structure_mapping": "说明如何继承原结构但替换变量"
}}
""".strip()


@router.post("/remake-exports/rewrite")
def rewrite_remake_export(payload: RemakeRewritePayload) -> dict[str, Any]:
    if not payload.target_genre:
        raise HTTPException(status_code=400, detail="target_genre is required")
    try:
        client = DeepSeekChatClient()
        started = time.perf_counter()
        response = client.generate_summary(prompt=_rewrite_prompt(payload))
        rewritten = json.loads(response.text)
        export = save_remake_export(
            run_id=payload.run_id or payload.task_id,
            task_id=payload.task_id or payload.run_id,
            title=payload.title,
            genre=payload.source_genre,
            target_genre=payload.target_genre,
            markdown=payload.markdown,
            source=payload.result,
            rewritten={**rewritten, "usage": response.usage, "latency_ms": int((time.perf_counter() - started) * 1000)},
            export_type="cross_genre_rewrite",
            status="rewritten",
        )
        return {"status": "ok", "rewritten": rewritten, "export": export}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail={"error_type": type(exc).__name__, "message": "DeepSeek returned non-JSON text"}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.post("/remake-exports/send-to-script")
def send_remake_to_script(payload: RemakeScriptPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    idea = payload.markdown
    if payload.result:
        idea = "\n\n".join([idea, json.dumps(payload.result, ensure_ascii=False)])
    if not idea.strip():
        raise HTTPException(status_code=400, detail="markdown or result is required")
    request = NaturalLanguageScriptRequest(
        input=idea,
        title=payload.title or "AI 视频拆解复刻脚本",
        creative_preset=payload.target_genre or payload.source_genre or "",
        duration_seconds=payload.duration_seconds,
        scene_count=payload.scene_count,
        resolution="9:16",
        generation_mode="local",
        provider=payload.provider,
    )
    task = generate_script_from_natural_language(request, background_tasks)
    export = save_remake_export(
        run_id=payload.run_id or payload.task_id,
        task_id=payload.task_id or payload.run_id,
        title=payload.title,
        genre=payload.source_genre,
        target_genre=payload.target_genre,
        markdown=payload.markdown,
        source=payload.result,
        rewritten={"script_task_id": task.get("id"), "project_id": task.get("project_id")},
        export_type="send_to_script_generator",
        status="sent",
    )
    return {"status": "ok", "task": task, "export": export}


@router.post("/jobs")
def create_breakdown_job(payload: BreakdownRequest) -> dict[str, Any]:
    try:
        instance = adapter()
        provider = payload.provider or active_ai_provider(instance.provider)
        task_id = f"video-breakdown-{payload.video.get('aweme_id') or payload.video.get('id') or uuid4().hex}-{int(time.time())}"
        task = create_task(
            task_id=task_id,
            task_type="ai_video_analysis",
            title=video_title(payload.video),
            provider=provider,
            payload={
                "video": payload.video,
                "comment_collection": payload.comment_collection or {"enabled": True},
            },
            message="已加入 AI 视频拆解队列，等待评论数据和后台 worker 执行",
        )
        enqueue_ai_video_job(task_id=task_id, video=payload.video, provider=provider)
        task["queue"] = queue_stats(task_id=task_id)
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


@router.get("/queue/status")
def queue_status(backlog_limit: int = 20, task_id: str | None = None) -> dict[str, Any]:
    snapshot = queue_snapshot(task_id=task_id, backlog_limit=backlog_limit)
    snapshot["worker_enabled"] = ai_video_coordinator.enabled()
    snapshot["worker_started"] = ai_video_coordinator.started
    snapshot["thread_count"] = len(ai_video_coordinator.threads)
    return snapshot


@router.get("/jobs/{task_id}/queue")
def job_queue_status(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task, "job": get_ai_video_job(task_id), "queue": queue_stats(task_id=task_id)}


@router.post("/jobs/{task_id}/cancel")
def cancel_job(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    job = cancel_ai_video_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="AI video queue job not found")
    if job.get("status") == "cancelled":
        update_task(task_id, status="cancelled", progress=100, message="AI 视频拆解已取消")
    else:
        update_task(task_id, status="running", message="已请求取消，当前阶段结束后停止")
    return {"status": "ok", "job": job, "queue": queue_stats(task_id=task_id)}


@router.delete("/jobs/{task_id}")
def delete_job(
    task_id: str,
    delete_task_row: bool = Query(default=True),
    allow_active: bool = Query(default=False),
) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("type") != "ai_video_analysis":
        raise HTTPException(status_code=400, detail="Only AI video analysis tasks can be deleted here")
    job = get_ai_video_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="AI video queue job not found")
    if job.get("status") in {"running", "claimed"} and not allow_active:
        cancelled = cancel_ai_video_job(task_id)
        if cancelled and cancelled.get("status") in {"running", "claimed"}:
            raise HTTPException(status_code=409, detail="Task is running. Cancel it first, then delete after it stops.")
    deleted_job = delete_ai_video_job(task_id, allow_active=allow_active)
    if not deleted_job or not deleted_job.get("deleted"):
        raise HTTPException(status_code=404, detail="AI video queue job not found")
    deleted_task = delete_task(task_id, delete_archives=True) if delete_task_row else False
    return {
        "status": "ok",
        "deleted": True,
        "deleted_task": deleted_task,
        "task_id": task_id,
        "queue": queue_stats(task_id=task_id),
    }


@router.post("/jobs/{task_id}/retry")
def retry_job(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("type") != "ai_video_analysis":
        raise HTTPException(status_code=400, detail="Only AI video analysis tasks can be retried here")
    job = retry_ai_video_job(task_id)
    if not job:
        video = (task.get("payload") or {}).get("video") or {}
        job = enqueue_ai_video_job(
            task_id=task_id,
            video=video,
            provider=task.get("provider") or active_ai_provider(adapter().provider),
        )
    update_task(task_id, status="pending", progress=0, message="已重新加入 AI 视频拆解队列", error=None)
    return {"status": "ok", "job": job, "queue": queue_stats(task_id=task_id)}


@router.post("/jobs/{task_id}/comments/retry")
def retry_job_comments(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("type") != "ai_video_analysis":
        raise HTTPException(status_code=400, detail="Only AI video analysis tasks can retry comments here")

    job = get_ai_video_job(task_id)
    if job and job.get("status") in {"running", "claimed"}:
        raise HTTPException(status_code=409, detail="AI video task is still running. Wait for the current run to finish before retrying comments.")

    def report(progress: int, message: str) -> None:
        update_task(task_id, progress=max(int(task.get("progress") or 0), progress), message=message)

    comment_state, patched_video = collect_comments_for_ai_task(task, force=True, progress=report)
    payload = merge_comment_state_into_payload(task.get("payload") or {}, video=patched_video, comment_state=comment_state)
    result = merge_comment_state_into_task_result(task.get("result") or {}, video=patched_video, comment_state=comment_state)
    updated = update_task(
        task_id,
        status=task.get("status") or "done",
        progress=task.get("progress") or 100,
        payload_json=payload,
        result_json=result,
        message=(
            f"评论数据重试完成：评论 {comment_state.get('comment_saved_count') or 0} 条 / 回复 {comment_state.get('reply_saved_count') or 0} 条"
            if comment_state.get("status") == "done"
            else f"评论数据重试失败：{comment_state.get('error') or comment_state.get('reason') or 'unknown'}"
        ),
        error=task.get("error"),
    )

    if task.get("status") == "done":
        save_analysis_archive(
            archive_id=task_id,
            task_id=task_id,
            title=task.get("title") or "AI 视频拆解",
            provider=task.get("provider") or "",
            video=patched_video,
            result=result,
        )
        persist_analysis_result(
            task_id=task_id,
            video=patched_video,
            result=result,
            provider=task.get("provider") or "",
            job_path=str(result.get("checkpoint_path") or ""),
        )
        update_target_task_by_ai_task_id({"id": task_id, "status": "done", "result": result, "error": task.get("error") or ""})

    return {"status": "ok", "task": updated, "comment_collection": comment_state}
