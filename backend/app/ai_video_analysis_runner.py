from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from backend.app.ai_video_comment_service import (
    collect_comments_for_ai_task,
    merge_comment_context_into_result,
    merge_comment_state_into_payload,
)
from backend.app.short_video_analysis_store import persist_analysis_result
from backend.app.task_store import get_task, save_analysis_archive, update_task
from backend.app.tiktok_target_store import update_target_task_by_ai_task_id
from backend.app.video_analysis_queue import list_ai_model_runs
from integrations.ai_video_analysis.adapter import AiVideoAnalysisAdapter


ProgressCallback = Callable[[int, str], None]


@dataclass
class AiVideoAnalysisRunResult:
    status: str
    provider: str
    result: dict[str, Any]
    payload: dict[str, Any]
    job_path: str = ""


def attach_model_runs(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    runs = list_ai_model_runs(task_id)
    if not runs:
        return result
    return {**result, "model_runs": runs}


class AiVideoAnalysisRunner:
    """Single execution path for AI video breakdown jobs.

    Queue workers and legacy background entrypoints should both call this class
    so comment collection, model execution, result persistence, and target sync
    stay in one place.
    """

    def __init__(self, adapter_factory: Callable[[], AiVideoAnalysisAdapter] | None = None) -> None:
        self.adapter_factory = adapter_factory or AiVideoAnalysisAdapter

    def run(
        self,
        *,
        task_id: str,
        video: dict[str, Any],
        provider: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> AiVideoAnalysisRunResult:
        task = get_task(task_id) or {}
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        if not video and isinstance(payload.get("video"), dict):
            video = payload["video"]

        if task:
            comment_state, patched_video = collect_comments_for_ai_task(task, progress=progress)
            payload = merge_comment_state_into_payload(payload, video=patched_video, comment_state=comment_state)
            task["payload"] = payload
            video = patched_video or video
            update_task(task_id, payload_json=payload)
            self._report_comment_state(comment_state, progress)
        else:
            comment_state = {"status": "skipped", "reason": "task_not_found"}

        def analysis_report(model_progress: int, message: str) -> None:
            self._progress(progress, 30 + int(max(0, min(100, model_progress)) * 0.7), message)

        result_job = self.adapter_factory().create_job(
            video=video,
            provider=provider,
            job_id=task_id,
            progress=analysis_report,
        )
        latest_task = get_task(task_id)
        if not latest_task:
            return AiVideoAnalysisRunResult(
                status="task_missing",
                provider=str(result_job.get("provider", provider or "")),
                result={},
                payload=payload,
                job_path=str(result_job.get("job_path") or ""),
            )

        latest_payload = latest_task.get("payload") if isinstance(latest_task.get("payload"), dict) else {}
        latest_comment_state = (
            latest_payload.get("comment_collection_state")
            if isinstance(latest_payload.get("comment_collection_state"), dict)
            else {}
        )
        if comment_state.get("status") == "failed" and latest_comment_state.get("status") == "done":
            comment_state = latest_comment_state
            payload = latest_payload
            latest_video = latest_payload.get("video") if isinstance(latest_payload.get("video"), dict) else {}
            video = latest_video or video

        result = attach_model_runs(task_id, result_job.get("result") or {})
        result = merge_comment_context_into_result(result, video=video, comment_state=comment_state)
        result_status = "done" if result_job.get("status") == "done" else "running"
        result_provider = str(result_job.get("provider", provider or ""))
        update_task(
            task_id,
            status=result_status,
            progress=100 if result_status == "done" else 70,
            message="拆解完成" if result_status == "done" else "等待外部模型继续处理",
            provider=result_provider,
            payload_json=payload,
            result_json=result,
            error=None,
        )

        if result_status == "done":
            self.save_archive_if_possible(task_id, latest_task, video=video, provider=result_provider, result=result)
            self.persist_analysis_dataset_if_possible(
                task_id,
                video=video,
                provider=result_provider,
                result=result,
                job_path=str(result_job.get("job_path") or ""),
            )
            self.sync_target_state_if_possible(task_id, payload=payload, video=video, result=result)

        return AiVideoAnalysisRunResult(
            status=result_status,
            provider=result_provider,
            result=result,
            payload=payload,
            job_path=str(result_job.get("job_path") or ""),
        )

    def save_archive_if_possible(
        self,
        task_id: str,
        task: dict[str, Any],
        *,
        video: dict[str, Any],
        provider: str,
        result: dict[str, Any],
    ) -> None:
        try:
            save_analysis_archive(
                archive_id=task_id,
                task_id=task_id,
                title=task.get("title") or "AI 视频拆解",
                provider=provider,
                video=video,
                result=result,
            )
        except Exception as exc:
            print(f"[ai-video-runner] archive save failed {task_id}: {type(exc).__name__}: {exc}", flush=True)

    def persist_analysis_dataset_if_possible(
        self,
        task_id: str,
        *,
        video: dict[str, Any],
        provider: str,
        result: dict[str, Any],
        job_path: str = "",
    ) -> None:
        try:
            persist_analysis_result(
                task_id=task_id,
                video=video,
                result=result,
                provider=provider,
                job_path=job_path,
            )
        except Exception as exc:
            print(f"[ai-video-runner] analysis dataset save failed {task_id}: {type(exc).__name__}: {exc}", flush=True)

    def sync_target_state_if_possible(
        self,
        task_id: str,
        *,
        payload: dict[str, Any],
        video: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        try:
            if "douyin_target" not in payload and "douyin_target_context" not in video:
                return
            updated = update_target_task_by_ai_task_id(
                {
                    "id": task_id,
                    "status": "done",
                    "result": result,
                    "error": "",
                }
            )
            if updated:
                print(f"[ai-video-runner] synced target task {updated['id']} from {task_id}", flush=True)
        except Exception as exc:
            print(f"[ai-video-runner] target sync failed {task_id}: {type(exc).__name__}: {exc}", flush=True)

    def _report_comment_state(self, comment_state: dict[str, Any], progress: ProgressCallback | None) -> None:
        if comment_state.get("status") == "failed":
            self._progress(progress, 30, f"评论数据获取失败，继续拆解：{comment_state.get('error') or 'unknown'}")
            return
        if comment_state.get("status") == "done":
            self._progress(
                progress,
                30,
                f"评论数据已补全：评论 {comment_state.get('comment_saved_count') or 0} 条 / 回复 {comment_state.get('reply_saved_count') or 0} 条",
            )
            return
        self._progress(progress, 30, "评论数据跳过，继续拆解")

    def _progress(self, progress: ProgressCallback | None, value: int, message: str) -> None:
        if progress:
            progress(value, message)
