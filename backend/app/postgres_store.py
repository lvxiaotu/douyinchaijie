from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from typing import Any, Iterator
from pathlib import Path

from dotenv import load_dotenv
from psycopg import Connection
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


PG_URI_KEYS = {
    "core_task": "CORE_TASK_DATABASE_URL",
    "task_audit": "TASK_AUDIT_DATABASE_URL",
    "archive": "ARCHIVE_DATABASE_URL",
    "ai_video_queue": "AI_VIDEO_QUEUE_DATABASE_URL",
    "tiktok_target": "TIKTOK_TARGET_DATABASE_URL",
    "tiktok_target_cache": "TIKTOK_TARGET_CACHE_DATABASE_URL",
    "short_video_analysis": "SHORT_VIDEO_ANALYSIS_DATABASE_URL",
    "media": "MEDIA_DATABASE_URL",
}

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_POOLS: dict[str, ConnectionPool] = {}
_POOLS_LOCK = threading.Lock()
_INIT_LOCK = threading.Lock()
_INITIALIZED: set[str] = set()


def database_url(name: str) -> str:
    env_name = PG_URI_KEYS[name]
    url = os.getenv(env_name) or os.getenv("DATABASE_URL") or ""
    if not url:
        raise RuntimeError(f"PostgreSQL DSN is not configured. Set {env_name} or DATABASE_URL.")
    return url


@contextmanager
def pg_connection(name: str) -> Iterator[Connection[Any]]:
    with _POOLS_LOCK:
        pool = _POOLS.get(name)
        if pool is None:
            pool = ConnectionPool(
                conninfo=database_url(name),
                kwargs={"row_factory": dict_row},
                min_size=int(os.getenv("POSTGRES_POOL_MIN_SIZE", "1") or 1),
                max_size=int(os.getenv("POSTGRES_POOL_MAX_SIZE", "10") or 10),
            )
            _POOLS[name] = pool
    with pool.connection() as connection:
        schema = os.getenv("POSTGRES_SCHEMA") or ""
        if schema:
            connection.execute(f"SET search_path TO {quote_identifier(schema)}, public")
        yield connection


def close_all_postgres_pools(*, timeout: float = 10.0) -> None:
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close(timeout=timeout)


def reset_postgres_runtime_state() -> None:
    close_all_postgres_pools()
    with _INIT_LOCK:
        _INITIALIZED.clear()


def run_once(key: str, callback: Any) -> None:
    if key in _INITIALIZED:
        return
    with _INIT_LOCK:
        if key in _INITIALIZED:
            return
        callback()
        _INITIALIZED.add(key)


def quote_identifier(value: str) -> str:
    if not _IDENTIFIER.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def placeholders(count: int) -> str:
    if count <= 0:
        raise ValueError("placeholder count must be positive")
    return ", ".join("%s" for _ in range(count))


def jsonb_text_update(column: str, key: str, value_placeholder: str = "%s") -> str:
    quote_identifier(column)
    escaped_key = key.replace("'", "''")
    return (
        f"{column} = jsonb_set("
        f"COALESCE(NULLIF({column}, '')::jsonb, '{{}}'::jsonb), "
        f"'{{{escaped_key}}}', to_jsonb({value_placeholder}::text), true"
        f")::text"
    )


def ensure_columns(connection: Connection[Any], table: str, columns: dict[str, str]) -> None:
    table_name = quote_identifier(table)
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    existing = {str(row["column_name"]) for row in rows}
    for name, definition in columns.items():
        column_name = quote_identifier(name)
        if column_name not in existing:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def sync_sequence_to_max(connection: Connection[Any], table: str, column: str = "id") -> None:
    table_name = quote_identifier(table)
    column_name = quote_identifier(column)
    seq_row = connection.execute(
        "SELECT pg_get_serial_sequence(%s, %s) AS seq",
        (table_name, column_name),
    ).fetchone()
    sequence = str(seq_row["seq"]) if seq_row and seq_row["seq"] else ""
    if not sequence:
        return
    max_row = connection.execute(f"SELECT MAX({column_name}) AS max_value FROM {table_name}").fetchone()
    max_value = max_row["max_value"] if max_row else None
    if max_value is None:
        connection.execute("SELECT setval(%s, 1, false)", (sequence,))
    else:
        connection.execute("SELECT setval(%s, %s, true)", (sequence, int(max_value)))


def init_all_postgres_databases() -> None:
    from backend.app.short_video_analysis_store import init_db as init_short_video_analysis_db
    from backend.app.task_store import init_db as init_task_dbs
    from backend.app.tiktok_target_store import init_db as init_tiktok_target_db
    from backend.app.video_analysis_queue import init_ai_video_queue_db

    init_task_dbs()
    init_ai_video_queue_db()
    init_tiktok_target_db()
    init_short_video_analysis_db()
