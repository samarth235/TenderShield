"""Stage 2/3 orchestration: tender PDF -> clauses -> candidate rules -> normalised Tender Rulebook."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from ..config import get_settings
from ..db import dumps, fetch_one, put_artifact
from ..ingestion.pdf_text import document_pages
from .llm_extractor import extract_candidates_llm, llm_available
from .pattern_extractor import extract_candidates
from .rulebook import METRICS, Condition, Extraction, Rule, RuleSource, describe_condition, describe_requirement
from .segmentation import Clause, segment_clauses

log = logging.getLogger(__name__)


def _clause_order(clause_id: str) -> tuple[int, ...]:
    return tuple(int(p) for p in clause_id.split("."))


def normalise(
    candidates: list[dict], clauses: list[Clause], document: dict, method: str, model: str | None
) -> list[Rule]:
    by_clause = {c.clause_id: c for c in clauses}
    order = {m: i for i, m in enumerate(METRICS)}
    candidates = [c for c in candidates if c["clause_id"] in by_clause]
    candidates.sort(key=lambda c: (_clause_order(c["clause_id"]), order.get(c["metric"], 99)))

    rules: list[Rule] = []
    seen: set[tuple[str, str]] = set()
    for cand in candidates:
        key = (cand["clause_id"], cand["metric"])
        if key in seen:
            continue
        seen.add(key)
        clause = by_clause[cand["clause_id"]]
        metric, operator, threshold = cand["metric"], cand["operator"], cand["threshold"]
        notes: list[str] = []
        info = METRICS.get(metric)
        if info is None:
            notes.append("Requirement could not be mapped to a machine-checkable metric; manual review needed.")
            category, unit = "Unmapped", ""
        else:
            category, unit = info["category"], info["unit"]
            if info["type"] == "number" and operator in ("gte", "gt", "lte", "eq"):
                try:
                    threshold = float(threshold)
                except (TypeError, ValueError):
                    notes.append("Threshold missing or non-numeric; rule will evaluate to UNKNOWN.")
                    threshold = None
        describable = info is not None and (
            threshold is not None or operator in ("is_true", "is_false", "valid_on_submission")
        )
        requirement = describe_requirement(metric, operator, threshold) if describable else clause.text
        applies_if = Condition(**cand["applies_if"]) if cand.get("applies_if") else None
        if applies_if is not None:
            label = METRICS.get(applies_if.metric, {}).get("label", applies_if.metric)
            requirement += f" (applies only if: {label.lower()})"
        rules.append(
            Rule(
                rule_id=f"R{len(rules) + 1:02d}",
                category=category,
                requirement=requirement,
                metric=metric,
                operator=operator,
                threshold=threshold,
                unit=unit,
                mandatory=bool(cand["mandatory"]),
                applies_if=applies_if,
                condition=describe_condition(metric, operator, threshold),
                clause_text=clause.text,
                source=RuleSource(
                    document_id=document["document_id"], filename=document["filename"], page=clause.page,
                    clause=clause.clause_id,
                ),
                extraction=Extraction(method=method, confidence=float(cand.get("confidence", 0.8)), model=model),
                notes=notes,
            )
        )
    return rules


def extract_rulebook(conn: sqlite3.Connection, tender_id: str, method: str | None = None) -> dict:
    settings = get_settings()
    requested = (method or settings.extractor).lower()
    document = fetch_one(
        conn, "SELECT * FROM documents WHERE tender_id = ? AND kind = 'tender' ORDER BY document_id LIMIT 1", (tender_id,)
    )
    if document is None:
        raise LookupError(f"No tender document registered for {tender_id}")
    clauses = segment_clauses(document_pages(conn, document["document_id"]))

    warnings: list[str] = []
    used, model = "pattern", None
    candidates: list[dict] | None = None
    if requested in ("llm", "auto"):
        # An explicit "llm" request always attempts the call (the SDK may find credentials in an
        # `ant auth login` profile); "auto" only does so when credentials are visibly configured.
        if requested == "llm" or llm_available():
            try:
                candidates, model = extract_candidates_llm(clauses)
                used = "llm"
            except Exception as exc:  # network, auth, refusal, truncation...
                log.warning("LLM extraction failed, falling back to pattern extractor: %s", exc)
                warnings.append(f"LLM extraction unavailable ({type(exc).__name__}: {exc}); used pattern extractor.")
    if candidates is None:
        candidates = extract_candidates(clauses)

    rules = normalise(candidates, clauses, document, used, model)
    conn.execute("DELETE FROM rules WHERE tender_id = ?", (tender_id,))
    conn.executemany(
        "INSERT INTO rules (tender_id, rule_id, body) VALUES (?, ?, ?)",
        [(tender_id, r.rule_id, dumps(r.model_dump())) for r in rules],
    )
    summary = {
        "tender_id": tender_id,
        "method": used,
        "model": model,
        "clauses_analysed": len(clauses),
        "rules_extracted": len(rules),
        "mandatory_rules": sum(r.mandatory for r in rules),
        "unmapped_rules": sum(r.metric not in METRICS for r in rules),
        "warnings": warnings,
        "clauses": [c.to_dict() for c in clauses],
    }
    put_artifact(conn, tender_id, "rule_extraction", summary, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {**summary, "rules": [r.model_dump() for r in rules]}


def load_rules(conn: sqlite3.Connection, tender_id: str) -> list[dict]:
    rows = conn.execute("SELECT body FROM rules WHERE tender_id = ? ORDER BY rule_id", (tender_id,)).fetchall()
    return [json.loads(r["body"]) for r in rows]
