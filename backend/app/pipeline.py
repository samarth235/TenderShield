"""End-to-end analysis workflow: runs Stages 1-10 in order and records per-stage timings."""

from __future__ import annotations

import time
from typing import Callable

from .compliance.engine import run_compliance
from .db import session
from .entities.resolution import run_entity_resolution
from .evidence import audit
from .graph.builder import run_graph_stage
from .ingestion.facts import ingest_vendor_facts
from .intelligence.behaviour import run_behaviour
from .intelligence.similarity import run_similarity
from .nlp.extract import extract_rulebook
from .reasoning.engine import generate_findings

STAGES = [
    "extract_rules",
    "ingest_evidence",
    "compliance",
    "entity_resolution",
    "document_similarity",
    "relationship_graph",
    "behaviour_analysis",
    "reasoning",
]


def _stage_summary(name: str, result: dict) -> dict:
    if name == "extract_rules":
        return {k: result[k] for k in ("method", "clauses_analysed", "rules_extracted", "mandatory_rules", "warnings")}
    if name == "ingest_evidence":
        return {"facts_extracted": result["facts_extracted"]}
    if name == "compliance":
        return {k: result[k] for k in ("evaluations", "counts")}
    if name == "entity_resolution":
        return result["summary"]
    if name == "document_similarity":
        top = result["pairs"][0] if result["pairs"] else None
        return {"backend": result["backend"], "pairs": len(result["pairs"]), "baseline": result["baseline"],
                "most_similar": top and {"vendors": top["vendors"], "similarity": top["document_similarity"]}}
    if name == "relationship_graph":
        return {k: result[k] for k in ("full_graph", "corporate_clusters")}
    if name == "behaviour_analysis":
        return {"historical_tenders": result["historical_tenders"], "model": result["model"]}
    if name == "reasoning":
        return {k: result[k] for k in ("findings", "by_category", "escalated_signals")}
    return {}


def run_analysis(tender_id: str, method: str | None = None, actor: str = "system") -> dict:
    steps: dict[str, Callable] = {
        "extract_rules": lambda c: extract_rulebook(c, tender_id, method),
        "ingest_evidence": lambda c: ingest_vendor_facts(c, tender_id),
        "compliance": lambda c: run_compliance(c, tender_id),
        "entity_resolution": lambda c: run_entity_resolution(c, tender_id),
        "document_similarity": lambda c: run_similarity(c, tender_id),
        "relationship_graph": lambda c: run_graph_stage(c, tender_id),
        "behaviour_analysis": lambda c: run_behaviour(c, tender_id),
        "reasoning": lambda c: generate_findings(c, tender_id),
    }
    report = {"tender_id": tender_id, "stages": []}
    started = time.perf_counter()
    with session() as conn:
        if not conn.execute("SELECT 1 FROM tenders WHERE tender_id = ?", (tender_id,)).fetchone():
            raise LookupError(f"Unknown tender {tender_id}")
        for name in STAGES:
            t0 = time.perf_counter()
            result = steps[name](conn)
            report["stages"].append({"stage": name, "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                                     "summary": _stage_summary(name, result)})
        report["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        audit.append(conn, tender_id, "ANALYSIS_RUN", actor,
                     {"stages": [s["stage"] for s in report["stages"]],
                      "findings": report["stages"][-1]["summary"]["findings"]})
    return report
