"""Tender Rulebook model (Stage 3) and the controlled metric vocabulary.

Every extractor (pattern or LLM) must map a clause onto a metric from ``METRICS`` so
that the deterministic compliance engine knows which bidder fact to test. Clauses that
cannot be mapped are kept as ``unmapped`` rules and evaluate to UNKNOWN.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Operator = Literal["gte", "gt", "lte", "eq", "is_true", "is_false", "valid_on_submission", "submitted_before"]

OPERATOR_SYMBOL = {
    "gte": ">=", "gt": ">", "lte": "<=", "eq": "==", "is_true": "== true", "is_false": "== false",
    "valid_on_submission": "valid on bid submission date", "submitted_before": "<=",
}

# metric -> (category, value type, unit, human label)
METRICS: dict[str, dict[str, str]] = {
    "avg_annual_turnover_cr": {"category": "Financial", "type": "number", "unit": "crore", "label": "Average annual turnover"},
    "net_worth_cr": {"category": "Financial", "type": "number", "unit": "crore", "label": "Net worth"},
    "solvency_amount_cr": {"category": "Financial", "type": "number", "unit": "crore", "label": "Solvency certificate amount"},
    "years_in_operation": {"category": "Experience", "type": "number", "unit": "years", "label": "Years in operation"},
    "similar_projects_5y": {"category": "Experience", "type": "number", "unit": "projects", "label": "Similar projects completed (5 years)"},
    "similar_projects_value_cr": {"category": "Experience", "type": "number", "unit": "crore", "label": "Aggregate value of similar projects"},
    "technical_staff": {"category": "Resources", "type": "number", "unit": "persons", "label": "Technical personnel on payroll"},
    "iso9001_valid_until": {"category": "Certification", "type": "date", "unit": "", "label": "ISO 9001 certificate validity"},
    "iso27001_valid_until": {"category": "Certification", "type": "date", "unit": "", "label": "ISO/IEC 27001 certificate validity"},
    "gst_registered": {"category": "Statutory", "type": "bool", "unit": "", "label": "GST registration"},
    "pan_available": {"category": "Statutory", "type": "bool", "unit": "", "label": "PAN furnished"},
    "blacklisted": {"category": "Integrity", "type": "bool", "unit": "", "label": "Blacklisted / debarred"},
    "ownership_disclosure": {"category": "Integrity", "type": "bool", "unit": "", "label": "Director / ownership disclosure"},
    "power_of_attorney": {"category": "Statutory", "type": "bool", "unit": "", "label": "Power of attorney for signatory"},
    "claims_msme_exemption": {"category": "Statutory", "type": "bool", "unit": "", "label": "MSME exemption claimed"},
    "udyam_registered": {"category": "Statutory", "type": "bool", "unit": "", "label": "Udyam (MSME) registration"},
    "emd_amount_lakh": {"category": "Bid Security", "type": "number", "unit": "lakh", "label": "Earnest money deposit"},
    "submitted_at": {"category": "Process", "type": "datetime", "unit": "", "label": "Bid submission time"},
    "bid_validity_days": {"category": "Process", "type": "number", "unit": "days", "label": "Bid validity"},
}


class Condition(BaseModel):
    metric: str
    operator: Operator
    threshold: Any = None


class RuleSource(BaseModel):
    document_id: str
    filename: str
    page: int
    clause: str


class Extraction(BaseModel):
    method: Literal["pattern", "llm"]
    confidence: float
    model: Optional[str] = None


class Rule(BaseModel):
    rule_id: str
    category: str
    requirement: str
    metric: str
    operator: Operator
    threshold: Any = None
    unit: str = ""
    mandatory: bool = True
    applies_if: Optional[Condition] = None
    condition: str = ""
    clause_text: str
    source: RuleSource
    extraction: Extraction
    notes: list[str] = Field(default_factory=list)


def describe_condition(metric: str, operator: str, threshold: Any) -> str:
    symbol = OPERATOR_SYMBOL[operator]
    if operator in ("is_true", "is_false", "valid_on_submission"):
        return f"{metric} {symbol}"
    return f"{metric} {symbol} {threshold}"


def describe_requirement(metric: str, operator: str, threshold: Any) -> str:
    info = METRICS.get(metric, {"label": metric, "unit": ""})
    label, unit = info["label"], info["unit"]
    if operator == "valid_on_submission":
        return f"{label}: valid on bid submission date"
    if operator == "is_true":
        return f"{label}: required"
    if operator == "is_false":
        return f"{label}: must not apply"
    if operator == "submitted_before":
        return f"Bid submitted on or before {threshold}"
    if operator == "gt" and threshold == 0:
        return f"{label} must be positive"
    amount = f"Rs. {threshold:g} {unit}" if unit in ("crore", "lakh") else f"{threshold:g} {unit}".strip()
    return f"{label} {OPERATOR_SYMBOL[operator]} {amount}"
