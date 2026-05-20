from __future__ import annotations

import os
import threading
import time
import traceback
from typing import Any

from backend.app.ai_provider_state import active_ai_provider
from backend.app.ai_video_comment_service import (
    collect_comments_for_ai_task,
    merge_comment_context_into_result,
    merge_comment_state_into_payload,
)
from backend.app.task_store import get_task, save_analysis_archive, update_task
from backend.app.tiktok_target_store import update_target_task_by_ai_task_id
from backend.app.short_video_analysis_store import persist_analysis_result
from backend.app.video_analysis_queue import (
    cancel_ai_video_job,
    claim_next_ai_video_job,
    complete_ai_video_job,
    fail_ai_video_job,
    heartbeat_ai_video_job,
    init_ai_video_queue_db,
    list_ai_model_runs,
    queue_stats,
    requeue_stale_ai_video_jobs,
    update_ai_video_job,
    worker_host_id,
)
from backend.app.video_task_limiter import video_task_concurrency_limit
from integrations.ai_video_analysis.adapter import AiVideoAnalysisAdapter


class VideoAnalysisCoordinator:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.started = False
        self.lock = threading.Lock()

    def enabled(self) -> bool:
        return os.getenv("AI_VIDEO_WORKER_ENABLED", "true").lower() not in {"0", "false", "no"}

    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            init_ai_video_queue_db()
            recovered = requeue_stale_ai_video_jobs()
            if recovered:
                print(f"[ai-video-worker] recovered stale jobs: {recovered}", flush=True)
            if not self.enabled():
                print("[ai-video-worker] disabled by AI_VIDEO_WORKER_ENABLED", flush=True)
                self.started = True
                return
            self.stop_event.clear()
            limit = video_task_concurrency_limit()
            self.threads = []
            for index in range(limit):
                worker_id = f"{worker_host_id()}-ai-video-{index + 1}"
                thread = threading.Thread(
                    target=self.worker_loop,
                    args=(worker_id,),
                    name=f"ai-video-worker-{index + 1}",
                    daemon=True,
                )
                thread.start()
                self.threads.append(thread)
            self.started = True
            print(f"[ai-video-worker] started {len(self.threads)} worker(s)", flush=True)

    def stop(self) -> None:
        with self.lock:
            self.stop_event.set()
            threads = list(self.threads)
        for thread in threads:
            thread.join(timeout=5)
        with self.lock:
            self.threads = []
            self.started = False
        print("[ai-video-worker] stopped", flush=True)

    def worker_loop(self, worker_id: str) -> None:
        poll_interval = float(os.getenv("AI_VIDEO_WORKER_POLL_INTERVAL_SECONDS", "2") or 2)
        while not self.stop_event.is_set():
            try:
                job = claim_next_ai_video_job(worker_id)
                if not job:
                    self.stop_event.wait(max(0.5, poll_interval))
                    continue
                self.run_claimed_job(worker_id, job)
            except Exception as exc:
                print(f"[ai-video-worker] loop error {worker_id}: {type(exc).__name__}: {exc}", flush=True)
                traceback.print_exc()
                self.stop_event.wait(max(1.0, poll_interval))

    def run_claimed_job(self, worker_id: str, job: dict[str, Any]) -> None:
        task_id = str(job["task_id"])
        task = get_task(task_id)
        if not task:
            fail_ai_video_job(
                task_id,
                error_code="TASK_NOT_FOUND",
                error_message="Task row disappeared before execution.",
                retryable=False,
            )
            return

        payload = task.get("payload") or {}
        video = payload.get("video") or {}
        provider = job.get("provider") or task.get("provider") or active_ai_provider("mock")
        update_ai_video_job(task_id, status="running", stage="running", progress=max(1, int(job.get("progress") or 1)), worker_id=worker_id)

        heartbeat = JobHeartbeat(task_id=task_id, worker_id=worker_id, stop_event=self.stop_event)
        heartbeat.start()
        try:
            if job.get("cancel_requested"):
                cancel_ai_video_job(task_id)
                update_task(task_id, status="cancelled", progress=100, message="AI 视频拆解已取消")
                return

            def report(progress: int, message: str) -> None:
                current = update_ai_video_job(
                    task_id,
                    status="running",
                    stage=message[:80] if message else "running",
                    progress=progress,
                    worker_id=worker_id,
                )
                if current and current.get("cancel_requested"):
                    raise RuntimeError("AI_VIDEO_TASK_CANCELLED")
                update_task(task_id, status="running", progress=progress, message=message)

            report(5, "后台 worker 已认领 AI 视频拆解任务")
            comment_state, patched_video = collect_comments_for_ai_task(task, progress=report)
            if patched_video:
                payload = merge_comment_state_into_payload(payload, video=patched_video, comment_state=comment_state)
                task["payload"] = payload
                video = patched_video
                update_task(task_id, payload_json=payload)
                if comment_state.get("status") == "failed":
                    report(30, f"评论数据获取失败，继续拆解：{comment_state.get('error') or 'unknown'}")
                elif comment_state.get("status") == "done":
                    report(
                        30,
                        f"评论数据已补全：评论 {comment_state.get('comment_saved_count') or 0} 条 / 回复 {comment_state.get('reply_saved_count') or 0} 条",
                    )
                else:
                    report(30, "评论数据跳过，继续拆解")
            adapter = AiVideoAnalysisAdapter()

            def analysis_report(progress: int, message: str) -> None:
                report(30 + int(max(0, min(100, progress)) * 0.7), message)

            result_job = adapter.create_job(video=video, provider=provider, job_id=task_id, progress=analysis_report)
            if not get_task(task_id):
                fail_ai_video_job(
                    task_id,
                    error_code="TASK_NOT_FOUND",
                    error_message="Task row disappeared after execution.",
                    retryable=False,
                )
                return
            result = result_job.get("result") or {}
            model_runs = list_ai_model_runs(task_id)
            if model_runs:
                result = {**result, "model_runs": model_runs}
            result = merge_comment_context_into_result(result, video=video, comment_state=comment_state)
            update_task(
                task_id,
                status="done" if result_job.get("status") == "done" else "running",
                progress=100 if result_job.get("status") == "done" else 70,
                message="拆解完成" if result_job.get("status") == "done" else "等待外部模型继续处理",
                provider=result_job.get("provider", provider or ""),
                payload_json=payload,
                result_json=result,
                error=None,
            )
            if result_job.get("status") == "done":
                self.save_archive_if_possible(task_id, task, provider=result_job.get("provider", provider or ""), result=result)
                self.persist_analysis_dataset_if_possible(
                    task_id,
                    task,
                    provider=result_job.get("provider", provider or ""),
                    result=result,
                    job_path=result_job.get("job_path") or "",
                )
                self.sync_target_state_if_possible(task_id, task, result=result)
                complete_ai_video_job(task_id)
            else:
                update_ai_video_job(task_id, status="running", stage="model_pending", progress=70, worker_id=worker_id)
        except Exception as exc:
            if str(exc) == "AI_VIDEO_TASK_CANCELLED":
                cancel_ai_video_job(task_id)
                update_task(task_id, status="cancelled", progress=100, message="AI 视频拆解已取消", error=None)
                return
            traceback.print_exc()
            failed = fail_ai_video_job(
                task_id,
                error_code=type(exc).__name__,
                error_message=str(exc),
                retryable=True,
            )
            if failed and failed.get("status") == "retry_waiting":
                update_task(
                    task_id,
                    status="pending",
                    progress=min(99, int(failed.get("progress") or 0)),
                    message=f"拆解失败，等待重试：{type(exc).__name__}",
                    error=f"{type(exc).__name__}: {exc}",
                )
            else:
                update_task(
                    task_id,
                    status="failed",
                    progress=100,
                    message="拆解失败",
                    error=f"{type(exc).__name__}: {exc}",
                )
        finally:
            heartbeat.stop()

    def save_archive_if_possible(self, task_id: str, task: dict[str, Any], *, provider: str, result: dict[str, Any]) -> None:
        try:
            video = (task.get("payload") or {}).get("video") or {}
            save_analysis_archive(
                archive_id=task_id,
                task_id=task_id,
                title=task.get("title") or "AI 视频拆解",
                provider=provider,
                video=video,
                result=result,
            )
        except Exception as exc:
            print(f"[ai-video-worker] archive save failed {task_id}: {type(exc).__name__}: {exc}", flush=True)

    def persist_analysis_dataset_if_possible(
        self,
        task_id: str,
        task: dict[str, Any],
        *,
        provider: str,
        result: dict[str, Any],
        job_path: str = "",
    ) -> None:
        try:
            video = (task.get("payload") or {}).get("video") or {}
            persist_analysis_result(
                task_id=task_id,
                video=video,
                result=result,
                provider=provider,
                job_path=job_path,
            )
        except Exception as exc:
            print(f"[ai-video-worker] analysis dataset save failed {task_id}: {type(exc).__name__}: {exc}", flush=True)

    def sync_target_state_if_possible(self, task_id: str, task: dict[str, Any], *, result: dict[str, Any]) -> None:
        try:
            payload = task.get("payload") or {}
            if "douyin_target" not in payload and "douyin_target_context" not in (payload.get("video") or {}):
                return
            ai_task = {
                "id": task_id,
                "status": "done",
                "result": result,
                "error": "",
            }
            updated = update_target_task_by_ai_task_id(ai_task)
            if updated:
                print(f"[ai-video-worker] synced target task {updated['id']} from {task_id}", flush=True)
        except Exception as exc:
            print(f"[ai-video-worker] target sync failed {task_id}: {type(exc).__name__}: {exc}", flush=True)

    def status(self) -> dict[str, Any]:
        data = queue_stats()
        data["worker_enabled"] = self.enabled()
        data["worker_started"] = self.started
        data["thread_count"] = len(self.threads)
        return data


class JobHeartbeat:
    def __init__(self, *, task_id: str, worker_id: str, stop_event: threading.Event) -> None:
        self.task_id = task_id
        self.worker_id = worker_id
        self.parent_stop_event = stop_event
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.loop, name=f"ai-video-heartbeat-{self.task_id}", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def loop(self) -> None:
        interval = float(os.getenv("AI_VIDEO_WORKER_HEARTBEAT_SECONDS", "30") or 30)
        while not self.stop_event.is_set() and not self.parent_stop_event.is_set():
            heartbeat_ai_video_job(self.task_id, self.worker_id)
            self.stop_event.wait(max(5.0, interval))


coordinator = VideoAnalysisCoordinator()
