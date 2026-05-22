from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
import psycopg
from psycopg import sql

from backend.app.postgres_store import PG_URI_KEYS, quote_identifier
from scripts.migrate_sqlite_to_postgres import TABLE_MAPPINGS, target_store_for_table


load_dotenv(ROOT_DIR / ".env")


POSTGRES_STORE_ORDER = tuple(PG_URI_KEYS.keys())
LEGACY_SQLITE_ROOT = ROOT_DIR / "data" / "runtime"


@dataclass(frozen=True)
class TablePlan:
    name: str
    exists: bool
    rows: int


@dataclass(frozen=True)
class JobPlan:
    kind: str
    label: str
    target: str
    tables: tuple[TablePlan, ...]
    dsn: str = ""
    sqlite_path: Path | None = None

    @property
    def total_rows(self) -> int:
        return sum(table.rows for table in self.tables if table.exists)


def quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def resolve_dsn(store: str) -> str:
    env_name = PG_URI_KEYS[store]
    return os.getenv(env_name) or os.getenv("DATABASE_URL") or ""


def set_search_path(connection: Any, schema: str) -> None:
    if schema:
        connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))


def table_exists_postgres(connection: Any, table: str) -> bool:
    row = connection.execute("SELECT to_regclass(%s) AS regclass", (table,)).fetchone()
    return bool(row and row[0])


def count_postgres_table(connection: Any, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {quote_identifier(table)}").fetchone()
    return int(row[0] if row else 0)


def table_exists_sqlite(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return bool(row)


def count_sqlite_table(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {quote_sqlite_identifier(table)}").fetchone()
    return int(row[0] if row else 0)


def build_postgres_jobs(schema: str) -> list[JobPlan]:
    grouped: dict[str, list[str]] = {store: [] for store in POSTGRES_STORE_ORDER}
    for mapping in TABLE_MAPPINGS:
        grouped[target_store_for_table(mapping.target_table)].append(mapping.target_table)

    jobs: list[JobPlan] = []
    for store in POSTGRES_STORE_ORDER:
        tables = grouped.get(store, [])
        if not tables:
            continue
        dsn = resolve_dsn(store)
        if not dsn:
            raise SystemExit(f"缺少 PostgreSQL 连接串：{PG_URI_KEYS[store]} 或 DATABASE_URL")
        table_plans: list[TablePlan] = []
        with psycopg.connect(dsn) as connection:
            set_search_path(connection, schema)
            for table in tables:
                exists = table_exists_postgres(connection, table)
                rows = count_postgres_table(connection, table) if exists else 0
                table_plans.append(TablePlan(name=table, exists=exists, rows=rows))
        jobs.append(
            JobPlan(
                kind="postgres",
                label=f"PostgreSQL / {store}",
                target=store,
                tables=tuple(table_plans),
                dsn=dsn,
            )
        )
    return jobs


def build_sqlite_jobs(sqlite_root: Path) -> list[JobPlan]:
    grouped: dict[Path, list[str]] = {}
    for mapping in TABLE_MAPPINGS:
        db_path = (sqlite_root / mapping.source_db).resolve()
        grouped.setdefault(db_path, [])
        if mapping.source_table not in grouped[db_path]:
            grouped[db_path].append(mapping.source_table)

    jobs: list[JobPlan] = []
    for db_path, tables in grouped.items():
        if not db_path.exists():
            continue
        table_plans: list[TablePlan] = []
        with sqlite3.connect(db_path) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            for table in tables:
                exists = table_exists_sqlite(connection, table)
                rows = count_sqlite_table(connection, table) if exists else 0
                table_plans.append(TablePlan(name=table, exists=exists, rows=rows))
        jobs.append(
            JobPlan(
                kind="sqlite",
                label=f"SQLite / {db_path.name}",
                target=db_path.name,
                tables=tuple(table_plans),
                sqlite_path=db_path,
            )
        )
    return jobs


def print_plan(jobs: list[JobPlan]) -> None:
    total_rows = sum(job.total_rows for job in jobs)
    print("=" * 60)
    print("一键清空业务数据")
    print(f"目标数：{len(jobs)}  |  预估清空行数：{total_rows}")
    print("=" * 60)
    for index, job in enumerate(jobs, start=1):
        print(f"[预览 {index}/{len(jobs)}] {job.label}")
        for table in job.tables:
            if table.exists:
                print(f"  - {table.name}: {table.rows} 行")
            else:
                print(f"  - {table.name}: 不存在，跳过")
        print(f"  小计：{job.total_rows} 行")
    print()


def clear_postgres_job(job: JobPlan, schema: str) -> int:
    tables = [table.name for table in job.tables if table.exists]
    if not tables:
        print("  没有可清空的表，跳过。", flush=True)
        return 0
    with psycopg.connect(job.dsn) as connection:
        set_search_path(connection, schema)
        statement = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(sql.Identifier(table) for table in tables)
        )
        connection.execute(statement)
        connection.commit()
    return job.total_rows


def clear_sqlite_job(job: JobPlan) -> int:
    if job.sqlite_path is None:
        return 0
    tables = [table.name for table in job.tables if table.exists]
    if not tables:
        print("  没有可清空的表，跳过。", flush=True)
        return 0
    with sqlite3.connect(job.sqlite_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN")
        for table in tables:
            connection.execute(f"DELETE FROM {quote_sqlite_identifier(table)}")
        try:
            connection.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError:
            pass
        connection.commit()
    return job.total_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键清空本项目的所有业务数据。")
    parser.add_argument("--yes", action="store_true", help="跳过二次确认，直接执行。")
    parser.add_argument("--dry-run", action="store_true", help="只展示清空计划，不执行。")
    parser.add_argument("--skip-sqlite", action="store_true", help="只清空 PostgreSQL，跳过旧 SQLite 数据库。")
    parser.add_argument("--sqlite-root", default=str(LEGACY_SQLITE_ROOT), help="旧 SQLite 数据库根目录。")
    parser.add_argument("--schema", default=os.getenv("POSTGRES_SCHEMA") or "", help="PostgreSQL schema。")
    args = parser.parse_args(argv)

    sqlite_root = Path(args.sqlite_root).resolve()

    jobs = build_postgres_jobs(args.schema)
    if not args.skip_sqlite:
        jobs.extend(build_sqlite_jobs(sqlite_root))

    if not jobs:
        print("没有找到可清空的业务数据。")
        return 0

    print_plan(jobs)

    if args.dry_run:
        print("dry-run 完成：未执行任何删除操作。")
        return 0

    if not args.yes:
        confirm = input("输入 YES 继续清空：").strip().lower()
        if confirm not in {"yes", "y", "是"}:
            print("已取消。")
            return 1

    total_removed = 0
    total_jobs = len(jobs)
    for index, job in enumerate(jobs, start=1):
        print(f"[{index}/{total_jobs}] 正在清空 {job.label} ...", flush=True)
        for table in job.tables:
            if table.exists:
                print(f"  - {table.name}: {table.rows} 行", flush=True)
            else:
                print(f"  - {table.name}: 不存在，跳过", flush=True)
        removed = clear_postgres_job(job, args.schema) if job.kind == "postgres" else clear_sqlite_job(job)
        total_removed += removed
        print(f"  完成：已清空 {removed} 行。", flush=True)

    print("=" * 60)
    print(f"清空完成，共删除 {total_removed} 行业务数据。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
