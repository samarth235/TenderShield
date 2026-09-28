"""Deterministic Compliance Engine (Stage 4).

Every bidder is evaluated against every rule. Each evaluation records the expected
condition, the actual value, the evidence source and a plain-language reason. Missing
evidence yields UNKNOWN - never FAIL - because absent data is not proof of wrongdoing.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from ..db import dumps, fetch_all, put_artifact
from ..ingestion.facts import load_facts
from ..nlp.extract import load_rules
from ..nlp.rulebook import METRICS, OPERATOR_SYMBOL

PASS, FAIL, UNKNOWN, NOT_APPLICABLE = "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"


def _evidence(fact: dict | None, role: str = "primary") -> list[dict]:
    if not fact:
        return []
    return [{
        "role": role, "document_id": fact.get("document_id"), "filename": fact.get("filename"),
        "page": fact.get("page"), "excerpt": fact.get("excerpt"),
    }]


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _compare(operator: str, actual: float, threshold: float) -> bool:
    return {
        "gte": actual >= threshold, "gt": actual > threshold, "lte": actual <= threshold, "eq": actual == threshold,
    }[operator]


def _fmt(metric: str, value: Any) -> str:
    unit = METRICS.get(metric, {}).get("unit", "")
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and unit in ("crore", "lakh"):
        return f"Rs. {value:g} {unit}"
    if isinstance(value, (int, float)):
        return f"{value:g} {unit}".strip()
    return str(value)


def evaluate_rule(rule: dict, facts: dict[str, dict], deadline: str | None) -> dict:
    metric, operator, threshold = rule["metric"], rule["operator"], rule["threshold"]
    expected = rule["condition"] or f"{metric} {OPERATOR_SYMBOL.get(operator, operator)} {threshold}"
    base = {"rule_id": rule["rule_id"], "expected": expected, "mandatory": rule["mandatory"]}

    def result(status: str, reason: str, actual: Any = None, evidence: list[dict] | None = None) -> dict:
        return {**base, "result": status, "actual": actual, "reason": reason, "evidence": evidence or []}

    applies_if = rule.get("applies_if")
    if applies_if:
        cond_fact = facts.get(applies_if["metric"])
        if cond_fact is None:
            return result(UNKNOWN, f"Applicability could not be determined: no evidence for {applies_if['metric']}.")
        applies = bool(cond_fact["value"]) if applies_if["operator"] == "is_true" else not bool(cond_fact["value"])
        if not applies:
            return result(NOT_APPLICABLE, "Rule does not apply to this bidder "
                          f"({METRICS.get(applies_if['metric'], {}).get('label', applies_if['metric'])}: "
                          f"{_fmt(applies_if['metric'], cond_fact['value'])}).",
                          evidence=_evidence(cond_fact, "applicability"))

    if metric not in METRICS:
        return result(UNKNOWN, "Requirement is not machine-checkable; manual verification required.")

    fact = facts.get(metric)
    if fact is None or fact["value"] is None:
        label = METRICS[metric]["label"]
        return result(UNKNOWN, f"Insufficient data: no evidence of '{label}' found in the submitted documents.")

    actual = fact["value"]
    evidence = _evidence(fact)

    if operator in ("gte", "gt", "lte", "eq"):
        if threshold is None:
            return result(UNKNOWN, "Rule threshold could not be determined from the tender clause.", actual, evidence)
        ok = _compare(operator, float(actual), float(threshold))
        reason = (f"{_fmt(metric, actual)} {'satisfies' if ok else 'does not satisfy'} "
                  f"{OPERATOR_SYMBOL[operator]} {_fmt(metric, threshold)}.")
        return result(PASS if ok else FAIL, reason, actual, evidence)

    if operator in ("is_true", "is_false"):
        wanted = operator == "is_true"
        ok = bool(actual) is wanted
        label = METRICS[metric]["label"]
        reason = f"{label}: {_fmt(metric, actual)} (required: {'yes' if wanted else 'no'})."
        return result(PASS if ok else FAIL, reason, actual, evidence)

    if operator == "valid_on_submission":
        if actual == "NOT_HELD":
            return result(FAIL, "Certificate not held.", actual, evidence)
        submitted = facts.get("submitted_at")
        reference: date
        if submitted:
            reference = _parse_dt(submitted["value"]).date()
            evidence += _evidence(submitted, "reference_date")
            ref_label = "bid submission date"
        elif deadline:
            reference = _parse_dt(deadline).date()
            ref_label = "bid deadline (submission time unavailable)"
        else:
            return result(UNKNOWN, "Reference date for validity check unavailable.", actual, evidence)
        expiry = date.fromisoformat(actual)
        ok = expiry >= reference
        reason = (f"Certificate valid until {expiry.isoformat()}; {ref_label} {reference.isoformat()} - "
                  + ("valid on that date." if ok else "certificate had expired before that date."))
        return result(PASS if ok else FAIL, reason, actual, evidence)

    if operator == "submitted_before":
        ok = _parse_dt(actual) <= _parse_dt(str(threshold))
        reason = f"Submitted at {actual}; deadline {threshold} - " + ("on time." if ok else "late submission.")
        return result(PASS if ok else FAIL, reason, actual, evidence)

    return result(UNKNOWN, f"Unsupported operator {operator}.")


def overall_status(evaluations: list[dict]) -> str:
    mandatory = [e for e in evaluations if e["mandatory"]]
    if any(e["result"] == FAIL for e in mandatory):
        return "NOT_QUALIFIED"
    if any(e["result"] == UNKNOWN for e in mandatory):
        return "INCOMPLETE_EVIDENCE"
    return "QUALIFIED"


def run_compliance(conn: sqlite3.Connection, tender_id: str) -> dict:
    rules = load_rules(conn, tender_id)
    if not rules:
        raise LookupError("Rulebook is empty - extract rules first.")
    tender = conn.execute("SELECT bid_deadline FROM tenders WHERE tender_id = ?", (tender_id,)).fetchone()
    bidders = fetch_all(conn, "SELECT DISTINCT vendor_id FROM bids WHERE tender_id = ? AND vendor_id IS NOT NULL"
                        " ORDER BY vendor_id", (tender_id,))
    facts = load_facts(conn, tender_id)

    conn.execute("DELETE FROM compliance WHERE tender_id = ?", (tender_id,))
    counts = {PASS: 0, FAIL: 0, UNKNOWN: 0, NOT_APPLICABLE: 0}
    per_vendor: dict[str, dict] = {}
    for bidder in bidders:
        vid = bidder["vendor_id"]
        evaluations = [evaluate_rule(rule, facts.get(vid, {}), tender["bid_deadline"]) for rule in rules]
        for ev in evaluations:
            counts[ev["result"]] += 1
            conn.execute(
                "INSERT INTO compliance (tender_id, vendor_id, rule_id, result, body) VALUES (?, ?, ?, ?, ?)",
                (tender_id, vid, ev["rule_id"], ev["result"], dumps(ev)),
            )
        per_vendor[vid] = {
            "status": overall_status(evaluations),
            "counts": {k: sum(e["result"] == k for e in evaluations) for k in counts},
        }
    summary = {
        "tender_id": tender_id,
        "bidders": len(bidders),
        "rules": len(rules),
        "evaluations": len(bidders) * len(rules),
        "counts": counts,
        "vendors": per_vendor,
    }
    put_artifact(conn, tender_id, "compliance", summary, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return summary


def compliance_matrix(conn: sqlite3.Connection, tender_id: str) -> dict:
    rules = load_rules(conn, tender_id)
    rows = fetch_all(conn, "SELECT vendor_id, rule_id, result, body FROM compliance WHERE tender_id = ?", (tender_id,))
    vendors = fetch_all(
        conn,
        "SELECT v.vendor_id, v.alias, v.name FROM vendors v WHERE v.vendor_id IN "
        "(SELECT DISTINCT vendor_id FROM compliance WHERE tender_id = ?) ORDER BY v.vendor_id",
        (tender_id,),
    )
    cells: dict[str, dict[str, dict]] = {}
    for r in rows:
        cells.setdefault(r["vendor_id"], {})[r["rule_id"]] = r["body"]
    vendor_rows = []
    for v in vendors:
        evaluations = list(cells.get(v["vendor_id"], {}).values())
        vendor_rows.append({
            **v,
            "status": overall_status(evaluations),
            "counts": {k: sum(e["result"] == k for e in evaluations) for k in (PASS, FAIL, UNKNOWN, NOT_APPLICABLE)},
        })
    return {
        "tender_id": tender_id,
        "rules": [
            {k: r[k] for k in ("rule_id", "category", "requirement", "condition", "mandatory", "source")} for r in rules
        ],
        "vendors": vendor_rows,
        "cells": cells,
        "evaluations": len(rows),
    }
