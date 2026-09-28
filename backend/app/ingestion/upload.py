"""Exploration Mode: ingest an evaluator-supplied tender PDF plus bidder data (JSON or CSV)."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import uuid
from pathlib import Path

from ..config import get_settings
from ..db import dumps
from ..nlp.rulebook import METRICS
from .pdf_text import register_document

UPLOADED_EXCERPT = "Uploaded structured data"
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def create_tender_from_pdf(conn: sqlite3.Connection, content: bytes, filename: str, tender_id: str | None,
                           title: str | None, department: str | None, bid_deadline: str | None) -> dict:
    if not content.startswith(b"%PDF"):
        raise ValueError("Uploaded file is not a PDF")
    tender_id = tender_id or f"UP-{uuid.uuid4().hex[:8].upper()}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", tender_id):
        raise ValueError("tender_id may contain only letters, digits, '-' and '_'")
    if conn.execute("SELECT 1 FROM tenders WHERE tender_id = ?", (tender_id,)).fetchone():
        raise ValueError(f"Tender {tender_id} already exists")
    folder = get_settings().documents_dir / tender_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (SAFE_NAME.sub("_", Path(filename or "tender.pdf").name) or "tender.pdf")
    path.write_bytes(content)
    conn.execute(
        "INSERT INTO tenders (tender_id, title, department, estimated_value_cr, published_on, bid_deadline, status,"
        " is_current, source, meta) VALUES (?, ?, ?, NULL, NULL, ?, 'UNDER_EVALUATION', 1, 'upload', '{}')",
        (tender_id, title or path.stem, department, bid_deadline),
    )
    doc = register_document(conn, document_id=f"DOC-{tender_id}-TENDER", tender_id=tender_id, vendor_id=None,
                            kind="tender", path=path)
    return {"tender_id": tender_id, "document": doc}


def _coerce(metric: str, value):
    if value is None or value == "":
        return None
    kind = METRICS[metric]["type"]
    if kind == "number":
        return float(value)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y")
    return str(value)


def add_bidders(conn: sqlite3.Connection, tender_id: str, bidders: list[dict]) -> dict:
    if not conn.execute("SELECT 1 FROM tenders WHERE tender_id = ?", (tender_id,)).fetchone():
        raise LookupError(f"Unknown tender {tender_id}")
    added = []
    for b in bidders:
        vendor_id = b.get("vendor_id") or f"U{uuid.uuid4().hex[:6].upper()}"
        if not conn.execute("SELECT 1 FROM vendors WHERE vendor_id = ?", (vendor_id,)).fetchone():
            conn.execute(
                "INSERT INTO vendors (vendor_id, alias, name, gstin, pan, registered_address, phone, email, incorporated,"
                " msme, directors, meta) VALUES (?, NULL, ?, ?, NULL, ?, ?, ?, NULL, 0, ?, ?)",
                (vendor_id, b["name"], b.get("gstin"), b.get("registered_address"), b.get("phone"), b.get("email"),
                 dumps(b.get("directors") or []), dumps({"source": "upload",
                                                         "directors_available": bool(b.get("directors"))})),
            )
        conn.execute(
            "INSERT INTO bids (tender_id, vendor_id, bidder_name, bidder_gstin, amount_cr, submitted_at, outcome, rank)"
            " VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL)",
            (tender_id, vendor_id, b["name"], b.get("gstin"), b.get("amount_cr"), b.get("submitted_at")),
        )
        facts = dict(b.get("facts") or {})
        if b.get("submitted_at"):
            facts.setdefault("submitted_at", b["submitted_at"])
        unknown = sorted(set(facts) - set(METRICS))
        for metric, value in facts.items():
            if metric not in METRICS:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO vendor_facts (tender_id, vendor_id, metric, value, document_id, page, excerpt)"
                " VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (tender_id, vendor_id, metric, dumps(_coerce(metric, value)), UPLOADED_EXCERPT),
            )
        added.append({"vendor_id": vendor_id, "name": b["name"], "facts": len(facts) - len(unknown),
                      "ignored_fields": unknown})
    return {"tender_id": tender_id, "bidders": added}


def parse_bidders_csv(text: str) -> list[dict]:
    """Columns: name, vendor_id, gstin, amount_cr, submitted_at, registered_address, plus any metric names."""
    rows = []
    for raw in csv.DictReader(io.StringIO(text)):
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
        if not row.get("name"):
            continue
        rows.append({
            "vendor_id": row.get("vendor_id") or None,
            "name": row["name"],
            "gstin": row.get("gstin") or None,
            "registered_address": row.get("registered_address") or None,
            "amount_cr": float(row["amount_cr"]) if row.get("amount_cr") else None,
            "submitted_at": row.get("submitted_at") or None,
            "facts": {k: v for k, v in row.items() if k in METRICS and v not in (None, "")},
        })
    return rows
