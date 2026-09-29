"""Deterministic synthetic dataset for the demonstration tender (Demo Mode).

Produces a registry of 180 contractors, 480 historical tenders with five years of award
records (``market.py`` / ``history.py``), the current tender TN-2026-014 with six bidders,
and the full PDF document package.
"""

from __future__ import annotations

import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..db import dumps, put_artifact, reset_db, session
from ..ingestion.pdf_text import register_document
from . import documents as docs
from .history import build_history
from .market import build_registry, gstin, registry_meta
from .scenario import BIDDER_FACTS, BIDDERS, CURRENT_BIDS, DEMO_TENDER, DEMO_TENDER_ID


def _gstin(vendor: dict) -> str:
    return gstin(vendor["state_code"], vendor["pan"])


def load_demo() -> dict:
    """Reset the database and load the complete demonstration dataset."""
    settings = get_settings()
    rng = random.Random(settings.random_seed)
    reset_db()
    tender_dir = settings.documents_dir / DEMO_TENDER_ID
    if tender_dir.exists():
        shutil.rmtree(tender_dir)
    tender_dir.mkdir(parents=True)

    vendors = build_registry(rng)
    history, hist_bids, planted = build_history(rng, vendors)
    by_id = {v["vendor_id"]: v for v in vendors}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with session() as conn:
        for v in vendors:
            conn.execute(
                "INSERT INTO vendors (vendor_id, alias, name, gstin, pan, registered_address, phone, email,"
                " incorporated, msme, directors, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    v["vendor_id"], v["alias"], v["name"], _gstin(v), v["pan"], v["registered_address"], v["phone"],
                    v["email"], v["incorporated"], int(v["msme"]), dumps(v["directors"]),
                    dumps({"source": v["source"], "directors_available": bool(v["directors"]), **registry_meta(v)}),
                ),
            )
        for t in history:
            conn.execute(
                "INSERT INTO tenders (tender_id, title, department, estimated_value_cr, published_on, bid_deadline,"
                " status, is_current, source, meta) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'history', ?)",
                (t["tender_id"], t["title"], t["department"], t["estimated_value_cr"], t["published_on"],
                 t["bid_deadline"], t["status"], dumps(t["meta"])),
            )
        t = DEMO_TENDER
        conn.execute(
            "INSERT INTO tenders (tender_id, title, department, estimated_value_cr, published_on, bid_deadline,"
            " status, is_current, source, meta) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'demo', ?)",
            (t["tender_id"], t["title"], t["department"], t["estimated_value_cr"], t["published_on"],
             t["bid_deadline"], t["status"], dumps({"demo": True})),
        )
        truth: dict[str, str | None] = {}
        for b in hist_bids:
            cur = conn.execute(
                "INSERT INTO bids (tender_id, vendor_id, bidder_name, bidder_gstin, amount_cr, submitted_at, outcome, rank)"
                " VALUES (?, NULL, ?, ?, ?, ?, ?, ?)",
                (b["tender_id"], b["bidder_name"], b["bidder_gstin"], b["amount_cr"], b["submitted_at"], b["outcome"], b["rank"]),
            )
            truth[str(cur.lastrowid)] = b["truth_vendor_id"]
        for vid, (amount, submitted) in CURRENT_BIDS.items():
            conn.execute(
                "INSERT INTO bids (tender_id, vendor_id, bidder_name, bidder_gstin, amount_cr, submitted_at, outcome, rank)"
                " VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL)",
                (DEMO_TENDER_ID, vid, by_id[vid]["name"], _gstin(by_id[vid]), amount, submitted),
            )
        put_artifact(conn, DEMO_TENDER_ID, "demo_ground_truth", {"bid_vendor": truth, "planted_tenders": planted}, now)

        registered = render_documents(conn, tender_dir, settings.random_seed)

    return {
        "tender_id": DEMO_TENDER_ID,
        "title": DEMO_TENDER["title"],
        "bidders": len(BIDDERS),
        "tender_documents": len(registered),
        "historical_tenders": len(history),
        "registered_vendors": len(vendors),
        "historical_bid_records": len(hist_bids),
        "documents": registered,
    }


def render_documents(conn, tender_dir: Path, seed: int, overrides: dict | None = None) -> list[dict]:
    """Render and register every PDF of the demo tender package.

    ``overrides`` maps vendor_id -> {fact: value} and is used by the tamper demo.
    """
    overrides = overrides or {}
    registered = []
    path = tender_dir / f"Tender_{DEMO_TENDER_ID}.pdf"
    docs.write_pdf(path, f"Tender Document {DEMO_TENDER_ID}", docs.tender_pages())
    registered.append(register_document(conn, document_id="DOC-TENDER", tender_id=DEMO_TENDER_ID,
                                        vendor_id=None, kind="tender", path=path))

    sections = docs.technical_sections(BIDDERS, seed)
    log_rows = []
    for vendor in BIDDERS:
        vid = vendor["vendor_id"]
        facts = {**BIDDER_FACTS[vid], **overrides.get(vid, {})}
        letter = vendor["alias"].split()[-1]
        tech = tender_dir / f"TechnicalBid_{letter}.pdf"
        docs.write_pdf(tech, f"Technical Proposal - {vendor['name']}", docs.technical_pages(vendor, facts, sections[vid], seed))
        registered.append(register_document(conn, document_id=f"DOC-{vid}-TECH", tender_id=DEMO_TENDER_ID,
                                            vendor_id=vid, kind="technical_bid", path=tech))
        comp = tender_dir / f"ComplianceDocs_{letter}.pdf"
        docs.write_pdf(comp, f"Compliance Documents - {vendor['name']}", docs.compliance_pages(vendor, facts))
        registered.append(register_document(conn, document_id=f"DOC-{vid}-COMP", tender_id=DEMO_TENDER_ID,
                                            vendor_id=vid, kind="compliance", path=comp))
        amount, submitted = CURRENT_BIDS[vid]
        log_rows.append((vid, vendor["name"], submitted, amount))

    log = tender_dir / f"BidSubmissionLog_{DEMO_TENDER_ID}.pdf"
    docs.write_pdf(log, f"Bid Submission Log {DEMO_TENDER_ID}", docs.submission_log_pages(log_rows))
    registered.append(register_document(conn, document_id="DOC-SUBMISSION-LOG", tender_id=DEMO_TENDER_ID,
                                        vendor_id=None, kind="submission_log", path=log))
    return registered
