"""Primary objective orchestrator: tender -> Procurement Restructuring Plan.

    1 tender documents (+ BOQ)      -> work items with provenance            components.py
    2 items                         -> capability components                 components.py
    3 components                    -> technical dependency graph            dependencies.py
    4 graph + market evidence       -> feasible structures, scored, ranked   packaging.py
    5 packages                      -> SME / supplier pools with evidence    matching.py
    6 shortlisted suppliers         -> cross-relationship screening          relationships.py
    7 everything                    -> plan with rationale, risks, caveats   (here)

The plan is decision support for the procurement authority. It states what *may* be separated,
what should stay integrated and why, which firms have published evidence of capability, and what
needs human review - never an award decision.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from ..db import fetch_all, fetch_one, get_artifact, put_artifact
from ..market.store import connect as market_connect
from ..market.store import market_available
from ..market.store import status as market_status
from .classifier import model_card as classifier_card
from .competition import model_card as competition_card
from .components import build_components, items_from_boq, items_from_documents, stated_estimate_cr
from .dependencies import build_dependency_graph
from .matching import MarketIndex
from .packaging import compare_structures
from .relationships import screen_relationships
from .taxonomy import LABELS

STAGE = "restructuring"
TENDER_DOC_KINDS = ("tender", "tender_annex", "scope", "specification")


def _default_countries() -> tuple[str, ...] | None:
    raw = os.environ.get("TS_MARKET_COUNTRIES", "")
    return tuple(c.strip() for c in raw.split(",") if c.strip()) or None


def tender_pages(conn: sqlite3.Connection, tender_id: str) -> list[tuple[str, int, str]]:
    docs = fetch_all(conn, "SELECT document_id FROM documents WHERE tender_id = ? AND vendor_id IS NULL AND kind IN (%s)"
                     " ORDER BY document_id" % ",".join("?" * len(TENDER_DOC_KINDS)), (tender_id, *TENDER_DOC_KINDS))
    pages = []
    for d in docs:
        for r in conn.execute("SELECT page, text FROM document_pages WHERE document_id = ? ORDER BY page", (d["document_id"],)):
            pages.append((d["document_id"], r["page"], r["text"]))
    return pages


def run_restructuring(conn: sqlite3.Connection, tender_id: str, *, weights: dict | None = None, params: dict | None = None,
                      countries: tuple[str, ...] | None = None, value_overrides: dict | None = None) -> dict:
    tender = fetch_one(conn, "SELECT * FROM tenders WHERE tender_id = ?", (tender_id,))
    if tender is None:
        raise LookupError(f"Unknown tender {tender_id}")
    pages = tender_pages(conn, tender_id)
    doc_items, doc_unassigned = items_from_documents(pages, title=tender["title"])
    boq = get_artifact(conn, tender_id, "boq")
    boq_items, boq_unassigned = items_from_boq(boq["rows"], boq["document_id"]) if boq else ([], [])
    # A BOQ is the authoritative list of work items; document text then only informs dependencies.
    items = boq_items if boq_items else doc_items

    estimate, estimate_src = (tender["estimated_value_cr"], {"basis": "tender record"}) if tender["estimated_value_cr"] else \
        stated_estimate_cr(pages)
    overrides = value_overrides if value_overrides is not None else (get_artifact(conn, tender_id, "component_values") or {})
    components = build_components(items, estimate, overrides)
    if estimate is None and components and all(c["value_basis"] in ("boq", "document") for c in components):
        # No overall estimate stated, but every component carries its own stated cost: report their sum.
        estimate = round(sum(c["value_inr_cr"] for c in components), 4)
        estimate_src = {"basis": "sum of item costs stated in the tender documents / BOQ"}
    if not components:
        raise ValueError("No scope items could be identified in the tender documents. Upload the Scope of Work / "
                         "Technical Specifications or a BOQ (CSV/XLSX).")
    dep = build_dependency_graph(components, pages)

    countries = countries if countries is not None else _default_countries()
    market_conn = market_connect() if market_available() else None
    try:
        idx = MarketIndex.load(market_conn, countries)
        market = market_status(market_conn) if market_conn else {"real_data_loaded": False, "sources": []}
        structures = compare_structures(components, dep, idx, weights, params)
        rec = structures["scenarios"]["B_recommended"]
        names, shortlisted = {}, []
        for pk in rec["packages"]:
            for s in pk["match"]["shortlist"][:10]:
                names[s["supplier_key"]] = s["name"]
                shortlisted.append(s["supplier_key"])
        relationships = screen_relationships(market_conn, shortlisted, names)
    finally:
        if market_conn is not None:
            market_conn.close()

    by_id = {c["component_id"]: c for c in components}
    plan = {
        "tender_id": tender_id,
        "tender_title": tender["title"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "estimated_value_inr_cr": estimate,
        "estimate_source": estimate_src,
        "components": [{k: v for k, v in c.items() if k != "items"} | {"items": c["items"][:25]} for c in components],
        "unassigned_items": (doc_unassigned + boq_unassigned)[:40],
        "dependency_graph": dep,
        "structures": structures,
        "relationships": relationships,
        "recommendation": _narrative(by_id, dep, structures, relationships),
        "data_quality": _data_quality(components, market, countries, idx),
        "market_scope": {"countries": list(countries) if countries else "all loaded datasets",
                         "awards_in_scope": idx.total_awards, "sources": [s["source_id"] for s in market.get("sources", [])]},
        "models": {"capability_classifier": _card_summary(classifier_card()),
                   "competition_model": _card_summary(competition_card())},
    }
    put_artifact(conn, tender_id, STAGE, plan, plan["generated_at"])
    return plan


def _card_summary(card: dict | None) -> dict | None:
    if not card:
        return None
    return {"trained_at": card["trained_at"], "algorithm": card["algorithm"],
            "training_data": [{k: d.get(k) for k in ("name", "rows", "origin")} for d in card["training_data"]],
            "metrics": {k: v for k, v in card["metrics"].items() if k != "per_class_f1"}, "limitations": card["limitations"]}


def _cap_names(pkg: dict) -> str:
    return " + ".join(LABELS.get(c, c) for c in pkg["capabilities"])


def _narrative(by_id: dict, dep: dict, structures: dict, rel: dict) -> dict:
    rec, cur = structures["scenarios"]["B_recommended"], structures["scenarios"]["A_integrated"]
    keep_together = []
    for group in dep["strong_groups"]:
        caps = [by_id[c]["label"] for c in group]
        reasons = [e for e in dep["edges"] if e["strength"] == "strong" and e["source"] in group and e["target"] in group]
        keep_together.append({"components": group, "labels": caps,
                              "why": sorted({e["prior_rationale"] for e in reasons}),
                              "evidence": [q for e in reasons for q in e["text_evidence"]][:3]})
    packages = []
    for i, pk in enumerate(rec["packages"], start=1):
        pool = pk["match"]["pool"]
        packages.append({
            "package": f"P{i}", "components": pk["components"], "scope": _cap_names(pk),
            "value_inr_cr": pk["value_inr_cr"], "required_turnover_cr": pk["required_turnover_cr"],
            "sme_size_accessible": pk["sme_size_accessible"],
            "suppliers_with_full_capability_evidence": pk["capable_pool"],
            "of_which_meet_similar_work_scale": pool.get("POTENTIALLY_SUITABLE", 0),
            "sme_candidates": pk["sme_capable_pool"],
            "expected_bidders_indicator": pk["competition"]["expected_bidders"],
        })
    separated = rec["n_packages"] > 1
    headline = (f"Consider {rec['n_packages']} packages instead of one contract." if separated and structures["recommendation_differs_from_current"]
                else "Keep the procurement as one integrated contract: splitting does not improve procurement value "
                     "under the stated weights.")
    return {
        "headline": headline,
        "recommended_structure": rec["summary"], "current_structure": cur["summary"] if cur else None,
        "score_recommended": rec["score"], "score_current": cur["score"] if cur else None,
        "metrics_recommended": rec["metrics"], "metrics_current": cur["metrics"] if cur else None,
        "packages": packages,
        "keep_integrated": keep_together,
        "cut_interfaces_to_manage": rec["cut_dependencies"],
        "robustness": structures["sensitivity"],
        "relationships_requiring_review": rel["requires_review"],
        "decision_note": "Decision support only. The procurement authority decides the structure, verifies supplier "
                         "evidence and MSME status, and reviews any flagged relationships.",
    }


def _data_quality(components: list[dict], market: dict, countries, idx: MarketIndex) -> list[dict]:
    out = []
    assumed = [c["component_id"] for c in components if c["value_basis"] == "assumed_item_share"]
    unknown = [c["component_id"] for c in components if c["value_basis"] == "unknown"]
    if assumed:
        out.append({"level": "WARNING", "issue": "Component values are assumed from the share of scope items",
                    "components": assumed, "fix": "Upload the BOQ or enter values from the BOQ abstract"})
    if unknown:
        out.append({"level": "WARNING", "issue": "Component values unknown", "components": unknown,
                    "fix": "Upload the BOQ, or enter the tender's estimated value"})
    low = [c["component_id"] for c in components if c["mean_confidence"] < 0.5]
    if low:
        out.append({"level": "INFO", "issue": "Low-confidence capability classification", "components": low,
                    "fix": "Check the listed source items"})
    if not market.get("real_data_loaded"):
        out.append({"level": "WARNING", "issue": "No market (award) data loaded - supplier pools are empty",
                    "fix": "Run scripts/fetch_real_data.py and scripts/build_market.py"})
    elif idx.total_awards == 0:
        out.append({"level": "WARNING", "issue": f"No award records for market scope {countries}",
                    "fix": "Load awards for this country or widen TS_MARKET_COUNTRIES"})
    out.append({"level": "INFO", "issue": "MSME status shown as a size proxy unless Udyam evidence was imported",
                "fix": "Import verified Udyam records via POST /api/market/udyam"})
    return out


def load_plan(conn: sqlite3.Connection, tender_id: str) -> dict | None:
    return get_artifact(conn, tender_id, STAGE)
