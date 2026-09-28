import pytest

from app.db import fetch_all, session
from app.reasoning.counterfactual import NotTestable, evaluate_removal, robustness_report
from app.reasoning.engine import load_finding
from app.reasoning.scoring import assess

from .conftest import TENDER


def _item(family, weight):
    return {"family": family, "weight": weight}


def test_scoring_requires_independent_corroboration():
    assert assess([])["level"] == "NONE"
    assert assess([_item("corporate", 0.2)])["level"] == "LOW"
    assert assess([_item("corporate", 0.2), _item("document", 0.25)])["level"] == "MEDIUM"
    # Lots of support but a single family is still not escalated.
    assert assess([_item("behavioural", 0.25)] * 4)["level"] == "LOW"
    assert assess([_item("behavioural", 0.5), _item("corporate", 0.45)])["level"] == "HIGH"


def _findings():
    with session() as conn:
        ids = [r["finding_id"] for r in fetch_all(conn, "SELECT finding_id FROM findings WHERE tender_id = ?", (TENDER,))]
        return [load_finding(conn, i) for i in ids]


def _pair(findings, a, b):
    return next(f for f in findings if f["category"] == "INVESTIGATION_SIGNAL"
                and [v["vendor_id"] for v in f["subject"]["vendors"]] == [a, b])


def test_planted_scenarios_are_distinguished(analyzed):
    findings = _findings()
    ab = _pair(findings, "V001", "V002")
    assert ab["level"] == "HIGH" and ab["recommendation"] == "REVIEW"
    types = {e["type"] for e in ab["evidence"]}
    assert {"SHARED_DIRECTOR", "SHARED_ADDRESS", "REPEATED_CO_BIDDING", "WINNER_ROTATION", "DOCUMENT_SIMILARITY"} <= types
    assert ab["reasoning"]["steps"][0]["label"] == "Corporate overlap"
    assert ab["alternative_explanations"] and ab["recommended_verification"]

    cd = _pair(findings, "V003", "V004")
    assert cd["level"] == "LOW" and cd["recommendation"] == "NO_ACTION"

    compliance = [f for f in findings if f["category"] == "COMPLIANCE"]
    assert [f["subject"]["vendors"][0]["vendor_id"] for f in compliance] == ["V005"]
    quality = [f for f in findings if f["category"] == "DATA_QUALITY"]
    assert [f["subject"]["vendors"][0]["vendor_id"] for f in quality] == ["V006"]
    assert findings[0] is not None and findings[0]["finding_id"].endswith("F01") and findings[0] == ab


def test_counterfactual_matches_hero_demo(analyzed):
    ab = _pair(_findings(), "V001", "V002")
    ids = {e["type"]: e["evidence_id"] for e in ab["evidence"]}
    director_removed = evaluate_removal(ab, [ids["SHARED_DIRECTOR"]])
    assert director_removed["status"] == "STILL_SUPPORTED"
    behavioural = [e["evidence_id"] for e in ab["evidence"] if e["family"] in ("behavioural", "model")]
    downgraded = evaluate_removal(ab, behavioural)
    assert downgraded["status"] == "DOWNGRADED"
    report = robustness_report(ab)
    assert report["robustness_score"] == 1.0
    assert report["minimal_breaking_set"]["size"] >= 2


def test_counterfactual_rejects_compliance_findings(analyzed):
    compliance = next(f for f in _findings() if f["category"] == "COMPLIANCE")
    with pytest.raises(NotTestable):
        robustness_report(compliance)
