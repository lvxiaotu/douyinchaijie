from __future__ import annotations

import os
import threading
import traceback
from typing import Any

from backend.app.ai_provider_state import active_ai_provider
from backend.app.ai_video_analysis_runner import AiVideoAnalysisRunner
from backend.app.task_store import get_task, update_task
from backend.app.video_analysis_queue import (
    AiVideoTaskCancelled,
    cancel_ai_video_job,
    claim_next_ai_video_job,
    complete_ai_video_job,
    fail_ai_video_job,
    heartbeat_ai_video_job,
    init_ai_video_queue_db,
    queue_stats,
    requeue_stale_ai_video_jobs,
    update_ai_video_job,
    worker_host_id,
)
from backend.app.video_task_limiter import video_task_concurrency_limit


class VideoAnalysisCoordinator:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.started = False
        self.desired_thread_count = 0
        self.lock = threading.Lock()

    def enabled(self) -> bool:
        return os.getenv("AI_VIDEO_WORKER_ENABLED", "true").lower() not in {"0", "false", "no"}

    def _compact_threads_locked(self, *, exclude: threading.Thread | None = None) -> None:
        self.threads = [thread for thread in self.threads if thread is not exclude and thread.is_alive()]

    def _spawn_worker_thread(self, index: int) -> threading.Thread:
        worker_id = f"{worker_host_id()}-ai-video-{index}"
        thread = threading.Thread(
            target=self.worker_loop,
            args=(worker_id, index),
            name=f"ai-video-worker-{index}",
            daemon=True,
        )
        thread.start()
        self.threads.append(thread)
        return thread

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
            self.desired_thread_count = limit
            self.threads = []
            for index in range(1, limit + 1):
                self._spawn_worker_thread(index)
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

    def reconcile(self, target_thread_count: int | None = None) -> dict[str, Any]:
        target = target_thread_count if target_thread_count is not None else video_task_concurrency_limit()
        try:
            desired = max(1, min(3, int(target or 3)))
        except ValueError:
            desired = video_task_concurrency_limit()

        spawned = 0
        with self.lock:
            self._compact_threads_locked()
            self.desired_thread_count = desired
            current = len(self.threads)
            if self.started and self.enabled() and current < desired:
                for index in range(current + 1, desired + 1):
                    self._spawn_worker_thread(index)
                    spawned += 1
                current = len(self.threads)
        return {
            "enabled": self.enabled(),
            "started": self.started,
            "target_thread_count": desired,
            "thread_count": current,
            "thread_count_delta": current - desired,
            "spawned": spawned,
        }

    def worker_loop(self, worker_id: str, worker_index: int) -> None:
        poll_interval = float(os.getenv("AI_VIDEO_WORKER_POLL_INTERVAL_SECONDS", "2") or 2)
        current_thread = threading.current_thread()
        try:
            while not self.stop_event.is_set():
                try:
                    with self.lock:
                        target = self.desired_thread_count or video_task_concurrency_limit()
                    if worker_index > target:
                        print(f"[ai-video-worker] retiring {worker_id} above target {target}", flush=True)
                        break
                    job = claim_next_ai_video_job(worker_id)
                    if not job:
                        self.stop_event.wait(max(0.5, poll_interval))
                        continue
                    self.run_claimed_job(worker_id, job)
                except Exception as exc:
                    print(f"[ai-video-worker] loop error {worker_id}: {type(exc).__name__}: {exc}", flush=True)
                    traceback.print_exc()
                    self.stop_event.wait(max(1.0, poll_interval))
        finally:
            with self.lock:
                self._compact_threads_locked(exclude=current_thread)

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
            result_job = AiVideoAnalysisRunner().run(
                task_id=task_id,
                video=video,
                provider=provider,
                progress=report,
            )
            if result_job.status == "task_missing":
                fail_ai_video_job(
                    task_id,
                    error_code="TASK_NOT_FOUND",
                    error_message="Task row disappeared after execution.",
                    retryable=False,
                )
                return
            if result_job.status == "done":
                complete_ai_video_job(task_id)
            else:
                update_ai_video_job(task_id, status="running", stage="model_pending", progress=70, worker_id=worker_id)
        except Exception as exc:
            if isinstance(exc, AiVideoTaskCancelled) or str(exc) == "AI_VIDEO_TASK_CANCELLED":
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

    def status(self) -> dict[str, Any]:
        data = queue_stats()
        with self.lock:
            self._compact_threads_locked()
            thread_count = len(self.threads)
            target = self.desired_thread_count or video_task_concurrency_limit()
        data["worker_enabled"] = self.enabled()
        data["worker_started"] = self.started
        data["thread_count"] = thread_count
        data["worker_target_threads"] = target
        data["thread_count_delta"] = thread_count - target
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
