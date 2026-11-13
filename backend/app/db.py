"""Persistence for tenders, vendors, evidence, findings, users and the audit trail.

PostgreSQL in production (TS_DATABASE_URL), SQLite for local development and tests. The schema
lives in ``app.schema`` and is created and evolved by Alembic migrations (``migrations/``), which
``init_db`` applies. Structured records live in typed columns; stage outputs (graph, similarity,
restructuring plan...) are stored as JSON artifacts.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import BACKEND_DIR, get_settings
from .schema import MARKET_TABLES

JSON_COLUMNS = {"meta", "directors", "value", "body", "removed", "run_result", "payload", "bundle"}


def _db_path() -> Path:
    return get_settings().db_path


def connect() -> sqlite3.Connection:
    """A DB-API connection. On PostgreSQL this is ``app.pg.Connection`` (same interface)."""
    settings = get_settings()
    if settings.is_postgres:
        from . import pg

        return pg.connect(settings.database_url)  # type: ignore[return-value]
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_migrated: set[str] = set()
_migrate_lock = threading.Lock()


def init_db() -> None:
    """Apply pending Alembic migrations (once per database per process)."""
    url = get_settings().sqlalchemy_url
    with _migrate_lock:
        if url in _migrated:
            return
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        command.upgrade(cfg, "head")
        _migrated.add(url)


# Users and the real market datasets survive a reset of the procurement data.
KEEP_ON_RESET = {"users", *(t.name for t in MARKET_TABLES)}


def reset_db() -> None:
    """Drop all procurement data, then re-apply migrations. Users and market data are kept."""
    from sqlalchemy import create_engine, inspect

    url = get_settings().sqlalchemy_url
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for name in inspect(conn).get_table_names():
                if name not in KEEP_ON_RESET:
                    conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}"')
    finally:
        engine.dispose()
    _migrated.discard(url)
    init_db()


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if key in JSON_COLUMNS and isinstance(value, str):
            value = json.loads(value)
        out[key] = value
    return out


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]  # type: ignore[misc]


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(sql, params).fetchone())


def put_artifact(conn: sqlite3.Connection, tender_id: str, stage: str, body: Any, created_at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO artifacts (tender_id, stage, body, created_at) VALUES (?, ?, ?, ?)",
        (tender_id, stage, dumps(body), created_at),
    )


def get_artifact(conn: sqlite3.Connection, tender_id: str, stage: str) -> Any | None:
    row = fetch_one(conn, "SELECT body FROM artifacts WHERE tender_id = ? AND stage = ?", (tender_id, stage))
    return row["body"] if row else None
