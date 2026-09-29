"""Integrity demonstrations.

Scenario 1 - ``tamper_document``: alter a committed evidence file in place (outside the normal
workflow) so verification reports an integrity mismatch. ``restore`` puts the original back.

Scenario 2 - ``create_demo_version``: the bidder uploads a renewed compliance document as a new
version. Nothing historical changes; the system reports a new version for auditor review."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from ..config import get_settings
from ..db import fetch_one
from ..evidence import versions
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


# A renewal five months after bid submission: both ISO certificates renewed and the turnover
# restated with the next audited financial year. Certificate number and identity stay the same.
RENEWAL_CHANGES = {"iso9001_valid_until": "2029-06-30", "iso27001_valid_until": "2027-11-30",
                   "avg_annual_turnover_cr": 13.10}


def create_demo_version(conn: sqlite3.Connection, document_id: str | None = None) -> dict:
    document_id = document_id or DEFAULT_DOCUMENT
    doc = fetch_one(conn, "SELECT * FROM documents WHERE document_id = ?", (document_id,))
    if doc is None:
        raise LookupError(f"Unknown document {document_id}")
    vendor = next((v for v in BIDDERS if v["vendor_id"] == doc["vendor_id"]), None)
    if doc["kind"] != "compliance" or vendor is None:
        raise ValueError("The renewal demo applies to bidder compliance documents (e.g. DOC-V001-COMP).")
    facts = {**BIDDER_FACTS[vendor["vendor_id"]], **RENEWAL_CHANGES}
    with tempfile.TemporaryDirectory(dir=get_settings().data_dir) as tmp:
        path = Path(tmp) / doc["filename"]
        docs.write_pdf(path, f"Compliance Documents - {vendor['name']}", docs.compliance_pages(vendor, facts))
        content = path.read_bytes()
    return versions.create_version(conn, document_id, content, doc["filename"], f"{vendor['name']} (bidder upload)",
                                   note="Renewed ISO certificates and restated turnover", origin="demo_renewal")
