from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "runtime" / "tasks.sqlite3"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def load_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_archives (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                title TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                video_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_reverse_archives (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                title TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                video_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS production_reverse_archives (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                title TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                video_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                detail_json TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id, created_at)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jianying_assets (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'local',
                path TEXT NOT NULL DEFAULT '',
                resource_id TEXT NOT NULL DEFAULT '',
                effect_id TEXT NOT NULL DEFAULT '',
                duration REAL,
                width INTEGER,
                height INTEGER,
                hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'unknown',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jianying_assets_type ON jianying_assets(type)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jianying_assets_path ON jianying_assets(path)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jianying_drafts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                draft_path TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'created',
                status TEXT NOT NULL DEFAULT 'created',
                asset_report_json TEXT NOT NULL DEFAULT '{}',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jianying_drafts_status ON jianying_drafts(status)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jianying_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                template_path TEXT NOT NULL DEFAULT '',
                text_slots_json TEXT NOT NULL DEFAULT '[]',
                media_slots_json TEXT NOT NULL DEFAULT '[]',
                audio_slots_json TEXT NOT NULL DEFAULT '[]',
                required_assets_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'unknown',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jianying_templates_status ON jianying_templates(status)")


def row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["payload"] = load_json(task.pop("payload_json"), {})
    result_json = task.pop("result_json")
    task["result"] = load_json(result_json, None) if result_json else None
    task["events"] = list_task_events(task["id"], limit=200)
    return task


def compact_text(value: Any, limit: int = 180) -> str:
    text = str(value or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def compact_task_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    video = payload.get("video")
    if isinstance(video, dict):
        return {
            "video": {
                "id": video.get("id") or video.get("aweme_id") or "",
                "aweme_id": video.get("aweme_id") or video.get("id") or "",
                "desc": compact_text(video.get("desc") or video.get("title") or "", 120),
                "title": compact_text(video.get("title") or video.get("desc") or "", 120),
                "cover_url": video.get("cover_url") or "",
            }
        }
    compact: dict[str, Any] = {}
    for key in ("idea", "title", "text", "workflow_id", "workflow_key"):
        if key in payload:
            compact[key] = compact_text(payload.get(key), 160)
    return compact


def row_to_task_summary(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["payload"] = compact_task_payload(load_json(task.pop("payload_json"), {}))
    task.pop("result_json", None)
    task["result"] = None
    task["events"] = []
    return task


def row_to_task_event(row: sqlite3.Row) -> dict[str, Any]:
    event = dict(row)
    detail_json = event.pop("detail_json")
    event["detail"] = json.loads(detail_json) if detail_json else None
    return event


def append_task_event(
    task_id: str,
    *,
    status: str = "",
    progress: int = 0,
    message: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    init_db()
    now = int(time.time())
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO task_events (task_id, status, progress, message, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                status,
                int(progress or 0),
                message,
                json.dumps(detail, ensure_ascii=False) if detail else None,
                now,
            ),
        )
        row = connection.execute("SELECT * FROM task_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
    if message:
        print(f"[task-progress] {task_id} {progress}% {status or '-'} {message}", flush=True)
    return row_to_task_event(row) if row else None


def list_task_events(task_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM task_events
            WHERE task_id = ?
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
    return [row_to_task_event(row) for row in rows]


def create_task(
    *,
    task_id: str,
    task_type: str,
    title: str,
    provider: str,
    payload: dict[str, Any],
    message: str = "等待执行",
) -> dict[str, Any]:
    init_db()
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tasks (
                id, type, title, status, progress, message, provider,
                payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                title,
                "pending",
                0,
                message,
                provider,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ),
        )
    append_task_event(task_id, status="pending", progress=0, message=message)
    return get_task(task_id)


def update_task(task_id: str, **updates: Any) -> dict[str, Any] | None:
    init_db()
    allowed = {"status", "progress", "message", "provider", "result_json", "error"}
    normalized: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if key == "result_json" and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        normalized[key] = value
    normalized["updated_at"] = int(time.time())

    assignments = ", ".join(f"{key} = ?" for key in normalized)
    values = list(normalized.values()) + [task_id]
    with connect() as connection:
        cursor = connection.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", values)
    if cursor.rowcount == 0:
        return None
    append_task_event(
        task_id,
        status=str(normalized.get("status") or ""),
        progress=int(normalized.get("progress") or 0),
        message=str(normalized.get("message") or normalized.get("error") or ""),
        detail={"error": normalized.get("error")} if normalized.get("error") else None,
    )
    return get_task(task_id)


def list_tasks(
    task_type: str | None = None,
    limit: int = 100,
    *,
    include_result: bool = True,
    include_events: bool = True,
) -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        if task_type:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE type = ? ORDER BY created_at DESC LIMIT ?",
                (task_type, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    if include_result or include_events:
        tasks = [row_to_task(row) for row in rows]
        if not include_events:
            for task in tasks:
                task["events"] = []
        if not include_result:
            for task in tasks:
                task["result"] = None
        return tasks
    return [row_to_task_summary(row) for row in rows]


def get_task(task_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row_to_task(row) if row else None


def delete_task(task_id: str, delete_archives: bool = True) -> bool:
    init_db()
    with connect() as connection:
        if delete_archives:
            connection.execute("DELETE FROM analysis_archives WHERE task_id = ? OR id = ?", (task_id, task_id))
            connection.execute("DELETE FROM prompt_reverse_archives WHERE task_id = ? OR id = ?", (task_id, task_id))
            connection.execute("DELETE FROM production_reverse_archives WHERE task_id = ? OR id = ?", (task_id, task_id))
        connection.execute("DELETE FROM task_events WHERE task_id = ?", (task_id,))
        cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0


def save_analysis_archive(
    *,
    archive_id: str,
    task_id: str,
    title: str,
    provider: str,
    video: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO analysis_archives (
                id, task_id, title, provider, video_json, result_json, created_at, updated_at
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                COALESCE((SELECT created_at FROM analysis_archives WHERE id = ?), ?),
                ?
            )
            """,
            (
                archive_id,
                task_id,
                title,
                provider,
                json.dumps(video, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                archive_id,
                now,
                now,
            ),
        )
    return get_analysis_archive(archive_id)


def row_to_archive(row: sqlite3.Row) -> dict[str, Any]:
    archive = dict(row)
    archive["video"] = load_json(archive.pop("video_json"), {})
    archive["result"] = load_json(archive.pop("result_json"), {})
    return archive


def archive_result_summary(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    nested = result.get("result") if isinstance(result.get("result"), dict) else result
    summary = nested.get("summary") if isinstance(nested, dict) else ""
    if isinstance(summary, str) and summary.strip().startswith("{"):
        parsed = load_json(summary, {})
        if isinstance(parsed, dict):
            nested = parsed
            summary = nested.get("summary") or nested.get("摘要") or nested.get("视频摘要") or ""
    compact = {"summary": compact_text(summary, 220)}
    for key in (
        "master_prompt",
        "production_overview",
        "content_identity",
        "core_hook",
        "market_positioning",
        "viral_scores",
    ):
        value = nested.get(key) if isinstance(nested, dict) else None
        if value is not None:
            compact[key] = value
    return compact


def row_to_archive_summary(row: sqlite3.Row) -> dict[str, Any]:
    archive = dict(row)
    archive["video"] = compact_task_payload({"video": load_json(archive.pop("video_json"), {})}).get("video", {})
    archive["result"] = archive_result_summary(load_json(archive.pop("result_json"), {}))
    return archive


def list_analysis_archives(limit: int = 100, *, include_result: bool = True) -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM analysis_archives ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_archive(row) if include_result else row_to_archive_summary(row) for row in rows]


def get_analysis_archive(archive_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM analysis_archives WHERE id = ?", (archive_id,)).fetchone()
    return row_to_archive(row) if row else None


def save_prompt_reverse_archive(
    *,
    archive_id: str,
    task_id: str,
    title: str,
    provider: str,
    video: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO prompt_reverse_archives (
                id, task_id, title, provider, video_json, result_json, created_at, updated_at
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                COALESCE((SELECT created_at FROM prompt_reverse_archives WHERE id = ?), ?),
                ?
            )
            """,
            (
                archive_id,
                task_id,
                title,
                provider,
                json.dumps(video, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                archive_id,
                now,
                now,
            ),
        )
    return get_prompt_reverse_archive(archive_id)


def list_prompt_reverse_archives(limit: int = 100, *, include_result: bool = True) -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM prompt_reverse_archives ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_archive(row) if include_result else row_to_archive_summary(row) for row in rows]


def get_prompt_reverse_archive(archive_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM prompt_reverse_archives WHERE id = ?", (archive_id,)).fetchone()
    return row_to_archive(row) if row else None


def save_production_reverse_archive(
    *,
    archive_id: str,
    task_id: str,
    title: str,
    provider: str,
    video: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO production_reverse_archives (
                id, task_id, title, provider, video_json, result_json, created_at, updated_at
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                COALESCE((SELECT created_at FROM production_reverse_archives WHERE id = ?), ?),
                ?
            )
            """,
            (
                archive_id,
                task_id,
                title,
                provider,
                json.dumps(video, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                archive_id,
                now,
                now,
            ),
        )
    return get_production_reverse_archive(archive_id)


def list_production_reverse_archives(limit: int = 100, *, include_result: bool = True) -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM production_reverse_archives ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_archive(row) if include_result else row_to_archive_summary(row) for row in rows]


def get_production_reverse_archive(archive_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM production_reverse_archives WHERE id = ?", (archive_id,)).fetchone()
    return row_to_archive(row) if row else None


def row_to_jianying_asset(row: sqlite3.Row) -> dict[str, Any]:
    asset = dict(row)
    asset["meta"] = json.loads(asset.pop("meta_json") or "{}")
    return asset


def upsert_jianying_assets(assets: list[dict[str, Any]], *, source: str = "local") -> list[dict[str, Any]]:
    init_db()
    now = int(time.time())
    saved_ids: list[str] = []
    with connect() as connection:
        for asset in assets:
            asset_id = str(asset.get("id") or "")
            if not asset_id:
                continue
            saved_ids.append(asset_id)
            connection.execute(
                """
                INSERT INTO jianying_assets (
                    id, type, name, source, path, resource_id, effect_id,
                    duration, width, height, hash, status, meta_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type,
                    name = excluded.name,
                    source = excluded.source,
                    path = excluded.path,
                    resource_id = excluded.resource_id,
                    effect_id = excluded.effect_id,
                    duration = excluded.duration,
                    width = excluded.width,
                    height = excluded.height,
                    hash = excluded.hash,
                    status = excluded.status,
                    meta_json = excluded.meta_json,
                    updated_at = excluded.updated_at
                """
                ,
                (
                    asset_id,
                    str(asset.get("type") or ""),
                    str(asset.get("name") or ""),
                    str(asset.get("source") or source),
                    str(asset.get("path") or ""),
                    str(asset.get("resource_id") or ""),
                    str(asset.get("effect_id") or ""),
                    asset.get("duration"),
                    asset.get("width"),
                    asset.get("height"),
                    str(asset.get("hash") or ""),
                    str(asset.get("status") or "unknown"),
                    json.dumps(asset.get("meta") or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        if not saved_ids:
            return []
        placeholders = ",".join("?" for _ in saved_ids)
        rows = connection.execute(
            f"SELECT * FROM jianying_assets WHERE id IN ({placeholders}) ORDER BY updated_at DESC",
            saved_ids,
        ).fetchall()
    return [row_to_jianying_asset(row) for row in rows]


def list_jianying_assets(
    *,
    asset_type: str | None = None,
    source: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    init_db()
    conditions = []
    values: list[Any] = []
    if asset_type:
        conditions.append("type = ?")
        values.append(asset_type)
    if source:
        conditions.append("source = ?")
        values.append(source)
    if status:
        conditions.append("status = ?")
        values.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jianying_assets {where} ORDER BY updated_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [row_to_jianying_asset(row) for row in rows]


def get_jianying_assets_by_ids(asset_ids: list[str]) -> list[dict[str, Any]]:
    init_db()
    normalized_ids = [asset_id for asset_id in asset_ids if asset_id]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jianying_assets WHERE id IN ({placeholders})",
            normalized_ids,
        ).fetchall()
    assets_by_id = {row["id"]: row_to_jianying_asset(row) for row in rows}
    return [assets_by_id[asset_id] for asset_id in normalized_ids if asset_id in assets_by_id]


def jianying_asset_counts() -> dict[str, Any]:
    init_db()
    with connect() as connection:
        total = connection.execute("SELECT COUNT(*) AS count FROM jianying_assets").fetchone()["count"]
        by_type = connection.execute(
            "SELECT type, COUNT(*) AS count FROM jianying_assets GROUP BY type ORDER BY count DESC"
        ).fetchall()
        by_status = connection.execute(
            "SELECT status, COUNT(*) AS count FROM jianying_assets GROUP BY status ORDER BY count DESC"
        ).fetchall()
    return {
        "total": total,
        "by_type": [dict(row) for row in by_type],
        "by_status": [dict(row) for row in by_status],
    }


def row_to_jianying_draft(row: sqlite3.Row) -> dict[str, Any]:
    draft = dict(row)
    draft["asset_report"] = json.loads(draft.pop("asset_report_json") or "{}")
    draft["meta"] = json.loads(draft.pop("meta_json") or "{}")
    return draft


def save_jianying_draft(
    *,
    draft_id: str,
    name: str,
    draft_path: str,
    source: str = "created",
    status: str = "created",
    asset_report: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jianying_drafts (
                id, name, draft_path, source, status, asset_report_json, meta_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                draft_path = excluded.draft_path,
                source = excluded.source,
                status = excluded.status,
                asset_report_json = excluded.asset_report_json,
                meta_json = excluded.meta_json,
                updated_at = excluded.updated_at
            """,
            (
                draft_id,
                name,
                draft_path,
                source,
                status,
                json.dumps(asset_report or {}, ensure_ascii=False),
                json.dumps(meta or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
    return get_jianying_draft(draft_id) or {}


def get_jianying_draft(draft_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM jianying_drafts WHERE id = ?", (draft_id,)).fetchone()
    return row_to_jianying_draft(row) if row else None


def delete_jianying_draft(draft_id: str) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute("DELETE FROM jianying_drafts WHERE id = ?", (draft_id,))
    return cursor.rowcount > 0


def list_jianying_drafts(*, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    values: list[Any] = []
    where = ""
    if status:
        where = "WHERE status = ?"
        values.append(status)
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jianying_drafts {where} ORDER BY updated_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [row_to_jianying_draft(row) for row in rows]


def row_to_jianying_template(row: sqlite3.Row) -> dict[str, Any]:
    template = dict(row)
    template["text_slots"] = json.loads(template.pop("text_slots_json") or "[]")
    template["media_slots"] = json.loads(template.pop("media_slots_json") or "[]")
    template["audio_slots"] = json.loads(template.pop("audio_slots_json") or "[]")
    template["required_assets"] = json.loads(template.pop("required_assets_json") or "{}")
    template["meta"] = json.loads(template.pop("meta_json") or "{}")
    return template


def save_jianying_template(
    *,
    template_id: str,
    name: str,
    template_path: str,
    text_slots: list[dict[str, Any]] | None = None,
    media_slots: list[dict[str, Any]] | None = None,
    audio_slots: list[dict[str, Any]] | None = None,
    required_assets: dict[str, Any] | None = None,
    status: str = "unknown",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jianying_templates (
                id, name, template_path, text_slots_json, media_slots_json, audio_slots_json,
                required_assets_json, status, meta_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                template_path = excluded.template_path,
                text_slots_json = excluded.text_slots_json,
                media_slots_json = excluded.media_slots_json,
                audio_slots_json = excluded.audio_slots_json,
                required_assets_json = excluded.required_assets_json,
                status = excluded.status,
                meta_json = excluded.meta_json,
                updated_at = excluded.updated_at
            """,
            (
                template_id,
                name,
                template_path,
                json.dumps(text_slots or [], ensure_ascii=False),
                json.dumps(media_slots or [], ensure_ascii=False),
                json.dumps(audio_slots or [], ensure_ascii=False),
                json.dumps(required_assets or {}, ensure_ascii=False),
                status,
                json.dumps(meta or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
    return get_jianying_template(template_id) or {}


def get_jianying_template(template_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM jianying_templates WHERE id = ?", (template_id,)).fetchone()
    return row_to_jianying_template(row) if row else None


def list_jianying_templates(*, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    values: list[Any] = []
    where = ""
    if status:
        where = "WHERE status = ?"
        values.append(status)
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jianying_templates {where} ORDER BY updated_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [row_to_jianying_template(row) for row in rows]
