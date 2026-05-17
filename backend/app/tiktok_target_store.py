from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "runtime" / "tiktok_targeting.sqlite3"

TARGET_USER_COLUMNS = {
    "avatar_url": "avatar_url TEXT NOT NULL DEFAULT ''",
    "signature": "signature TEXT NOT NULL DEFAULT ''",
    "aweme_count": "aweme_count INTEGER",
    "following_count": "following_count INTEGER",
    "is_private": "is_private INTEGER NOT NULL DEFAULT 0",
    "last_post_at": "last_post_at INTEGER",
    "searched_at": "searched_at INTEGER",
}

TARGET_SET_COLUMNS = {
    "keyword": "keyword TEXT NOT NULL DEFAULT ''",
    "filters_json": "filters_json TEXT NOT NULL DEFAULT '{}'",
    "video_strategy_json": "video_strategy_json TEXT NOT NULL DEFAULT '{}'",
}

TARGET_VIDEO_COLUMNS = {
    "set_id": "set_id TEXT NOT NULL DEFAULT ''",
    "create_time": "create_time INTEGER",
    "digg_count": "digg_count INTEGER",
    "comment_count": "comment_count INTEGER",
    "share_count": "share_count INTEGER",
    "collect_count": "collect_count INTEGER",
    "play_count": "play_count INTEGER",
    "is_top": "is_top INTEGER NOT NULL DEFAULT 0",
    "selection_strategy": "selection_strategy TEXT NOT NULL DEFAULT ''",
    "analysis_status": "analysis_status TEXT NOT NULL DEFAULT 'none'",
    "analysis_task_id": "analysis_task_id TEXT NOT NULL DEFAULT ''",
    "analysis_result_json": "analysis_result_json TEXT NOT NULL DEFAULT '{}'",
    "analyzed_at": "analyzed_at INTEGER",
}

TARGET_TASK_COLUMNS = {
    "strategy": "strategy TEXT NOT NULL DEFAULT ''",
    "retry_count": "retry_count INTEGER NOT NULL DEFAULT 0",
    "synced_at": "synced_at INTEGER",
}


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


def ensure_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_users (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL DEFAULT '',
                sec_user_id TEXT NOT NULL DEFAULT '',
                unique_id TEXT NOT NULL DEFAULT '',
                nickname TEXT NOT NULL DEFAULT '',
                follower_count INTEGER,
                like_count INTEGER,
                recent_update_at INTEGER,
                verified INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'candidate',
                source_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_sets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_set_users (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(set_id, user_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_videos (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                aweme_id TEXT NOT NULL DEFAULT '',
                desc TEXT NOT NULL DEFAULT '',
                cover_url TEXT NOT NULL DEFAULT '',
                play_url TEXT NOT NULL DEFAULT '',
                download_url TEXT NOT NULL DEFAULT '',
                source_json TEXT NOT NULL DEFAULT '{}',
                selected INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, aweme_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_tasks (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                video_id TEXT NOT NULL DEFAULT '',
                task_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        ensure_columns(connection, "tiktok_target_users", TARGET_USER_COLUMNS)
        ensure_columns(connection, "tiktok_target_sets", TARGET_SET_COLUMNS)
        ensure_columns(connection, "tiktok_target_videos", TARGET_VIDEO_COLUMNS)
        ensure_columns(connection, "tiktok_target_tasks", TARGET_TASK_COLUMNS)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_users_keyword ON tiktok_target_users(keyword, status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_videos_user ON tiktok_target_videos(user_id, selected)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_videos_set ON tiktok_target_videos(set_id, selected)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_tasks_status ON tiktok_target_tasks(status, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_tasks_video ON tiktok_target_tasks(video_id, status)")


def now() -> int:
    return int(time.time())


def load_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def row_to_target_user(row: sqlite3.Row) -> dict[str, Any]:
    user = dict(row)
    user["verified"] = bool(user.get("verified"))
    user["is_private"] = bool(user.get("is_private"))
    user["source_json"] = load_json(user.get("source_json"), {})
    return user


def row_to_target_set(row: sqlite3.Row) -> dict[str, Any]:
    target_set = dict(row)
    target_set["filters"] = load_json(target_set.pop("filters_json", "{}"), {})
    target_set["video_strategy"] = load_json(target_set.pop("video_strategy_json", "{}"), {})
    return target_set


def row_to_target_video(row: sqlite3.Row) -> dict[str, Any]:
    video = dict(row)
    video["selected"] = bool(video.get("selected"))
    video["is_top"] = bool(video.get("is_top"))
    video["source_json"] = load_json(video.get("source_json"), {})
    video["analysis_result"] = load_json(video.pop("analysis_result_json", "{}"), {})
    return video


def row_to_target_task(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["result"] = load_json(task.pop("result_json", "{}"), {})
    return task


def upsert_target_user(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_users (
                id, keyword, sec_user_id, unique_id, nickname, follower_count, like_count,
                recent_update_at, verified, status, source_json, created_at, updated_at,
                avatar_url, signature, aweme_count, following_count, is_private, last_post_at, searched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                keyword = excluded.keyword,
                sec_user_id = excluded.sec_user_id,
                unique_id = excluded.unique_id,
                nickname = excluded.nickname,
                follower_count = excluded.follower_count,
                like_count = excluded.like_count,
                recent_update_at = excluded.recent_update_at,
                verified = excluded.verified,
                status = excluded.status,
                source_json = excluded.source_json,
                avatar_url = excluded.avatar_url,
                signature = excluded.signature,
                aweme_count = excluded.aweme_count,
                following_count = excluded.following_count,
                is_private = excluded.is_private,
                last_post_at = excluded.last_post_at,
                searched_at = excluded.searched_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                payload.get('keyword', ''),
                payload.get('sec_user_id', ''),
                payload.get('unique_id', ''),
                payload.get('nickname', ''),
                payload.get('follower_count'),
                payload.get('like_count'),
                payload.get('recent_update_at'),
                1 if payload.get('verified') else 0,
                payload.get('status', 'candidate'),
                json.dumps(payload.get('source_json') or payload, ensure_ascii=False),
                current,
                current,
                payload.get('avatar_url') or payload.get('avatar') or '',
                payload.get('signature', ''),
                payload.get('aweme_count'),
                payload.get('following_count'),
                1 if payload.get('is_private') else 0,
                payload.get('last_post_at') or payload.get('recent_update_at'),
                payload.get('searched_at') or current,
            ),
        )
    return get_target_user(user_id) or {}


def get_target_user(user_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_users WHERE id = ?", (user_id,)).fetchone()
    return row_to_target_user(row) if row else None


def list_target_users(status: str | None = None, limit: int = 200, set_id: str | None = None) -> list[dict[str, Any]]:
    init_db()
    values: list[Any] = []
    if set_id:
        query = """
            SELECT u.*
            FROM tiktok_target_users u
            JOIN tiktok_target_set_users su ON su.user_id = u.id
            WHERE su.set_id = ?
        """
        values.append(set_id)
        if status:
            query += " AND u.status = ?"
            values.append(status)
        query += " ORDER BY u.updated_at DESC LIMIT ?"
        values.append(limit)
        with connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [row_to_target_user(row) for row in rows]

    query = "SELECT * FROM tiktok_target_users"
    if status:
        query += " WHERE status = ?"
        values.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(query, values).fetchall()
    return [row_to_target_user(row) for row in rows]


def create_target_set(
    set_id: str,
    name: str,
    note: str = '',
    *,
    keyword: str = '',
    filters: dict[str, Any] | None = None,
    video_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_sets (
                id, name, note, status, created_at, updated_at, keyword, filters_json, video_strategy_json
            )
            VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                note = excluded.note,
                keyword = excluded.keyword,
                filters_json = excluded.filters_json,
                video_strategy_json = excluded.video_strategy_json,
                updated_at = excluded.updated_at
            """,
            (
                set_id,
                name,
                note,
                current,
                current,
                keyword,
                json.dumps(filters or {}, ensure_ascii=False),
                json.dumps(video_strategy or {}, ensure_ascii=False),
            ),
        )
    return get_target_set(set_id) or {}


def get_target_set(set_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_sets WHERE id = ?", (set_id,)).fetchone()
    return row_to_target_set(row) if row else None


def update_target_set(
    set_id: str,
    *,
    name: str | None = None,
    note: str | None = None,
    keyword: str | None = None,
    filters: dict[str, Any] | None = None,
    video_strategy: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    init_db()
    current = now()
    updates: dict[str, Any] = {"updated_at": current}
    if name is not None:
        updates["name"] = name
    if note is not None:
        updates["note"] = note
    if keyword is not None:
        updates["keyword"] = keyword
    if filters is not None:
        updates["filters_json"] = json.dumps(filters, ensure_ascii=False)
    if video_strategy is not None:
        updates["video_strategy_json"] = json.dumps(video_strategy, ensure_ascii=False)
    if status is not None:
        updates["status"] = status
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [set_id]
    with connect() as connection:
        cursor = connection.execute(f"UPDATE tiktok_target_sets SET {assignments} WHERE id = ?", values)
    if cursor.rowcount == 0:
        return None
    return get_target_set(set_id)


def delete_target_set(set_id: str) -> bool:
    init_db()
    with connect() as connection:
        connection.execute("DELETE FROM tiktok_target_set_users WHERE set_id = ?", (set_id,))
        connection.execute("DELETE FROM tiktok_target_tasks WHERE set_id = ?", (set_id,))
        connection.execute("DELETE FROM tiktok_target_videos WHERE set_id = ?", (set_id,))
        cursor = connection.execute("DELETE FROM tiktok_target_sets WHERE id = ?", (set_id,))
    return cursor.rowcount > 0


def list_target_sets(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                s.*,
                COUNT(DISTINCT su.user_id) AS user_count,
                COUNT(DISTINCT v.id) AS video_count,
                SUM(CASE WHEN v.analysis_status = 'done' THEN 1 ELSE 0 END) AS analyzed_count
            FROM tiktok_target_sets s
            LEFT JOIN tiktok_target_set_users su ON su.set_id = s.id
            LEFT JOIN tiktok_target_videos v ON v.set_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_target_set(row) for row in rows]


def get_target_set_detail(set_id: str) -> dict[str, Any] | None:
    target_set = get_target_set(set_id)
    if not target_set:
        return None
    target_set["users"] = list_target_users(set_id=set_id, limit=500)
    target_set["videos"] = list_target_videos(set_id=set_id, limit=1000)
    target_set["tasks"] = list_target_tasks(set_id=set_id, limit=1000)
    return target_set


def add_user_to_target_set(set_id: str, user_id: str) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO tiktok_target_set_users (id, set_id, user_id, created_at) VALUES (?, ?, ?, ?)",
            (f'{set_id}:{user_id}', set_id, user_id, current),
        )
    return {"set_id": set_id, "user_id": user_id}


def remove_user_from_target_set(set_id: str, user_id: str) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM tiktok_target_set_users WHERE set_id = ? AND user_id = ?",
            (set_id, user_id),
        )
    return cursor.rowcount > 0


def create_target_video(video_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_videos (
                id, user_id, aweme_id, desc, cover_url, play_url, download_url, source_json,
                selected, created_at, updated_at, set_id, create_time, digg_count, comment_count,
                share_count, collect_count, play_count, is_top, selection_strategy, analysis_status,
                analysis_task_id, analysis_result_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id = excluded.user_id,
                aweme_id = excluded.aweme_id,
                desc = excluded.desc,
                cover_url = excluded.cover_url,
                play_url = excluded.play_url,
                download_url = excluded.download_url,
                source_json = excluded.source_json,
                updated_at = excluded.updated_at,
                selected = excluded.selected,
                set_id = excluded.set_id,
                create_time = excluded.create_time,
                digg_count = excluded.digg_count,
                comment_count = excluded.comment_count,
                share_count = excluded.share_count,
                collect_count = excluded.collect_count,
                play_count = excluded.play_count,
                is_top = excluded.is_top,
                selection_strategy = excluded.selection_strategy
            """,
            (
                video_id,
                user_id,
                payload.get('aweme_id', ''),
                payload.get('desc', ''),
                payload.get('cover_url', ''),
                payload.get('play_url', ''),
                payload.get('download_url', ''),
                json.dumps(payload.get('source_json') or payload, ensure_ascii=False),
                1 if payload.get('selected') else 0,
                current,
                current,
                payload.get('set_id', ''),
                payload.get('create_time'),
                payload.get('digg_count'),
                payload.get('comment_count'),
                payload.get('share_count'),
                payload.get('collect_count'),
                payload.get('play_count'),
                1 if payload.get('is_top') else 0,
                payload.get('selection_strategy', ''),
                payload.get('analysis_status', 'none'),
                payload.get('analysis_task_id', ''),
                json.dumps(payload.get('analysis_result') or payload.get('analysis_result_json') or {}, ensure_ascii=False),
                payload.get('analyzed_at'),
            ),
        )
    return get_target_video(video_id) or {}


def get_target_video(video_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_videos WHERE id = ?", (video_id,)).fetchone()
    return row_to_target_video(row) if row else None


def list_target_videos(
    *,
    set_id: str | None = None,
    user_id: str | None = None,
    selected: bool | None = None,
    analysis_status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    init_db()
    conditions = []
    values: list[Any] = []
    if set_id:
        conditions.append("set_id = ?")
        values.append(set_id)
    if user_id:
        conditions.append("user_id = ?")
        values.append(user_id)
    if selected is not None:
        conditions.append("selected = ?")
        values.append(1 if selected else 0)
    if analysis_status:
        conditions.append("analysis_status = ?")
        values.append(analysis_status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM tiktok_target_videos {where} ORDER BY selected DESC, digg_count DESC, create_time DESC LIMIT ?",
            values,
        ).fetchall()
    return [row_to_target_video(row) for row in rows]


def update_target_video_analysis(
    video_id: str,
    *,
    status: str,
    task_id: str = "",
    result: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any] | None:
    init_db()
    current = now()
    analyzed_at = current if status == "done" else None
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE tiktok_target_videos
            SET analysis_status = ?,
                analysis_task_id = COALESCE(NULLIF(?, ''), analysis_task_id),
                analysis_result_json = ?,
                analyzed_at = COALESCE(?, analyzed_at),
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                task_id,
                json.dumps(result or {}, ensure_ascii=False),
                analyzed_at,
                current,
                video_id,
            ),
        )
    if cursor.rowcount == 0:
        return None
    return get_target_video(video_id)


def create_target_task(
    task_id: str,
    *,
    set_id: str = "",
    user_id: str = "",
    video_id: str = "",
    ai_task_id: str = "",
    status: str = "pending",
    strategy: str = "",
) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_tasks (
                id, set_id, user_id, video_id, task_id, status, result_json, error,
                created_at, updated_at, strategy, retry_count, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '{}', '', ?, ?, ?, 0, ?)
            ON CONFLICT(id) DO UPDATE SET
                set_id = excluded.set_id,
                user_id = excluded.user_id,
                video_id = excluded.video_id,
                task_id = excluded.task_id,
                status = excluded.status,
                strategy = excluded.strategy,
                updated_at = excluded.updated_at,
                synced_at = excluded.synced_at
            """,
            (task_id, set_id, user_id, video_id, ai_task_id, status, current, current, strategy, current),
        )
    update_target_video_analysis(video_id, status=status, task_id=ai_task_id)
    return get_target_task(task_id) or {}


def get_target_task(target_task_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_tasks WHERE id = ?", (target_task_id,)).fetchone()
    return row_to_target_task(row) if row else None


def find_target_task_for_video(video_id: str, statuses: set[str] | None = None) -> dict[str, Any] | None:
    init_db()
    values: list[Any] = [video_id]
    query = "SELECT * FROM tiktok_target_tasks WHERE video_id = ?"
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        query += f" AND status IN ({placeholders})"
        values.extend(sorted(statuses))
    query += " ORDER BY created_at DESC LIMIT 1"
    with connect() as connection:
        row = connection.execute(query, values).fetchone()
    return row_to_target_task(row) if row else None


def list_target_tasks(
    *,
    set_id: str | None = None,
    video_id: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    init_db()
    conditions = []
    values: list[Any] = []
    if set_id:
        conditions.append("set_id = ?")
        values.append(set_id)
    if video_id:
        conditions.append("video_id = ?")
        values.append(video_id)
    if status:
        conditions.append("status = ?")
        values.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM tiktok_target_tasks {where} ORDER BY created_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [row_to_target_task(row) for row in rows]


def update_target_task_from_ai_task(target_task_id: str, ai_task: dict[str, Any]) -> dict[str, Any] | None:
    init_db()
    current = now()
    ai_status = ai_task.get("status") or "pending"
    status = "failed" if ai_status in {"failed", "error"} else ai_status
    result = ai_task.get("result") or {}
    error = ai_task.get("error") or ""
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE tiktok_target_tasks
            SET status = ?,
                result_json = ?,
                error = ?,
                updated_at = ?,
                synced_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False),
                error,
                current,
                current,
                target_task_id,
            ),
        )
        row = connection.execute("SELECT * FROM tiktok_target_tasks WHERE id = ?", (target_task_id,)).fetchone()
    if cursor.rowcount == 0 or not row:
        return None
    target_task = row_to_target_task(row)
    update_target_video_analysis(
        target_task["video_id"],
        status=status,
        task_id=target_task.get("task_id") or "",
        result=result,
        error=error,
    )
    return target_task
