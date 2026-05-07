from __future__ import annotations

import os
import threading

_task_semaphore: threading.BoundedSemaphore | None = None
_task_semaphore_limit = 0


def video_task_concurrency_limit() -> int:
    try:
        return max(1, min(4, int(os.getenv("AI_VIDEO_MAX_CONCURRENT_TASKS", "1") or 1)))
    except ValueError:
        return 1


def video_task_semaphore() -> threading.BoundedSemaphore:
    global _task_semaphore, _task_semaphore_limit
    limit = video_task_concurrency_limit()
    if _task_semaphore is None or _task_semaphore_limit != limit:
        _task_semaphore = threading.BoundedSemaphore(limit)
        _task_semaphore_limit = limit
    return _task_semaphore
