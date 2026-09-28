"""Evidence weights and the explicit, inspectable scoring rule for investigation signals.

The rule is deliberately simple so an auditor can re-derive any level by hand:
  HIGH    support >= 0.90, includes behavioural evidence, and >= 2 independent evidence families
  MEDIUM  support >= 0.45 and >= 2 independent evidence families
  LOW     some evidence, but not enough independent corroboration  -> relationship noted, no escalation
  NONE    no evidence
Evidence families: corporate, behavioural, document. The ML anomaly score adds support
but never counts as an independent family on its own.
"""

from __future__ import annotations

EVIDENCE_TYPES: dict[str, dict] = {
    "SHARED_DIRECTOR": {"family": "corporate", "weight": 0.20, "label": "Shared director"},
    "SHARED_ADDRESS": {"family": "corporate", "weight": 0.15, "label": "Shared registered address"},
    "SHARED_CONTACT": {"family": "corporate", "weight": 0.15, "label": "Shared contact details"},
    "REPEATED_CO_BIDDING": {"family": "behavioural", "weight": 0.20, "label": "Repeated co-bidding"},
    "WINNER_ROTATION": {"family": "behavioural", "weight": 0.25, "label": "Recurring winner/runner-up pattern"},
    "PRICE_PROXIMITY": {"family": "behavioural", "weight": 0.10, "label": "Consistently close bid prices"},
    "SUBMISSION_TIMING": {"family": "behavioural", "weight": 0.10, "label": "Near-simultaneous submissions"},
    "DOCUMENT_SIMILARITY": {"family": "document", "weight": 0.25, "label": "High bid-document similarity"},
    "BEHAVIOUR_ANOMALY": {"family": "model", "weight": 0.10, "label": "Unusual behaviour combination (Isolation Forest)"},
}
MODERATE_DOCUMENT_WEIGHT = 0.12
INDEPENDENT_FAMILIES = ("corporate", "behavioural", "document")
LEVELS = ["NONE", "LOW", "MEDIUM", "HIGH"]
HIGH_SUPPORT, MEDIUM_SUPPORT = 0.90, 0.45


def assess(items: list[dict]) -> dict:
    support = round(sum(i["weight"] for i in items), 3)
    families = sorted({i["family"] for i in items if i["family"] in INDEPENDENT_FAMILIES})
    if not items:
        level = "NONE"
    elif support >= HIGH_SUPPORT and "behavioural" in families and len(families) >= 2:
        level = "HIGH"
    elif support >= MEDIUM_SUPPORT and len(families) >= 2:
        level = "MEDIUM"
    else:
        level = "LOW"
    return {"support": support, "families": families, "level": level, "evidence_count": len(items)}


def level_rank(level: str) -> int:
    return LEVELS.index(level)


def scoring_rule() -> dict:
    return {
        "weights": {k: {"family": v["family"], "weight": v["weight"]} for k, v in EVIDENCE_TYPES.items()},
        "moderate_document_similarity_weight": MODERATE_DOCUMENT_WEIGHT,
        "levels": {
            "HIGH": f"support >= {HIGH_SUPPORT}, behavioural evidence present, >= 2 independent families",
            "MEDIUM": f"support >= {MEDIUM_SUPPORT}, >= 2 independent families",
            "LOW": "evidence present without independent corroboration (relationship noted, not escalated)",
            "NONE": "no evidence",
        },
        "independent_families": list(INDEPENDENT_FAMILIES),
    }
