"""SQLite persistence for tenders, vendors, evidence, findings and the audit trail.

The schema is intentionally small: structured records live in typed columns, and
stage outputs (graph, similarity, behaviour...) are stored as JSON artifacts so the
analysis pipeline can evolve without migrations during the hackathon.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenders (
    tender_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT,
    estimated_value_cr REAL,
    published_on TEXT,
    bid_deadline TEXT,
    status TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id TEXT PRIMARY KEY,
    alias TEXT,
    name TEXT NOT NULL,
    gstin TEXT,
    pan TEXT,
    registered_address TEXT,
    phone TEXT,
    email TEXT,
    incorporated TEXT,
    msme INTEGER NOT NULL DEFAULT 0,
    directors TEXT,
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS bids (
    bid_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id TEXT NOT NULL,
    vendor_id TEXT,
    bidder_name TEXT NOT NULL,
    bidder_gstin TEXT,
    amount_cr REAL,
    submitted_at TEXT,
    outcome TEXT NOT NULL,
    rank INTEGER
);
CREATE INDEX IF NOT EXISTS idx_bids_tender ON bids(tender_id);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    tender_id TEXT NOT NULL,
    vendor_id TEXT,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS document_pages (
    document_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, page)
);
CREATE TABLE IF NOT EXISTS vendor_facts (
    tender_id TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value TEXT NOT NULL,
    document_id TEXT,
    page INTEGER,
    excerpt TEXT,
    PRIMARY KEY (tender_id, vendor_id, metric)
);
CREATE TABLE IF NOT EXISTS rules (
    tender_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tender_id, rule_id)
);
CREATE TABLE IF NOT EXISTS compliance (
    tender_id TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    result TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tender_id, vendor_id, rule_id)
);
CREATE TABLE IF NOT EXISTS artifacts (
    tender_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tender_id, stage)
);
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    tender_id TEXT NOT NULL,
    category TEXT NOT NULL,
    level TEXT NOT NULL,
    status TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counterfactual_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL,
    removed TEXT NOT NULL,
    run_result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id TEXT NOT NULL,
    finding_id TEXT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    tender_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    bundle TEXT NOT NULL,
    bundle_hash TEXT NOT NULL,
    audit_head INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    tender_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    parent_version_id TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    anchor TEXT,
    UNIQUE (document_id, version)
);
CREATE TABLE IF NOT EXISTS document_version_pages (
    version_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (version_id, page)
);
"""

JSON_COLUMNS = {"meta", "directors", "value", "body", "removed", "run_result", "payload", "bundle", "anchor"}


def _db_path() -> Path:
    return get_settings().db_path


def connect() -> sqlite3.Connection:
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


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    path = _db_path()
    if path.exists():
        path.unlink()
    init_db()


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
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
