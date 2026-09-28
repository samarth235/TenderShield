"""Deterministic, offline requirement extractor.

A library of linguistic patterns (trigger phrase + value grammar) maps natural-language
eligibility clauses onto the controlled metric vocabulary. It is the default extractor
in Demo Mode because it is reproducible and needs no network access; the LLM extractor
produces the same candidate format for clauses written in unfamiliar styles.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

from .segmentation import Clause

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20,
}
NUM = r"(\d+(?:\.\d+)?|" + "|".join(WORD_NUMBERS) + r")"
AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\b|lakh|lac)", re.I)
AT_LEAST = r"(?:at least|minimum of|not less than|no less than|a minimum of)"
REQUIREMENT_VERB = re.compile(r"\b(shall|must|is required|are required|desirable|preferred)\b", re.I)
OPTIONAL = re.compile(r"\b(desirable|preferred|considered favourably|optional)\b", re.I)


def to_number(token: str) -> float:
    token = token.lower().replace(",", "")
    return float(WORD_NUMBERS.get(token, token))


def amount_in(text: str, unit: str) -> float | None:
    match = AMOUNT.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    source_unit = "crore" if match.group(2).lower().startswith("cr") else "lakh"
    if source_unit == unit:
        return value
    return value / 100 if unit == "crore" else value * 100


def _count(pattern: str) -> Callable[[str], float | None]:
    regex = re.compile(pattern, re.I)

    def extract(text: str) -> float | None:
        match = regex.search(text)
        return to_number(match.group(1)) if match else None

    return extract


def _deadline(text: str) -> str | None:
    match = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}),?\s*(\d{1,2}:\d{2})", text)
    if not match:
        return None
    stamp = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d %B %Y %H:%M")
    offset = "+05:30" if re.search(r"\bIST\b", text) else ""
    return stamp.isoformat() + offset


# (metric, trigger regex, operator, value extractor or constant, applies_if)
PATTERNS: list[tuple[str, str, str, Any, dict | None]] = [
    ("avg_annual_turnover_cr", r"\bturnover\b", "gte", lambda t: amount_in(t, "crore"), None),
    ("net_worth_cr", r"\bpositive net worth\b", "gt", 0, None),
    ("net_worth_cr", r"\bnet worth of\b", "gte", lambda t: amount_in(t, "crore"), None),
    ("solvency_amount_cr", r"\bsolvency\b", "gte", lambda t: amount_in(t, "crore"), None),
    ("years_in_operation", r"\bin (?:operation|existence)\b|\byears of experience\b", "gte",
     _count(AT_LEAST + r"\s+" + NUM + r"\s+years"), None),
    ("similar_projects_5y", r"\bsimilar (?:projects|works)\b", "gte", _count(AT_LEAST + r"\s+" + NUM + r"\s+similar"), None),
    ("similar_projects_value_cr", r"\baggregate value\b", "gte", lambda t: amount_in(t, "crore"), None),
    ("technical_staff", r"\btechnical (?:personnel|staff|manpower)\b", "gte",
     _count(AT_LEAST + r"\s+" + NUM + r"\s+technical"), None),
    ("iso9001_valid_until", r"\bISO\s*9001", "valid_on_submission", None, None),
    ("iso27001_valid_until", r"\bISO(?:/IEC)?\s*27001", "valid_on_submission", None, None),
    ("gst_registered", r"\bGST\b|Goods and Services Tax", "is_true", True, None),
    ("pan_available", r"\bPAN\b|Permanent Account Number", "is_true", True, None),
    ("blacklisted", r"\bblacklisted\b|\bdebarred\b", "is_false", False, None),
    ("ownership_disclosure", r"Director Identification|beneficial owners?|ownership details", "is_true", True, None),
    ("power_of_attorney", r"Power of Attorney", "is_true", True, None),
    ("udyam_registered", r"\bUdyam\b", "is_true", True,
     {"metric": "claims_msme_exemption", "operator": "is_true", "threshold": True}),
    ("emd_amount_lakh", r"Earnest Money|\bEMD\b", "gte", lambda t: amount_in(t, "lakh"), None),
    ("submitted_at", r"submitted on or before|submission deadline|last date (?:and time )?for submission", "submitted_before",
     _deadline, None),
    ("bid_validity_days", r"\bremain valid\b|\bbid validity\b", "gte", _count(r"(?:not less than\s+)?" + NUM + r"\s+days"), None),
]


def extract_candidates(clauses: list[Clause]) -> list[dict]:
    candidates: list[dict] = []
    for clause in clauses:
        text = clause.text
        if not REQUIREMENT_VERB.search(text):
            continue
        seen: set[str] = set()
        for metric, trigger, operator, value, applies_if in PATTERNS:
            if metric in seen or not re.search(trigger, text, re.I):
                continue
            threshold = value(text) if callable(value) else value
            if threshold is None and operator not in ("valid_on_submission",):
                continue  # trigger matched but the clause carries no usable value for this metric
            seen.add(metric)
            candidates.append(
                {
                    "clause_id": clause.clause_id,
                    "metric": metric,
                    "operator": operator,
                    "threshold": threshold,
                    "mandatory": not OPTIONAL.search(text),
                    "applies_if": applies_if,
                    "confidence": 0.9,
                }
            )
    return candidates
