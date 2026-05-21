from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import psycopg
from psycopg import sql

from backend.app.postgres_store import PG_URI_KEYS


@dataclass(frozen=True)
class TableMapping:
    source_db: str
    source_table: str
    target_table: str
    columns: tuple[str, ...]


TABLE_MAPPINGS: tuple[TableMapping, ...] = (
    TableMapping(
        "tasks.sqlite3",
        "tasks",
        "tasks",
        (
            "id",
            "type",
            "title",
            "status",
            "progress",
            "message",
            "provider",
            "payload_json",
            "result_json",
            "error",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "task_events",
        "task_events",
        (
            "id",
            "task_id",
            "status",
            "progress",
            "message",
            "detail_json",
            "created_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "analysis_archives",
        "analysis_archives",
        (
            "id",
            "task_id",
            "title",
            "provider",
            "video_json",
            "result_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "prompt_reverse_archives",
        "prompt_reverse_archives",
        (
            "id",
            "task_id",
            "title",
            "provider",
            "video_json",
            "result_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "production_reverse_archives",
        "production_reverse_archives",
        (
            "id",
            "task_id",
            "title",
            "provider",
            "video_json",
            "result_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "ai_video_jobs",
        "ai_video_jobs",
        (
            "task_id",
            "status",
            "stage",
            "priority",
            "provider",
            "video_fingerprint",
            "source_url",
            "duration",
            "progress",
            "attempts",
            "max_attempts",
            "locked_by",
            "locked_at",
            "heartbeat_at",
            "retry_after",
            "cancel_requested",
            "error_code",
            "error_message",
            "stage_state_json",
            "metrics_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "ai_video_artifacts",
        "ai_video_artifacts",
        (
            "id",
            "task_id",
            "type",
            "uri",
            "checksum",
            "size_bytes",
            "meta_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "ai_video_chunks",
        "ai_video_chunks",
        (
            "id",
            "task_id",
            "chunk_index",
            "start_time",
            "end_time",
            "status",
            "transcript",
            "frame_count",
            "grid_uri",
            "vision_result_uri",
            "attempts",
            "error_message",
            "meta_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "ai_model_runs",
        "ai_model_runs",
        (
            "id",
            "task_id",
            "chunk_id",
            "provider",
            "model",
            "purpose",
            "prompt_version",
            "input_uri",
            "output_uri",
            "status",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "cost_estimate",
            "error_message",
            "meta_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "jianying_assets",
        "jianying_assets",
        (
            "id",
            "type",
            "name",
            "source",
            "path",
            "resource_id",
            "effect_id",
            "duration",
            "width",
            "height",
            "hash",
            "status",
            "meta_json",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "jianying_drafts",
        "jianying_drafts",
        (
            "id",
            "name",
            "draft_path",
            "source",
            "status",
            "asset_report_json",
            "meta_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tasks.sqlite3",
        "jianying_templates",
        "jianying_templates",
        (
            "id",
            "name",
            "template_path",
            "text_slots_json",
            "media_slots_json",
            "audio_slots_json",
            "required_assets_json",
            "status",
            "meta_json",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_users",
        "tiktok_target_users",
        (
            "id",
            "keyword",
            "sec_user_id",
            "unique_id",
            "nickname",
            "follower_count",
            "like_count",
            "recent_update_at",
            "verified",
            "status",
            "source_json",
            "created_at",
            "updated_at",
            "avatar_url",
            "signature",
            "aweme_count",
            "following_count",
            "is_private",
            "last_post_at",
            "searched_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_sets",
        "tiktok_target_sets",
        (
            "id",
            "name",
            "note",
            "status",
            "created_at",
            "updated_at",
            "keyword",
            "filters_json",
            "video_strategy_json",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_set_users",
        "tiktok_target_set_users",
        (
            "id",
            "set_id",
            "user_id",
            "created_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_videos",
        "tiktok_target_videos",
        (
            "id",
            "user_id",
            "aweme_id",
            "description",
            "cover_url",
            "play_url",
            "download_url",
            "source_json",
            "selected",
            "created_at",
            "updated_at",
            "set_id",
            "create_time",
            "publish_hour",
            "publish_weekday",
            "publish_date",
            "publish_hour_bucket",
            "digg_count",
            "comment_count",
            "share_count",
            "collect_count",
            "play_count",
            "like_collect_ratio",
            "collect_like_ratio",
            "comment_like_ratio",
            "share_like_ratio",
            "engagement_score",
            "engagement_rate",
            "metrics_json",
            "comment_snapshot_status",
            "comment_snapshot_at",
            "comment_saved_count",
            "reply_saved_count",
            "is_top",
            "selection_strategy",
            "analysis_status",
            "analysis_task_id",
            "analysis_result_json",
            "analyzed_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_tasks",
        "tiktok_target_tasks",
        (
            "id",
            "set_id",
            "user_id",
            "video_id",
            "task_id",
            "status",
            "result_json",
            "error",
            "created_at",
            "updated_at",
            "strategy",
            "retry_count",
            "synced_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_video_comments",
        "tiktok_target_video_comments",
        (
            "id",
            "video_id",
            "aweme_id",
            "comment_id",
            "parent_comment_id",
            "reply_to_comment_id",
            "user_id",
            "sec_uid",
            "unique_id",
            "nickname",
            "text",
            "digg_count",
            "reply_count",
            "create_time",
            "is_pinned",
            "is_author",
            "rank_index",
            "level",
            "source_json",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_video_interaction_insights",
        "tiktok_target_video_interaction_insights",
        (
            "video_id",
            "aweme_id",
            "comment_count_saved",
            "reply_count_saved",
            "keyword_counts_json",
            "symbol_counts_json",
            "emotion_profile_json",
            "creator_reply_tactics_json",
            "top_comments_json",
            "pinned_comments_json",
            "author_replies_json",
            "raw_ai_json",
            "analyzed_at",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_user_video_pages",
        "tiktok_target_user_video_pages",
        (
            "id",
            "cache_key",
            "source",
            "user_id",
            "sec_user_id",
            "unique_id",
            "max_cursor",
            "count",
            "sort_type",
            "filter_type",
            "next_cursor",
            "has_more",
            "item_count",
            "request_json",
            "items_json",
            "raw_json",
            "pagination_json",
            "normalized_json",
            "fetched_at",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_user_search_pages",
        "tiktok_target_user_search_pages",
        (
            "id",
            "cache_key",
            "source",
            "keyword",
            "cursor",
            "count",
            "search_id",
            "douyin_user_fans",
            "douyin_user_type",
            "request_json",
            "items_json",
            "raw_json",
            "pagination_json",
            "normalized_json",
            "fetched_at",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "tiktok_targeting.sqlite3",
        "tiktok_target_video_comment_pages",
        "tiktok_target_video_comment_pages",
        (
            "id",
            "cache_key",
            "source",
            "video_id",
            "aweme_id",
            "item_id",
            "comment_id",
            "page_kind",
            "cursor",
            "count",
            "request_json",
            "items_json",
            "raw_json",
            "pagination_json",
            "normalized_json",
            "fetched_at",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "short_video_analysis.sqlite3",
        "short_video_items",
        "short_video_items",
        (
            "id",
            "platform",
            "source_id",
            "source_url",
            "author_id",
            "author_name",
            "title",
            "description",
            "genre",
            "publish_time",
            "publish_hour",
            "publish_weekday",
            "cover_url",
            "video_url",
            "local_video_path",
            "raw_json",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "short_video_analysis.sqlite3",
        "short_video_metric_snapshots",
        "short_video_metric_snapshots",
        (
            "id",
            "video_id",
            "like_count",
            "comment_count",
            "share_count",
            "collect_count",
            "play_count",
            "interaction_rate",
            "save_rate",
            "share_rate",
            "engagement_score",
            "engagement_rate",
            "property_tags_json",
            "raw_json",
            "captured_at",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "short_video_analysis.sqlite3",
        "short_video_analysis_runs",
        "short_video_analysis_runs",
        (
            "id",
            "video_id",
            "task_id",
            "provider",
            "model_summary",
            "genre",
            "status",
            "evidence_path",
            "job_path",
            "result_json",
            "markdown_report",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "short_video_analysis.sqlite3",
        "short_video_analysis_segments",
        "short_video_analysis_segments",
        (
            "id",
            "run_id",
            "video_id",
            "segment_id",
            "start_seconds",
            "end_seconds",
            "time_range",
            "transcript",
            "visual_style",
            "audio_pacing",
            "narrative_technique",
            "retention_mechanism",
            "raw_json",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "short_video_analysis.sqlite3",
        "short_video_formula_library",
        "short_video_formula_library",
        (
            "id",
            "video_id",
            "run_id",
            "genre",
            "formula_name",
            "generic_formula",
            "hook_template",
            "script_template",
            "cta_template",
            "visual_blueprint_json",
            "risk_json",
            "raw_json",
            "created_at",
            "updated_at",
        ),
    ),
    TableMapping(
        "short_video_analysis.sqlite3",
        "short_video_remake_exports",
        "short_video_remake_exports",
        (
            "id",
            "run_id",
            "video_id",
            "task_id",
            "title",
            "genre",
            "target_genre",
            "export_type",
            "markdown",
            "source_json",
            "rewritten_json",
            "status",
            "created_at",
            "updated_at",
        ),
    ),
)

BATCH_SIZE = int(os.getenv("SQLITE_MIGRATION_BATCH_SIZE", "1000") or 1000)

TARGET_STORE_BY_TABLE: dict[str, str] = {
    "tasks": "core_task",
    "task_events": "task_audit",
    "analysis_archives": "archive",
    "prompt_reverse_archives": "archive",
    "production_reverse_archives": "archive",
    "ai_video_jobs": "ai_video_queue",
    "ai_video_artifacts": "ai_video_queue",
    "ai_video_chunks": "ai_video_queue",
    "ai_model_runs": "ai_video_queue",
    "tiktok_target_users": "tiktok_target",
    "tiktok_target_sets": "tiktok_target",
    "tiktok_target_set_users": "tiktok_target",
    "tiktok_target_videos": "tiktok_target",
    "tiktok_target_tasks": "tiktok_target",
    "tiktok_target_video_comments": "tiktok_target",
    "tiktok_target_video_interaction_insights": "tiktok_target",
    "tiktok_target_user_video_pages": "tiktok_target_cache",
    "tiktok_target_user_search_pages": "tiktok_target_cache",
    "tiktok_target_video_comment_pages": "tiktok_target_cache",
    "short_video_items": "short_video_analysis",
    "short_video_metric_snapshots": "short_video_analysis",
    "short_video_analysis_runs": "short_video_analysis",
    "short_video_analysis_segments": "short_video_analysis",
    "short_video_formula_library": "short_video_analysis",
    "short_video_remake_exports": "short_video_analysis",
    "jianying_assets": "media",
    "jianying_drafts": "media",
    "jianying_templates": "media",
}


def resolve_path(root: Path, db_name: str) -> Path:
    path = root / db_name
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def read_rows(db_path: Path, table: str) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            return []
        columns = rows[0].keys()
        return [tuple(row[col] for col in columns) for row in rows]


def read_columns(db_path: Path, table: str) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def sqlite_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row[0] if row else 0)


def target_store_for_table(table: str) -> str:
    try:
        return TARGET_STORE_BY_TABLE[table]
    except KeyError as exc:
        raise KeyError(f"Missing target store mapping for table: {table}") from exc


def target_dsn_for_table(table: str, fallback_dsn: str) -> str:
    store = target_store_for_table(table)
    env_name = PG_URI_KEYS[store]
    return os.getenv(env_name) or os.getenv("DATABASE_URL") or fallback_dsn


def pg_count(pg_dsn: str, schema: str | None, table: str) -> int:
    with psycopg.connect(pg_dsn) as connection:
        if schema:
            connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        row = connection.execute(sql.SQL("SELECT COUNT(*) AS count FROM {}").format(sql.Identifier(table))).fetchone()
    return int(row[0] if row else 0)


def target_column_types(pg_dsn: str, schema: str | None, table: str) -> dict[str, str]:
    with psycopg.connect(pg_dsn) as connection:
        if schema:
            connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        rows = connection.execute(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
    return {
        str(row[0]): str(row[1] or row[2] or "")
        for row in rows
    }


def coerce_pg_value(value: Any, data_type: str) -> Any:
    if value is None:
        if data_type.lower() == "boolean":
            return False
        return None

    normalized_type = data_type.lower()
    if normalized_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {"1", "t", "true", "y", "yes", "on"}:
            return True
        if text in {"0", "f", "false", "n", "no", "off", ""}:
            return False
        return bool(text)
    if normalized_type in {
        "smallint",
        "integer",
        "bigint",
        "int2",
        "int4",
        "int8",
        "serial",
        "bigserial",
        "smallserial",
    }:
        if value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if normalized_type in {"real", "double precision", "numeric", "decimal", "float4", "float8"}:
        if value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if normalized_type in {"json", "jsonb"}:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value
    return value


def dump_table_counts(root: Path) -> None:
    for mapping in TABLE_MAPPINGS:
        db_path = resolve_path(root, mapping.source_db)
        print(f"{mapping.source_db}:{mapping.source_table} = {sqlite_count(db_path, mapping.source_table)}")


def select_mappings(table_names: list[str] | None) -> tuple[TableMapping, ...]:
    if not table_names:
        return TABLE_MAPPINGS
    wanted = {name.strip() for name in table_names if name.strip()}
    selected = tuple(mapping for mapping in TABLE_MAPPINGS if mapping.target_table in wanted)
    missing = sorted(wanted - {mapping.target_table for mapping in selected})
    if missing:
        raise SystemExit(f"Unknown target tables: {', '.join(missing)}")
    return selected


def truncate_target_tables(pg_dsn: str, schema: str | None, mappings: tuple[TableMapping, ...]) -> None:
    grouped: dict[str, set[str]] = {}
    for mapping in mappings:
        store = target_store_for_table(mapping.target_table)
        grouped.setdefault(store, set()).add(mapping.target_table)
    for store, tables in grouped.items():
        dsn = os.getenv(PG_URI_KEYS[store]) or os.getenv("DATABASE_URL") or pg_dsn
        if not dsn:
            raise SystemExit(f"Missing PostgreSQL DSN for store: {store}")
        with psycopg.connect(dsn) as connection:
            if schema:
                connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
            statement = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(", ").join(sql.Identifier(table) for table in sorted(tables))
            )
            connection.execute(statement)


def bootstrap_target_schema(pg_dsn: str, schema: str | None) -> None:
    from backend.app.postgres_store import reset_postgres_runtime_state
    from backend.app.postgres_store import init_all_postgres_databases

    env_names = [*PG_URI_KEYS.values(), "DATABASE_URL", "POSTGRES_SCHEMA"]
    old_env = {key: os.environ.get(key) for key in env_names}
    try:
        if pg_dsn:
            os.environ["DATABASE_URL"] = pg_dsn
            for env_name in PG_URI_KEYS.values():
                os.environ[env_name] = pg_dsn
        if schema:
            os.environ["POSTGRES_SCHEMA"] = schema
        reset_postgres_runtime_state()
        init_all_postgres_databases()
    finally:
        reset_postgres_runtime_state()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def verify_counts(sqlite_root: Path, pg_dsn: str, schema: str | None, mappings: tuple[TableMapping, ...]) -> list[str]:
    mismatches: list[str] = []
    seen: set[tuple[str, str]] = set()
    for mapping in mappings:
        key = (mapping.source_db, mapping.source_table)
        if key in seen:
            continue
        seen.add(key)
        source_count = sqlite_count(resolve_path(sqlite_root, mapping.source_db), mapping.source_table)
        target_dsn = target_dsn_for_table(mapping.target_table, pg_dsn)
        if not target_dsn:
            mismatches.append(f"{mapping.target_table} missing PostgreSQL DSN")
            continue
        target_count = pg_count(target_dsn, schema, mapping.target_table)
        if source_count != target_count:
            mismatches.append(
                f"{mapping.source_db}:{mapping.source_table} source={source_count} target={target_count}"
            )
    return mismatches


def import_table(
    *,
    sqlite_root: Path,
    pg_dsn: str,
    schema: str | None,
    mapping: TableMapping,
    dry_run: bool,
) -> int:
    db_path = resolve_path(sqlite_root, mapping.source_db)
    columns = read_columns(db_path, mapping.source_table)
    selected_columns = [column for column in mapping.columns if column in columns]
    if not selected_columns:
        return 0
    column_list = ", ".join(selected_columns)
    placeholders = ", ".join(["%s"] * len(selected_columns))
    if dry_run:
        total = sqlite_count(db_path, mapping.source_table)
        print(f"[dry-run] {mapping.source_db}:{mapping.source_table} -> {mapping.target_table} rows={total} cols={len(selected_columns)}")
        return total
    target_dsn = target_dsn_for_table(mapping.target_table, pg_dsn)
    if not target_dsn:
        raise SystemExit(f"Missing PostgreSQL DSN for target table: {mapping.target_table}")
    column_types = target_column_types(target_dsn, schema, mapping.target_table)
    total = 0
    with psycopg.connect(target_dsn) as connection:
        if schema:
            connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        with sqlite3.connect(db_path) as sqlite_connection:
            sqlite_connection.row_factory = sqlite3.Row
            cursor = sqlite_connection.execute(f"SELECT {column_list} FROM {mapping.source_table}")
            with connection.cursor() as pg_cursor:
                column_sql = sql.SQL(", ").join(sql.Identifier(column) for column in selected_columns)
                copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
                    sql.Identifier(mapping.target_table),
                    column_sql,
                )
                while True:
                    batch = cursor.fetchmany(BATCH_SIZE)
                    if not batch:
                        break
                    payload = [
                        tuple(
                            coerce_pg_value(row[column], column_types.get(column, ""))
                            for column in selected_columns
                        )
                        for row in batch
                    ]
                    with pg_cursor.copy(copy_sql) as copy:
                        for row in payload:
                            copy.write_row(row)
                    total += len(payload)
        connection.commit()
    print(f"[imported] {mapping.source_db}:{mapping.source_table} -> {mapping.target_table} rows={total}")
    return total


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite data into PostgreSQL.")
    parser.add_argument("--sqlite-root", default="data/runtime", help="Legacy SQLite root directory.")
    parser.add_argument(
        "--pg-dsn",
        default=os.getenv("DATABASE_URL") or os.getenv("CORE_TASK_DATABASE_URL") or "postgresql://postgres:123456@127.0.0.1:5432/postgres",
        help="PostgreSQL DSN.",
    )
    parser.add_argument("--schema", default=os.getenv("POSTGRES_SCHEMA") or "", help="Target PostgreSQL schema.")
    parser.add_argument("--dry-run", action="store_true", help="Only print counts and planned imports.")
    parser.add_argument("--truncate", action="store_true", help="Truncate target tables before import.")
    parser.add_argument("--bootstrap", action="store_true", help="Create/upgrade the PostgreSQL schema before import.")
    parser.add_argument("--verify", action="store_true", help="Compare source/target counts after import.")
    parser.add_argument("--counts", action="store_true", help="Print source counts and exit.")
    parser.add_argument(
        "--tables",
        nargs="+",
        default=[],
        help="Only migrate the listed target tables. Use target table names from TABLE_MAPPINGS.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    sqlite_root = Path(args.sqlite_root).resolve()
    if not sqlite_root.exists():
        raise SystemExit(f"SQLite root not found: {sqlite_root}")

    mappings = select_mappings(args.tables)

    if args.counts:
        for mapping in mappings:
            db_path = resolve_path(sqlite_root, mapping.source_db)
            print(f"{mapping.source_db}:{mapping.source_table} = {sqlite_count(db_path, mapping.source_table)}")
        return 0

    if not args.pg_dsn and not args.dry_run:
        raise SystemExit("Missing PostgreSQL DSN. Set DATABASE_URL or pass --pg-dsn.")

    if args.bootstrap and not args.dry_run:
        bootstrap_target_schema(args.pg_dsn, args.schema or None)

    if args.truncate and not args.dry_run:
        truncate_target_tables(args.pg_dsn, args.schema or None, mappings)

    total = 0
    for mapping in mappings:
        total += import_table(
            sqlite_root=sqlite_root,
            pg_dsn=args.pg_dsn,
            schema=args.schema or None,
            mapping=mapping,
            dry_run=args.dry_run,
        )
    if args.dry_run:
        print(f"[dry-run] total_rows={total}")
    else:
        print(f"[done] total_rows={total}")
        if args.verify:
            mismatches = verify_counts(sqlite_root, args.pg_dsn, args.schema or None, mappings)
            if mismatches:
                print("[verify] mismatch detected:")
                for mismatch in mismatches:
                    print(f"  - {mismatch}")
                return 1
            print("[verify] source and target counts match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
