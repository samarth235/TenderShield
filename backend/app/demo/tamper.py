"""Tamper demonstration: alter a stored evidence file on disk (outside the normal workflow)
so that integrity verification detects the change. ``restore`` puts the original back."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from ..db import fetch_one
from . import documents as docs
from .scenario import BIDDER_FACTS, BIDDERS

DEFAULT_DOCUMENT = "DOC-V001-COMP"


def _backup(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".orig")


def tamper_document(conn: sqlite3.Connection, document_id: str | None = None) -> dict:
    document_id = document_id or DEFAULT_DOCUMENT
    doc = fetch_one(conn, "SELECT * FROM documents WHERE document_id = ?", (document_id,))
    if doc is None:
        raise LookupError(f"Unknown document {document_id}")
    path = Path(doc["path"])
    backup = _backup(path)
    if not backup.exists():
        shutil.copy2(path, backup)

    vendor = next((v for v in BIDDERS if v["vendor_id"] == doc["vendor_id"]), None)
    if doc["kind"] == "compliance" and vendor is not None:
        facts = dict(BIDDER_FACTS[vendor["vendor_id"]])
        original = facts["avg_annual_turnover_cr"]
        facts["avg_annual_turnover_cr"] = round(original + 9.0, 2)
        docs.write_pdf(path, f"Compliance Documents - {vendor['name']}", docs.compliance_pages(vendor, facts))
        change = (f"Average annual turnover altered from Rs. {original:.2f} crore to "
                  f"Rs. {facts['avg_annual_turnover_cr']:.2f} crore")
    else:
        with open(path, "ab") as fh:
            fh.write(b"\n% modified after evidence commitment\n")
        change = "Bytes appended to the stored file"
    return {"document_id": document_id, "filename": doc["filename"], "change": change,
            "hint": "Run integrity verification on the finalised snapshot to detect the mismatch."}


def restore_documents(conn: sqlite3.Connection, tender_id: str) -> dict:
    restored = []
    for row in conn.execute("SELECT document_id, path FROM documents WHERE tender_id = ?", (tender_id,)).fetchall():
        path = Path(row["path"])
        backup = _backup(path)
        if backup.exists():
            shutil.move(str(backup), path)
            restored.append(row["document_id"])
    return {"restored": restored}
