"""Assurance Dossier data (Stage 13).

Aggregates everything the dossier PDF needs into one JSON document. PDF rendering is
owned by the dossier/blockchain module; this endpoint is its single data source.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..compliance.engine import compliance_matrix
from ..db import fetch_all, fetch_one, get_artifact
from ..reasoning.engine import load_finding
from . import audit
from .bundle import document_manifest, list_snapshots


def dossier_data(conn: sqlite3.Connection, tender_id: str) -> dict:
    tender = fetch_one(conn, "SELECT * FROM tenders WHERE tender_id = ?", (tender_id,))
    if tender is None:
        raise LookupError(f"Unknown tender {tender_id}")
    matrix = compliance_matrix(conn, tender_id)
    bids = fetch_all(
        conn,
        "SELECT b.vendor_id, v.alias, v.name, b.amount_cr, b.submitted_at FROM bids b JOIN vendors v ON v.vendor_id = b.vendor_id"
        " WHERE b.tender_id = ? ORDER BY b.vendor_id",
        (tender_id,),
    )
    status = {v["vendor_id"]: v["status"] for v in matrix["vendors"]}
    finding_ids = [r["finding_id"] for r in fetch_all(conn, "SELECT finding_id FROM findings WHERE tender_id = ? "
                                                             "ORDER BY finding_id", (tender_id,))]
    findings = [load_finding(conn, fid) for fid in finding_ids]
    runs = fetch_all(conn, "SELECT * FROM counterfactual_runs WHERE finding_id IN "
                           "(SELECT finding_id FROM findings WHERE tender_id = ?) ORDER BY run_id", (tender_id,))
    entities = get_artifact(conn, tender_id, "entities") or {}
    bidder_ids = {b["vendor_id"] for b in bids}
    behaviour = get_artifact(conn, tender_id, "behaviour") or {}
    similarity = get_artifact(conn, tender_id, "similarity") or {}
    extraction = get_artifact(conn, tender_id, "rule_extraction") or {}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tender_summary": {k: tender[k] for k in ("tender_id", "title", "department", "estimated_value_cr",
                                                  "published_on", "bid_deadline", "status")},
        "rule_extraction": {k: extraction.get(k) for k in ("method", "model", "clauses_analysed", "rules_extracted",
                                                            "mandatory_rules", "warnings")},
        "bidder_summary": [{**b, "compliance_status": status.get(b["vendor_id"])} for b in bids],
        "compliance_matrix": matrix,
        "failed_requirements": [
            {"vendor_id": vid, "rule_id": rid, "reason": cell["reason"], "evidence": cell["evidence"]}
            for vid, cells in matrix["cells"].items() for rid, cell in cells.items()
            if cell["result"] == "FAIL" and cell["mandatory"]
        ],
        "investigation_signals": [f for f in findings if f["category"] == "INVESTIGATION_SIGNAL"],
        "compliance_findings": [f for f in findings if f["category"] == "COMPLIANCE"],
        "data_quality_warnings": [f for f in findings if f["category"] == "DATA_QUALITY"],
        "graph_relationships": [
            link for link in entities.get("shared_links", []) if set(link["vendors"]) <= bidder_ids
        ],
        "behaviour_analysis": {
            "model": behaviour.get("model"), "thresholds": behaviour.get("thresholds"),
            "pairs": [{k: v for k, v in p.items() if k != "history"} for p in behaviour.get("pairs", [])],
        },
        "document_similarity": {
            "backend": similarity.get("backend"), "baseline": similarity.get("baseline"),
            "pairs": [{k: p[k] for k in ("vendors", "document_similarity", "high_overlap_sections")}
                      for p in similarity.get("pairs", [])],
        },
        "counterfactual_analysis": runs,
        "auditor_dispositions": [e for e in audit.history(conn, tender_id) if e["action"] == "DISPOSITION"],
        "audit_trail": audit.history(conn, tender_id),
        "evidence_manifest": document_manifest(conn, tender_id),
        "snapshots": list_snapshots(conn, tender_id),
    }
