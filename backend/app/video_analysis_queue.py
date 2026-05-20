from __future__ import annotations

import json
import os
import socket
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.task_store import connect, load_json
from backend.app.video_task_limiter import video_task_concurrency_limit

ACTIVE_STATUSES = {"claimed", "running"}
CLAIMABLE_STATUSES = {"queued", "retry_waiting", "stale_requeued"}
TERMINAL_STATUSES = {"done", "failed_final", "cancelled"}
AI_MODEL_RUN_COLUMNS = {
    "meta_json": "meta_json TEXT NOT NULL DEFAULT '{}'",
}


class AiVideoTaskCancelled(RuntimeError):
    def __init__(self, task_id: str):
        super().__init__("AI_VIDEO_TASK_CANCELLED")
        self.task_id = task_id


@contextmanager
def queue_connection():
    with connect() as connection:
        yield connection


def now_ts() -> int:
    return int(time.time())


def worker_host_id() -> str:
    return socket.gethostname() or "local"


def ensure_columns(connection: Any, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, definition in columns.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_ai_video_queue_db() -> None:
    with queue_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_video_jobs (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 5,
                provider TEXT NOT NULL DEFAULT '',
                video_fingerprint TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                duration REAL NOT NULL DEFAULT 0,
                progress INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                locked_by TEXT NOT NULL DEFAULT '',
                locked_at INTEGER,
                heartbeat_at INTEGER,
                retry_after INTEGER,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                stage_state_json TEXT NOT NULL DEFAULT '{}',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_video_jobs_queue
            ON ai_video_jobs(status, retry_after, priority, created_at)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_video_jobs_lock
            ON ai_video_jobs(status, locked_at, heartbeat_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_video_artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                type TEXT NOT NULL,
                uri TEXT NOT NULL,
                checksum TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_video_artifacts_task
            ON ai_video_artifacts(task_id, type)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_video_chunks (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                transcript TEXT NOT NULL DEFAULT '',
                frame_count INTEGER NOT NULL DEFAULT 0,
                grid_uri TEXT NOT NULL DEFAULT '',
                vision_result_uri TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT '',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_video_chunks_task
            ON ai_video_chunks(task_id, chunk_index)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_model_runs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                purpose TEXT NOT NULL,
                prompt_version TEXT NOT NULL DEFAULT '',
                input_uri TEXT NOT NULL DEFAULT '',
                output_uri TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                latency_ms INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_estimate REAL NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT '',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        ensure_columns(connection, "ai_model_runs", AI_MODEL_RUN_COLUMNS)
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_model_runs_task
            ON ai_model_runs(task_id, purpose, status)
            """
        )


def row_to_ai_video_job(row: Any) -> dict[str, Any]:
    job = dict(row)
    job["cancel_requested"] = bool(job.get("cancel_requested"))
    job["stage_state"] = load_json(job.pop("stage_state_json", "{}"), {})
    job["metrics"] = load_json(job.pop("metrics_json", "{}"), {})
    return job


def row_to_ai_video_queue_item(row: Any, *, position: int | None = None) -> dict[str, Any]:
    item = row_to_ai_video_job(row)
    item["title"] = str(item.pop("task_title", "") or item.get("task_id") or "")
    item["task_message"] = str(item.pop("task_message", "") or "")
    item["task_status"] = str(item.pop("task_status", "") or "")
    item["task_progress"] = int(item.pop("task_progress", 0) or 0)
    item["task_updated_at"] = item.pop("task_updated_at", None)
    item["task_provider"] = str(item.pop("task_provider", "") or "")
    if position is not None:
        item["position"] = position
    return item


def row_to_ai_video_artifact(row: Any) -> dict[str, Any]:
    artifact = dict(row)
    artifact["meta"] = load_json(artifact.pop("meta_json", "{}"), {})
    return artifact


def row_to_ai_video_chunk(row: Any) -> dict[str, Any]:
    chunk = dict(row)
    chunk["meta"] = load_json(chunk.pop("meta_json", "{}"), {})
    return chunk


def _local_file_info(uri: str) -> tuple[int, str]:
    if not uri or "://" in uri:
        return 0, ""
    path = Path(uri)
    if not path.exists() or not path.is_file():
        return 0, ""
    size = path.stat().st_size
    hash_limit = int(os.getenv("AI_VIDEO_ARTIFACT_HASH_MAX_BYTES", str(20 * 1024 * 1024)) or 0)
    if hash_limit <= 0 or size > hash_limit:
        return int(size), ""
    digest = sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return int(size), digest.hexdigest()


def record_ai_video_artifact(
    *,
    task_id: str,
    type: str,
    uri: str,
    checksum: str | None = None,
    size_bytes: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_ai_video_queue_db()
    if not task_id or not type or not uri:
        return {}
    detected_size, detected_checksum = _local_file_info(uri)
    size = int(size_bytes if size_bytes is not None else detected_size)
    digest = checksum if checksum is not None else detected_checksum
    now = now_ts()
    with queue_connection() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM ai_video_artifacts
            WHERE task_id = ? AND type = ? AND uri = ?
            LIMIT 1
            """,
            (task_id, type, uri),
        ).fetchone()
        artifact_id = existing["id"] if existing else f"artifact-{uuid4().hex}"
        existing_meta = load_json(existing["meta_json"], {}) if existing else {}
        merged_meta = {**existing_meta, **(meta or {})}
        if existing:
            connection.execute(
                """
                UPDATE ai_video_artifacts
                SET checksum = ?, size_bytes = ?, meta_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (digest or "", size, json.dumps(merged_meta, ensure_ascii=False), now, artifact_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO ai_video_artifacts (
                    id, task_id, type, uri, checksum, size_bytes, meta_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, task_id, type, uri, digest or "", size, json.dumps(merged_meta, ensure_ascii=False), now, now),
            )
        row = connection.execute("SELECT * FROM ai_video_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return row_to_ai_video_artifact(row) if row else {"id": artifact_id}


def list_ai_video_artifacts(task_id: str) -> list[dict[str, Any]]:
    init_ai_video_queue_db()
    with queue_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM ai_video_artifacts
            WHERE task_id = ?
            ORDER BY created_at ASC, type ASC
            """,
            (task_id,),
        ).fetchall()
    return [row_to_ai_video_artifact(row) for row in rows]


def upsert_ai_video_chunk(
    *,
    task_id: str,
    chunk_index: int,
    start_time: float = 0.0,
    end_time: float = 0.0,
    status: str = "pending",
    transcript: str = "",
    frame_count: int = 0,
    grid_uri: str = "",
    vision_result_uri: str = "",
    attempts: int | None = None,
    increment_attempts: bool = False,
    error_message: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_ai_video_queue_db()
    if not task_id or int(chunk_index or 0) <= 0:
        return {}
    now = now_ts()
    index = int(chunk_index)
    with queue_connection() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM ai_video_chunks
            WHERE task_id = ? AND chunk_index = ?
            LIMIT 1
            """,
            (task_id, index),
        ).fetchone()
        chunk_id = existing["id"] if existing else f"chunk-{uuid4().hex}"
        existing_meta = load_json(existing["meta_json"], {}) if existing else {}
        merged_meta = {**existing_meta, **(meta or {})}
        next_attempts = int(attempts if attempts is not None else (existing["attempts"] if existing else 0))
        if increment_attempts:
            next_attempts += 1
        if existing:
            connection.execute(
                """
                UPDATE ai_video_chunks
                SET start_time = ?,
                    end_time = ?,
                    status = ?,
                    transcript = ?,
                    frame_count = ?,
                    grid_uri = ?,
                    vision_result_uri = ?,
                    attempts = ?,
                    error_message = ?,
                    meta_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    float(start_time or existing["start_time"] or 0),
                    float(end_time or existing["end_time"] or 0),
                    status or existing["status"],
                    transcript if transcript != "" else existing["transcript"],
                    int(frame_count if frame_count is not None else existing["frame_count"]),
                    grid_uri if grid_uri != "" else existing["grid_uri"],
                    vision_result_uri if vision_result_uri != "" else existing["vision_result_uri"],
                    next_attempts,
                    error_message[:2000],
                    json.dumps(merged_meta, ensure_ascii=False),
                    now,
                    chunk_id,
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO ai_video_chunks (
                    id, task_id, chunk_index, start_time, end_time, status, transcript,
                    frame_count, grid_uri, vision_result_uri, attempts, error_message,
                    meta_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    task_id,
                    index,
                    float(start_time or 0),
                    float(end_time or 0),
                    status,
                    transcript,
                    int(frame_count or 0),
                    grid_uri,
                    vision_result_uri,
                    next_attempts,
                    error_message[:2000],
                    json.dumps(merged_meta, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        row = connection.execute("SELECT * FROM ai_video_chunks WHERE id = ?", (chunk_id,)).fetchone()
    return row_to_ai_video_chunk(row) if row else {"id": chunk_id}


def list_ai_video_chunks(task_id: str) -> list[dict[str, Any]]:
    init_ai_video_queue_db()
    with queue_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM ai_video_chunks
            WHERE task_id = ?
            ORDER BY chunk_index ASC
            """,
            (task_id,),
        ).fetchall()
    return [row_to_ai_video_chunk(row) for row in rows]


def video_source_url(video: dict[str, Any]) -> str:
    return str(
        video.get("source_video_url")
        or video.get("download_url")
        or video.get("video_url")
        or video.get("play_url")
        or ""
    )


def video_fingerprint(video: dict[str, Any]) -> str:
    stable = {
        "aweme_id": video.get("aweme_id") or video.get("id") or "",
        "source_url": video_source_url(video),
        "desc": video.get("desc") or video.get("title") or "",
    }
    return sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def enqueue_ai_video_job(
    *,
    task_id: str,
    video: dict[str, Any],
    provider: str,
    priority: int = 5,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    init_ai_video_queue_db()
    now = now_ts()
    attempts_limit = max_attempts if max_attempts is not None else int(os.getenv("AI_VIDEO_MAX_ATTEMPTS", "3") or 3)
    with queue_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO ai_video_jobs (
                task_id, status, stage, priority, provider, video_fingerprint,
                source_url, duration, progress, attempts, max_attempts,
                locked_by, locked_at, heartbeat_at, retry_after, cancel_requested,
                error_code, error_message, stage_state_json, metrics_json,
                created_at, updated_at
            )
            VALUES (
                ?,
                COALESCE((SELECT status FROM ai_video_jobs WHERE task_id = ?), 'queued'),
                'queued',
                ?, ?, ?, ?, ?,
                0,
                COALESCE((SELECT attempts FROM ai_video_jobs WHERE task_id = ?), 0),
                ?,
                '', NULL, NULL, NULL, 0, '', '', '{}', '{}',
                COALESCE((SELECT created_at FROM ai_video_jobs WHERE task_id = ?), ?),
                ?
            )
            """,
            (
                task_id,
                task_id,
                int(priority),
                provider,
                video_fingerprint(video),
                video_source_url(video),
                float(video.get("duration") or video.get("duration_seconds") or 0),
                task_id,
                max(1, attempts_limit),
                task_id,
                now,
                now,
            ),
        )
    return get_ai_video_job(task_id) or {}


def get_ai_video_job(task_id: str) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    with queue_connection() as connection:
        row = connection.execute("SELECT * FROM ai_video_jobs WHERE task_id = ?", (task_id,)).fetchone()
    return row_to_ai_video_job(row) if row else None


def is_ai_video_cancel_requested(task_id: str) -> bool:
    if not task_id:
        return False
    job = get_ai_video_job(task_id)
    return bool(job and (job.get("cancel_requested") or job.get("status") == "cancelled"))


def raise_if_ai_video_cancelled(task_id: str) -> None:
    if is_ai_video_cancel_requested(task_id):
        raise AiVideoTaskCancelled(task_id)


def active_job_count(connection: Any | None = None) -> int:
    if connection is not None:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM ai_video_jobs WHERE status IN ('claimed', 'running')"
        ).fetchone()
        return int(row["count"] if row else 0)
    init_ai_video_queue_db()
    with queue_connection() as owned_connection:
        row = owned_connection.execute(
            "SELECT COUNT(*) AS count FROM ai_video_jobs WHERE status IN ('claimed', 'running')"
        ).fetchone()
    return int(row["count"] if row else 0)


def claim_next_ai_video_job(worker_id: str) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    now = now_ts()
    limit = video_task_concurrency_limit()
    with queue_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        active = active_job_count(connection)
        if active >= limit:
            connection.rollback()
            return None

        row = connection.execute(
            """
            SELECT *
            FROM ai_video_jobs
            WHERE status IN ('queued', 'retry_waiting', 'stale_requeued')
              AND cancel_requested = 0
              AND attempts < max_attempts
              AND (retry_after IS NULL OR retry_after <= ?)
            ORDER BY priority ASC, created_at ASC
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if not row:
            connection.rollback()
            return None

        task_id = row["task_id"]
        cursor = connection.execute(
            """
            UPDATE ai_video_jobs
            SET status = 'claimed',
                stage = 'claimed',
                attempts = attempts + 1,
                locked_by = ?,
                locked_at = ?,
                heartbeat_at = ?,
                retry_after = NULL,
                error_code = '',
                error_message = '',
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('queued', 'retry_waiting', 'stale_requeued')
              AND cancel_requested = 0
            """,
            (worker_id, now, now, now, task_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return None
        connection.commit()
    return get_ai_video_job(task_id)


def update_ai_video_job(
    task_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    worker_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    stage_state: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    updates: dict[str, Any] = {"updated_at": now_ts()}
    if status is not None:
        updates["status"] = status
    if stage is not None:
        updates["stage"] = stage
    if progress is not None:
        updates["progress"] = max(0, min(100, int(progress)))
    if worker_id is not None:
        updates["locked_by"] = worker_id
        updates["heartbeat_at"] = now_ts()
    if error_code is not None:
        updates["error_code"] = error_code
    if error_message is not None:
        updates["error_message"] = error_message
    if stage_state is not None:
        updates["stage_state_json"] = json.dumps(stage_state, ensure_ascii=False)
    if metrics is not None:
        updates["metrics_json"] = json.dumps(metrics, ensure_ascii=False)

    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [task_id]
    with queue_connection() as connection:
        cursor = connection.execute(f"UPDATE ai_video_jobs SET {assignments} WHERE task_id = ?", values)
    return get_ai_video_job(task_id) if cursor.rowcount else None


def heartbeat_ai_video_job(task_id: str, worker_id: str) -> None:
    init_ai_video_queue_db()
    now = now_ts()
    with queue_connection() as connection:
        connection.execute(
            """
            UPDATE ai_video_jobs
            SET heartbeat_at = ?, locked_by = ?, updated_at = ?
            WHERE task_id = ? AND status IN ('claimed', 'running')
            """,
            (now, worker_id, now, task_id),
        )


def complete_ai_video_job(task_id: str, *, stage: str = "done") -> dict[str, Any] | None:
    now = now_ts()
    with queue_connection() as connection:
        connection.execute(
            """
            UPDATE ai_video_jobs
            SET status = 'done',
                stage = ?,
                progress = 100,
                locked_by = '',
                locked_at = NULL,
                heartbeat_at = NULL,
                retry_after = NULL,
                error_code = '',
                error_message = '',
                updated_at = ?
            WHERE task_id = ?
            """,
            (stage, now, task_id),
        )
    return get_ai_video_job(task_id)


def fail_ai_video_job(
    task_id: str,
    *,
    error_code: str,
    error_message: str,
    retryable: bool = True,
) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    current = get_ai_video_job(task_id)
    if not current:
        return None
    now = now_ts()
    attempts = int(current.get("attempts") or 0)
    max_attempts = int(current.get("max_attempts") or 1)
    should_retry = retryable and attempts < max_attempts and not current.get("cancel_requested")
    base = int(os.getenv("AI_VIDEO_RETRY_BASE_SECONDS", "60") or 60)
    max_delay = int(os.getenv("AI_VIDEO_RETRY_MAX_SECONDS", "1800") or 1800)
    delay = min(max(base, 1) * (2 ** max(0, attempts - 1)), max_delay)
    status = "retry_waiting" if should_retry else "failed_final"
    retry_after = now + delay if should_retry else None
    with queue_connection() as connection:
        connection.execute(
            """
            UPDATE ai_video_jobs
            SET status = ?,
                stage = 'failed',
                locked_by = '',
                locked_at = NULL,
                heartbeat_at = NULL,
                retry_after = ?,
                error_code = ?,
                error_message = ?,
                updated_at = ?
            WHERE task_id = ?
            """,
            (status, retry_after, error_code, error_message[:2000], now, task_id),
        )
    return get_ai_video_job(task_id)


def cancel_ai_video_job(task_id: str) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    now = now_ts()
    current = get_ai_video_job(task_id)
    if not current:
        return None
    if current["status"] in TERMINAL_STATUSES:
        return current
    if current["status"] in ACTIVE_STATUSES:
        with queue_connection() as connection:
            connection.execute(
                """
                UPDATE ai_video_jobs
                SET cancel_requested = 1,
                    error_code = 'CANCEL_REQUESTED',
                    error_message = 'Cancellation requested; running task will stop at the next safe checkpoint.',
                    updated_at = ?
                WHERE task_id = ?
                """,
                (now, task_id),
            )
    else:
        with queue_connection() as connection:
            connection.execute(
                """
                UPDATE ai_video_jobs
                SET status = 'cancelled',
                    stage = 'cancelled',
                    cancel_requested = 1,
                    locked_by = '',
                    locked_at = NULL,
                    heartbeat_at = NULL,
                    retry_after = NULL,
                    error_code = 'CANCELLED',
                    error_message = 'Cancelled before execution.',
                    updated_at = ?
                WHERE task_id = ?
                """,
                (now, task_id),
            )
    return get_ai_video_job(task_id)


def delete_ai_video_job(task_id: str, *, allow_active: bool = False) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    current = get_ai_video_job(task_id)
    if not current:
        return None
    if current["status"] in ACTIVE_STATUSES and not allow_active:
        return {**current, "deleted": False, "delete_blocked": True}
    with queue_connection() as connection:
        connection.execute("DELETE FROM ai_video_artifacts WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM ai_video_chunks WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM ai_model_runs WHERE task_id = ?", (task_id,))
        cursor = connection.execute("DELETE FROM ai_video_jobs WHERE task_id = ?", (task_id,))
    return {**current, "deleted": cursor.rowcount > 0, "delete_blocked": False}


def retry_ai_video_job(task_id: str) -> dict[str, Any] | None:
    init_ai_video_queue_db()
    now = now_ts()
    current = get_ai_video_job(task_id)
    if not current:
        return None
    with queue_connection() as connection:
        connection.execute(
            """
            UPDATE ai_video_jobs
            SET status = 'queued',
                stage = 'queued',
                progress = 0,
                attempts = 0,
                locked_by = '',
                locked_at = NULL,
                heartbeat_at = NULL,
                retry_after = NULL,
                cancel_requested = 0,
                error_code = '',
                error_message = '',
                updated_at = ?
            WHERE task_id = ?
            """,
            (now, task_id),
        )
    return get_ai_video_job(task_id)


def requeue_stale_ai_video_jobs(stale_seconds: int | None = None) -> int:
    init_ai_video_queue_db()
    stale_after = stale_seconds if stale_seconds is not None else int(os.getenv("AI_VIDEO_WORKER_STALE_SECONDS", "900") or 900)
    cutoff = now_ts() - max(60, stale_after)
    now = now_ts()
    with queue_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE ai_video_jobs
            SET status = 'stale_requeued',
                stage = 'queued',
                locked_by = '',
                locked_at = NULL,
                heartbeat_at = NULL,
                retry_after = NULL,
                error_code = 'STALE_LOCK',
                error_message = 'Recovered stale worker lock.',
                updated_at = ?
            WHERE status IN ('claimed', 'running')
              AND (heartbeat_at IS NULL OR heartbeat_at < ?)
              AND cancel_requested = 0
            """,
            (now, cutoff),
        )
    return int(cursor.rowcount or 0)


def queue_position(task_id: str) -> int | None:
    init_ai_video_queue_db()
    current = get_ai_video_job(task_id)
    if not current or current["status"] not in CLAIMABLE_STATUSES:
        return None
    with queue_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM ai_video_jobs
            WHERE status IN ('queued', 'retry_waiting', 'stale_requeued')
              AND cancel_requested = 0
              AND (
                priority < ?
                OR (priority = ? AND created_at <= ?)
              )
            """,
            (current["priority"], current["priority"], current["created_at"]),
        ).fetchone()
    return int(row["count"] if row else 0)


def queue_stats(*, task_id: str | None = None) -> dict[str, Any]:
    return queue_snapshot(task_id=task_id)


def queue_snapshot(*, task_id: str | None = None, backlog_limit: int = 20) -> dict[str, Any]:
    init_ai_video_queue_db()
    backlog_limit = max(1, min(int(backlog_limit or 20), 100))
    with queue_connection() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM ai_video_jobs GROUP BY status"
        ).fetchall()
        workers = connection.execute(
            """
            SELECT
                j.task_id,
                j.status,
                j.stage,
                j.progress,
                j.locked_by,
                j.locked_at,
                j.heartbeat_at,
                j.priority,
                j.attempts,
                j.max_attempts,
                j.created_at,
                j.updated_at,
                j.error_code,
                j.error_message,
                t.title AS task_title,
                t.message AS task_message,
                t.status AS task_status,
                t.progress AS task_progress,
                t.provider AS task_provider,
                t.updated_at AS task_updated_at
            FROM ai_video_jobs j
            LEFT JOIN tasks t ON t.id = j.task_id
            WHERE j.status IN ('claimed', 'running')
            ORDER BY j.locked_at ASC
            """
        ).fetchall()
        backlog = connection.execute(
            """
            SELECT
                j.task_id,
                j.status,
                j.stage,
                j.priority,
                j.progress,
                j.attempts,
                j.max_attempts,
                j.retry_after,
                j.locked_by,
                j.locked_at,
                j.heartbeat_at,
                j.created_at,
                j.updated_at,
                j.error_code,
                j.error_message,
                t.title AS task_title,
                t.message AS task_message,
                t.status AS task_status,
                t.progress AS task_progress,
                t.provider AS task_provider,
                t.updated_at AS task_updated_at
            FROM ai_video_jobs j
            LEFT JOIN tasks t ON t.id = j.task_id
            WHERE j.status IN ('queued', 'retry_waiting', 'stale_requeued')
              AND j.cancel_requested = 0
            ORDER BY j.priority ASC, j.created_at ASC
            LIMIT ?
            """,
            (backlog_limit,),
        ).fetchall()
        failed_recent = connection.execute(
            """
            SELECT
                j.task_id,
                j.status,
                j.stage,
                j.priority,
                j.progress,
                j.attempts,
                j.max_attempts,
                j.retry_after,
                j.locked_by,
                j.locked_at,
                j.heartbeat_at,
                j.created_at,
                j.updated_at,
                j.error_code,
                j.error_message,
                t.title AS task_title,
                t.message AS task_message,
                t.status AS task_status,
                t.progress AS task_progress,
                t.provider AS task_provider,
                t.updated_at AS task_updated_at
            FROM ai_video_jobs j
            LEFT JOIN tasks t ON t.id = j.task_id
            WHERE j.status = 'failed_final'
            ORDER BY j.updated_at DESC
            LIMIT 20
            """
        ).fetchall()
        done_recent = connection.execute(
            """
            SELECT
                j.task_id,
                j.status,
                j.stage,
                j.priority,
                j.progress,
                j.attempts,
                j.max_attempts,
                j.retry_after,
                j.locked_by,
                j.locked_at,
                j.heartbeat_at,
                j.created_at,
                j.updated_at,
                j.error_code,
                j.error_message,
                t.title AS task_title,
                t.message AS task_message,
                t.status AS task_status,
                t.progress AS task_progress,
                t.provider AS task_provider,
                t.updated_at AS task_updated_at
            FROM ai_video_jobs j
            LEFT JOIN tasks t ON t.id = j.task_id
            WHERE j.status = 'done'
            ORDER BY j.updated_at DESC
            LIMIT 20
            """
        ).fetchall()
        oldest = connection.execute(
            """
            SELECT MIN(created_at) AS oldest
            FROM ai_video_jobs
            WHERE status IN ('queued', 'retry_waiting', 'stale_requeued')
            """
        ).fetchone()
    counts = {row["status"]: int(row["count"]) for row in rows}
    queued = sum(counts.get(status, 0) for status in CLAIMABLE_STATUSES)
    active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
    result = {
        "max_concurrent": video_task_concurrency_limit(),
        "active": active,
        "queued": queued,
        "retry_waiting": counts.get("retry_waiting", 0),
        "done": counts.get("done", 0),
        "failed": counts.get("failed_final", 0),
        "cancelled": counts.get("cancelled", 0),
        "counts": counts,
        "oldest_queued_at": oldest["oldest"] if oldest else None,
        "workers": [row_to_ai_video_queue_item(row) for row in workers],
        "backlog": [row_to_ai_video_queue_item(row, position=index + 1) for index, row in enumerate(backlog)],
        "failed_recent": [row_to_ai_video_queue_item(row) for row in failed_recent],
        "done_recent": [row_to_ai_video_queue_item(row) for row in done_recent],
    }
    if task_id:
        result["task_id"] = task_id
        result["position"] = queue_position(task_id)
        result["job"] = get_ai_video_job(task_id)
        result["artifacts"] = list_ai_video_artifacts(task_id)
        result["chunks"] = list_ai_video_chunks(task_id)
    return result


def record_ai_model_run(
    *,
    task_id: str,
    provider: str,
    model: str,
    purpose: str,
    chunk_id: str = "",
    prompt_version: str = "",
    input_uri: str = "",
    output_uri: str = "",
    status: str = "done",
    latency_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_estimate: float = 0.0,
    error_message: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_ai_video_queue_db()
    now = now_ts()
    run_id = f"model-run-{uuid4().hex}"
    with queue_connection() as connection:
        connection.execute(
            """
            INSERT INTO ai_model_runs (
                id, task_id, chunk_id, provider, model, purpose, prompt_version,
                input_uri, output_uri, status, latency_ms, input_tokens,
                output_tokens, cost_estimate, error_message, meta_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task_id,
                chunk_id,
                provider,
                model,
                purpose,
                prompt_version,
                input_uri,
                output_uri,
                status,
                int(latency_ms or 0),
                int(input_tokens or 0),
                int(output_tokens or 0),
                float(cost_estimate or 0.0),
                error_message[:2000],
                json.dumps(meta or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        row = connection.execute("SELECT * FROM ai_model_runs WHERE id = ?", (run_id,)).fetchone()
    return row_to_ai_model_run(row) if row else {"id": run_id}


def row_to_ai_model_run(row: Any) -> dict[str, Any]:
    run = dict(row)
    run["meta"] = load_json(run.pop("meta_json", "{}"), {})
    return run


def list_ai_model_runs(task_id: str) -> list[dict[str, Any]]:
    init_ai_video_queue_db()
    with queue_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM ai_model_runs
            WHERE task_id = ?
            ORDER BY created_at ASC
            """,
            (task_id,),
        ).fetchall()
    return [row_to_ai_model_run(row) for row in rows]
