from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "runtime" / "tiktok_targeting.sqlite3"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


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
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_users_keyword ON tiktok_target_users(keyword, status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_videos_user ON tiktok_target_videos(user_id, selected)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_tasks_status ON tiktok_target_tasks(status, created_at)")


def now() -> int:
    return int(time.time())


def upsert_target_user(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_users (
                id, keyword, sec_user_id, unique_id, nickname, follower_count, like_count,
                recent_update_at, verified, status, source_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
    return get_target_user(user_id) or {}


def get_target_user(user_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_target_users(status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    query = "SELECT * FROM tiktok_target_users"
    values: list[Any] = []
    if status:
        query += " WHERE status = ?"
        values.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def create_target_set(set_id: str, name: str, note: str = '') -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_sets (id, name, note, status, created_at, updated_at)
            VALUES (?, ?, ?, 'draft', ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, note = excluded.note, updated_at = excluded.updated_at
            """,
            (set_id, name, note, current, current),
        )
    return get_target_set(set_id) or {}


def get_target_set(set_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_sets WHERE id = ?", (set_id,)).fetchone()
    return dict(row) if row else None


def add_user_to_target_set(set_id: str, user_id: str) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO tiktok_target_set_users (id, set_id, user_id, created_at) VALUES (?, ?, ?, ?)",
            (f'{set_id}:{user_id}', set_id, user_id, current),
        )
    return {"set_id": set_id, "user_id": user_id}


def create_target_video(video_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_videos (
                id, user_id, aweme_id, desc, cover_url, play_url, download_url, source_json, selected, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                aweme_id = excluded.aweme_id,
                desc = excluded.desc,
                cover_url = excluded.cover_url,
                play_url = excluded.play_url,
                download_url = excluded.download_url,
                source_json = excluded.source_json,
                updated = excluded.updated_at,
                selected = excluded.selected
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
            ),
        )
    return get_target_video(video_id) or {}


def get_target_video(video_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_videos WHERE id = ?", (video_id,)).fetchone()
    return dict(row) if row else None
