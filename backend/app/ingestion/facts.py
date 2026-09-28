"""Bidder evidence extraction: read declared values out of each bidder's compliance
documents and the portal submission log, keeping document + page + excerpt for every value."""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Callable

from ..db import dumps, fetch_all
from .pdf_text import document_pages

AMT = r"(?:Rs\.?|INR|₹)\s*(-?[\d,]+(?:\.\d+)?)\s*(crore|lakh)"


def _amount(unit: str) -> Callable[[re.Match], float]:
    def convert(m: re.Match) -> float:
        value = float(m.group(1).replace(",", ""))
        if m.group(2).lower() == unit:
            return value
        return value / 100 if unit == "crore" else value * 100

    return convert


def _int(m: re.Match) -> int:
    return int(m.group(1))


def _date_or_not_held(m: re.Match) -> str:
    return m.group(1) if m.group(1) else "NOT_HELD"


# metric -> (regex over a single line, converter)
FACT_PATTERNS: dict[str, tuple[str, Callable[[re.Match], Any]]] = {
    "avg_annual_turnover_cr": (r"Average Annual Turnover[^:]*:\s*" + AMT, _amount("crore")),
    "net_worth_cr": (r"Net Worth[^:]*:\s*" + AMT, _amount("crore")),
    "solvency_amount_cr": (r"Solvency Certificate Amount:\s*" + AMT, _amount("crore")),
    "years_in_operation": (r"Years in Operation[^:]*:\s*(\d+)", _int),
    "similar_projects_5y": (r"Similar Projects Completed[^:]*:\s*(\d+)", _int),
    "similar_projects_value_cr": (r"Aggregate Value of Similar Projects:\s*" + AMT, _amount("crore")),
    "technical_staff": (r"Technical Personnel on Payroll:\s*(\d+)", _int),
    "iso9001_valid_until": (r"ISO 9001\S*.*?Valid Until:\s*(\d{4}-\d{2}-\d{2})", lambda m: m.group(1)),
    "iso27001_valid_until": (r"ISO/IEC 27001 Certificate(?:\s*-\s*Valid Until:\s*(\d{4}-\d{2}-\d{2})|:\s*Not held)", _date_or_not_held),
    "gst_registered": (r"GST Registration:\s*(Registered|Not registered)", lambda m: m.group(1) == "Registered"),
    "pan_available": (r"PAN:\s*([A-Z]{5}\d{4}[A-Z]|Not furnished)", lambda m: m.group(1) != "Not furnished"),
    "blacklisted": (r"Blacklisting / Debarment Declaration:\s*(Not blacklisted|Blacklisted)", lambda m: m.group(1) == "Blacklisted"),
    "ownership_disclosure": (r"Ownership Disclosure:\s*(Submitted|Not submitted)", lambda m: m.group(1) == "Submitted"),
    "power_of_attorney": (r"Power of Attorney:\s*(Submitted|Not submitted)", lambda m: m.group(1) == "Submitted"),
    "claims_msme_exemption": (r"MSME Exemption Claimed:\s*(Yes|No)", lambda m: m.group(1) == "Yes"),
    "udyam_registered": (r"Udyam Registration:\s*(UDYAM-[\w-]+)", lambda m: True),
    "emd_amount_lakh": (r"Earnest Money Deposit:\s*" + AMT, _amount("lakh")),
    "bid_validity_days": (r"Bid Validity:\s*(\d+)\s*days", _int),
}

LOG_LINE = re.compile(r"^(V\d{3})\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|\s*" + AMT)
DIRECTOR_LINE = re.compile(r"Director:\s*(.+?)\s*\(DIN\s*(\d{8})\)")


def extract_facts_from_pages(pages: list[tuple[int, str]]) -> dict[str, dict]:
    facts: dict[str, dict] = {}
    for page, text in pages:
        for line in text.splitlines():
            for metric, (pattern, convert) in FACT_PATTERNS.items():
                if metric in facts:
                    continue
                match = re.search(pattern, line)
                if match:
                    facts[metric] = {"value": convert(match), "page": page, "excerpt": line.strip()}
    return facts


def extract_declared_directors(pages: list[tuple[int, str]]) -> list[dict]:
    out = []
    for page, text in pages:
        for match in DIRECTOR_LINE.finditer(text):
            out.append({"name": match.group(1), "din": match.group(2), "page": page})
    return out


def ingest_vendor_facts(conn: sqlite3.Connection, tender_id: str) -> dict:
    """Populate vendor_facts for every bidder of the tender. Returns coverage statistics."""
    # Facts supplied as structured uploads (document_id NULL) are kept; document-derived facts are re-extracted.
    conn.execute("DELETE FROM vendor_facts WHERE tender_id = ? AND document_id IS NOT NULL", (tender_id,))
    docs = fetch_all(conn, "SELECT * FROM documents WHERE tender_id = ?", (tender_id,))
    rows: list[tuple] = []
    per_vendor: dict[str, int] = {}
    declared_directors: dict[str, list[dict]] = {}

    for doc in docs:
        if doc["kind"] != "compliance" or not doc["vendor_id"]:
            continue
        pages = document_pages(conn, doc["document_id"])
        facts = extract_facts_from_pages(pages)
        declared_directors[doc["vendor_id"]] = extract_declared_directors(pages)
        per_vendor[doc["vendor_id"]] = len(facts)
        for metric, fact in facts.items():
            rows.append((tender_id, doc["vendor_id"], metric, dumps(fact["value"]), doc["document_id"], fact["page"], fact["excerpt"]))

    log_doc = next((d for d in docs if d["kind"] == "submission_log"), None)
    if log_doc:
        for page, text in document_pages(conn, log_doc["document_id"]):
            for line in text.splitlines():
                match = LOG_LINE.match(line.strip())
                if match:
                    rows.append((tender_id, match.group(1), "submitted_at", dumps(match.group(3)),
                                 log_doc["document_id"], page, line.strip()))
    else:
        # No portal log document: fall back to the structured bid records.
        for bid in fetch_all(conn, "SELECT * FROM bids WHERE tender_id = ? AND vendor_id IS NOT NULL"
                             " AND submitted_at IS NOT NULL", (tender_id,)):
            rows.append((tender_id, bid["vendor_id"], "submitted_at", dumps(bid["submitted_at"]), None, None,
                         "e-procurement bid record"))

    conn.executemany(
        "INSERT OR REPLACE INTO vendor_facts (tender_id, vendor_id, metric, value, document_id, page, excerpt)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return {"facts_extracted": len(rows), "facts_per_vendor": per_vendor, "declared_directors": declared_directors}


def load_facts(conn: sqlite3.Connection, tender_id: str) -> dict[str, dict[str, dict]]:
    """vendor_id -> metric -> {value, document_id, page, excerpt, filename}."""
    rows = fetch_all(
        conn,
        "SELECT f.*, d.filename FROM vendor_facts f LEFT JOIN documents d ON d.document_id = f.document_id"
        " WHERE f.tender_id = ?",
        (tender_id,),
    )
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        out.setdefault(r["vendor_id"], {})[r["metric"]] = {
            "value": r["value"], "document_id": r["document_id"], "filename": r["filename"],
            "page": r["page"], "excerpt": r["excerpt"],
        }
    return out
