from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4

import psycopg

from backend.app.postgres_store import PG_URI_KEYS, quote_identifier, reset_postgres_runtime_state


POSTGRES_TEST_DSN_ENV = "TEST_DATABASE_URL"


def postgres_test_dsn() -> str:
    return os.getenv(POSTGRES_TEST_DSN_ENV) or os.getenv("DATABASE_URL") or ""


def require_postgres_tests() -> str:
    dsn = postgres_test_dsn()
    if not dsn:
        raise unittest.SkipTest(f"Set {POSTGRES_TEST_DSN_ENV} to run PostgreSQL-backed tests.")
    return dsn


@contextmanager
def isolated_postgres_schema(prefix: str = "test") -> Iterator[str]:
    dsn = require_postgres_tests()
    schema = f"{prefix}_{uuid4().hex}"
    quoted_schema = quote_identifier(schema)
    old_env = {key: os.environ.get(key) for key in [*PG_URI_KEYS.values(), "DATABASE_URL", "POSTGRES_SCHEMA"]}
    reset_postgres_runtime_state()
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(f"CREATE SCHEMA {quoted_schema}")
    try:
        for env_name in PG_URI_KEYS.values():
            os.environ[env_name] = dsn
        os.environ["DATABASE_URL"] = dsn
        os.environ["POSTGRES_SCHEMA"] = schema
        reset_postgres_runtime_state()
        yield schema
    finally:
        reset_postgres_runtime_state()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_postgres_runtime_state()
