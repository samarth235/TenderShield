from app.compliance.engine import compliance_matrix, evaluate_rule
from app.db import session

from .conftest import TENDER


def _rule(**kw):
    base = {"rule_id": "RX", "metric": "avg_annual_turnover_cr", "operator": "gte", "threshold": 10.0,
            "mandatory": True, "condition": "avg_annual_turnover_cr >= 10", "applies_if": None}
    return {**base, **kw}


def test_missing_evidence_is_unknown_not_fail():
    result = evaluate_rule(_rule(), {}, None)
    assert result["result"] == "UNKNOWN"


def test_numeric_threshold():
    fact = {"value": 9.5, "document_id": "D", "filename": "f.pdf", "page": 1, "excerpt": "x"}
    assert evaluate_rule(_rule(), {"avg_annual_turnover_cr": fact}, None)["result"] == "FAIL"
    fact["value"] = 12.4
    ok = evaluate_rule(_rule(), {"avg_annual_turnover_cr": fact}, None)
    assert ok["result"] == "PASS" and ok["evidence"][0]["page"] == 1


def test_certificate_validity_uses_submission_date():
    rule = _rule(metric="iso9001_valid_until", operator="valid_on_submission", threshold=None)
    facts = {"iso9001_valid_until": {"value": "2026-01-31"},
             "submitted_at": {"value": "2026-03-12T18:30:44+05:30"}}
    assert evaluate_rule(rule, facts, None)["result"] == "FAIL"
    facts["iso9001_valid_until"]["value"] = "2026-03-12"
    assert evaluate_rule(rule, facts, None)["result"] == "PASS"


def test_demo_matrix(analyzed):
    with session() as conn:
        m = compliance_matrix(conn, TENDER)
    assert m["evaluations"] == 108  # 6 bidders x 18 rules
    status = {v["vendor_id"]: v["status"] for v in m["vendors"]}
    assert status["V005"] == "NOT_QUALIFIED"        # Vendor E - expired ISO 9001
    assert status["V006"] == "INCOMPLETE_EVIDENCE"  # Vendor F - ownership disclosure missing
    assert status["V001"] == status["V002"] == "QUALIFIED"
    rule_by_metric = {r["condition"].split()[0]: r["rule_id"] for r in m["rules"]}
    iso = rule_by_metric["iso9001_valid_until"]
    assert m["cells"]["V005"][iso]["result"] == "FAIL"
    assert m["cells"]["V005"][iso]["evidence"][0]["filename"] == "ComplianceDocs_E.pdf"
    assert m["cells"]["V006"][rule_by_metric["ownership_disclosure"]]["result"] == "UNKNOWN"
    udyam = rule_by_metric["udyam_registered"]
    assert m["cells"]["V003"][udyam]["result"] == "PASS"
    assert m["cells"]["V001"][udyam]["result"] == "NOT_APPLICABLE"
