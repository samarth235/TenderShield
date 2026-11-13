"""Market intelligence store: real historical awards, bids and supplier profiles.

On PostgreSQL the market tables live in the main database (created by the Alembic migration;
``db.reset_db`` never drops them). On SQLite they are kept in their own file (``market.db``,
TS_MARKET_DB) so the derived store can be rebuilt or shipped independently.

Every row records the dataset it came from (``source_id``), and every dataset records its origin
URL, licence, file SHA-256 and import time, so any supplier match can be traced back to the
published record that supports it.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from ..config import get_settings
from ..schema import MARKET_TABLES

_created: set[str] = set()

JSON_COLUMNS = {"sources", "capabilities", "capability_values", "identifiers", "msme_evidence"}


def market_db_path() -> Path:
    override = os.environ.get("TS_MARKET_DB")
    return Path(override) if override else get_settings().data_dir / "market.db"


def _use_main_db(path: Path | None) -> bool:
    return path is None and get_settings().is_postgres


def market_available() -> bool:
    """Whether a market store exists (it may still hold no awards)."""
    return get_settings().is_postgres or market_db_path().exists()


def connect(path: Path | None = None) -> sqlite3.Connection:
    if _use_main_db(path):
        from ..db import connect as main_connect
        from ..db import init_db

        init_db()
        return main_connect()
    path = path or market_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if str(path) not in _created:
        from sqlalchemy import create_engine

        engine = create_engine(f"sqlite:///{path}")
        MARKET_TABLES[0].metadata.create_all(engine, tables=MARKET_TABLES)
        engine.dispose()
        _created.add(str(path))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def market_session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row(r) -> dict | None:
    if r is None:
        return None
    out = dict(r)
    for key in JSON_COLUMNS & out.keys():
        if isinstance(out[key], str):
            out[key] = json.loads(out[key])
    return out


def rows(cursor: Iterable) -> list[dict]:
    return [row(r) for r in cursor]  # type: ignore[misc]


def drop_source(conn: sqlite3.Connection, source_id: str) -> None:
    for table in ("market_awards", "market_bids", "market_sources"):
        conn.execute(f"DELETE FROM {table} WHERE source_id = ?", (source_id,))


def status(conn: sqlite3.Connection) -> dict:
    sources = rows(conn.execute("SELECT * FROM market_sources ORDER BY imported_at"))
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("market_awards", "market_bids", "market_suppliers")}
    by_cap = {r[0]: r[1] for r in conn.execute(
        "SELECT capability, COUNT(*) FROM market_awards GROUP BY capability ORDER BY 2 DESC")}
    return {"sources": sources, "counts": counts, "awards_by_capability": by_cap,
            "real_data_loaded": counts["market_awards"] > 0}
