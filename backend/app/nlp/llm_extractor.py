"""LLM requirement extraction with Claude (Stage 2 - AI Tender Understanding).

The model only proposes *candidate* rules mapped onto the controlled metric vocabulary.
It never decides compliance: candidates are normalised into deterministic rules that
retain their source clause and page, and are then evaluated by the rule engine.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..config import get_settings
from .rulebook import METRICS
from .segmentation import Clause

log = logging.getLogger(__name__)

MetricName = Literal[tuple(METRICS) + ("unmapped",)]  # type: ignore[valid-type]


class CandidateRule(BaseModel):
    clause_id: str = Field(description="Clause number the requirement came from, e.g. '4.2'")
    metric: MetricName = Field(description="Metric from the vocabulary, or 'unmapped' if none fits")
    operator: Literal["gte", "gt", "lte", "eq", "is_true", "is_false", "valid_on_submission", "submitted_before"]
    threshold_number: Optional[float] = Field(None, description="Numeric threshold expressed in the metric's unit")
    threshold_text: Optional[str] = Field(None, description="ISO-8601 timestamp for submitted_before, else null")
    mandatory: bool
    applies_only_if_msme_exemption_claimed: bool = False
    confidence: float = Field(description="0-1 confidence that the mapping is correct")


class CandidateRules(BaseModel):
    rules: list[CandidateRule]


SYSTEM_PROMPT = """You convert eligibility clauses from public-procurement tender documents into \
machine-checkable rule candidates for an audit system. Auditors rely on these rules, so precision \
matters more than coverage: only emit a rule when a clause states a requirement bidders must (or, \
for optional/desirable clauses, should) satisfy.

Map each requirement onto exactly one metric from the vocabulary. A single clause may contain several \
requirements (for example a project count and an aggregate value) - emit one rule for each. Express \
numeric thresholds in the metric's unit (convert lakh <-> crore where needed; 1 crore = 100 lakh). \
Use operator "valid_on_submission" for certificates that must be valid on the bid date, and \
"submitted_before" with an ISO-8601 timestamp (include the timezone offset if stated) for submission \
deadlines. Mark mandatory=false only when the clause says the requirement is desirable, preferred or \
optional. If a requirement fits no metric, emit metric "unmapped" rather than forcing a mapping. \
Ignore clauses that are purely descriptive (scope of work, evaluation procedure, general notes)."""


def llm_available() -> bool:
    """True when Anthropic credentials are visibly configured (env var or `ant auth login` profile)."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE"):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


def extract_candidates_llm(clauses: list[Clause]) -> tuple[list[dict], str]:
    """Return (candidates, model). Raises on API failure or refusal - the caller falls back."""
    import anthropic

    settings = get_settings()
    vocabulary = {name: {k: v for k, v in info.items() if k != "category"} for name, info in METRICS.items()}
    payload = {"metric_vocabulary": vocabulary, "clauses": [c.to_dict() for c in clauses]}

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=settings.llm_model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": "Extract rule candidates from these tender clauses.\n\n" + json.dumps(payload, indent=2),
            }
        ],
        output_format=CandidateRules,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("LLM declined the extraction request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("LLM output was truncated (max_tokens)")
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError("LLM returned no structured output")

    candidates = []
    for rule in parsed.rules:
        threshold = rule.threshold_text if rule.operator == "submitted_before" else rule.threshold_number
        if rule.operator in ("is_true",):
            threshold = True
        elif rule.operator == "is_false":
            threshold = False
        candidates.append(
            {
                "clause_id": rule.clause_id,
                "metric": rule.metric,
                "operator": rule.operator,
                "threshold": threshold,
                "mandatory": rule.mandatory,
                "applies_if": (
                    {"metric": "claims_msme_exemption", "operator": "is_true", "threshold": True}
                    if rule.applies_only_if_msme_exemption_claimed
                    else None
                ),
                "confidence": max(0.0, min(1.0, rule.confidence)),
            }
        )
    return candidates, response.model
