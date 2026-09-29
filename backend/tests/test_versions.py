"""Document versioning, historical integrity, change analysis, explanation and auditor review."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.evidence import changes as changes_module
from app.main import app

from .conftest import TENDER

DOC = "DOC-V001-COMP"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/demo/load", params={"analyze": "true"})
        yield c


@pytest.fixture(scope="module")
def flow(client):
    """V1 sealed in snapshot S1, then the bidder uploads a renewed V2."""
    s1 = client.post(f"/api/tenders/{TENDER}/evidence/finalize", json={"auditor": "A. Auditor"}).json()
    v1_before = client.get(f"/api/documents/{DOC}/versions/1").json()
    created = client.post("/api/demo/new-version", json={})
    assert created.status_code == 200, created.text
    return {"s1": s1, "v1_before": v1_before, "created": created.json()}


def test_v1_is_created_for_every_document(client):
    listing = client.get(f"/api/documents/{DOC}/versions").json()
    v1 = listing["versions"][0]
    assert v1["version"] == 1 and v1["label"] == "V1" and v1["parent_version_id"] is None
    assert v1["status"] == "ACTIVE" and listing["official_version"] == 1
    assert v1["sha256"] == client.get(f"/api/documents/{DOC}").json()["sha256"]
    assert {"created_at", "created_by", "sha256", "filename"} <= set(v1)


def test_finalising_anchors_v1_with_its_own_chain_payload(client, flow):
    v1 = client.get(f"/api/documents/{DOC}/versions/1").json()
    payload = v1["chain_payload"]
    assert payload["case_id"] == f"{flow['s1']['snapshot_id']}:{DOC}@v1"
    assert payload["evidence_hash"] == v1["sha256"] and len(payload["audit_head_hash"]) == 64
    assert payload["auditor_actions"] == ["V1_FINALIZED"]
    assert flow["s1"]["snapshot_id"] in v1["committed_in_snapshots"]


def test_creating_v2_keeps_v1_unchanged(client, flow):
    v2 = flow["created"]["version"]
    assert v2["version"] == 2 and v2["parent_version_id"] == f"{DOC}@v1" and v2["status"] == "PENDING_REVIEW"
    v1_after = client.get(f"/api/documents/{DOC}/versions/1").json()
    assert v1_after == flow["v1_before"] | {"committed_in_snapshots": v1_after["committed_in_snapshots"]}
    assert v1_after["sha256"] != v2["sha256"]
    file_v2 = client.get(f"/api/documents/{DOC}/versions/2/file").content
    assert hashlib.sha256(file_v2).hexdigest() == v2["sha256"]
    # Uploading identical bytes again never creates a duplicate version.
    assert client.post("/api/demo/new-version", json={}).status_code == 409


def test_historical_verification_still_succeeds_and_v2_is_recognised(client, flow):
    s1 = client.get(f"/api/evidence/snapshots/{flow['s1']['snapshot_id']}/verify").json()
    assert s1["match"] is True and s1["status"] == "NEW_VERSION_DETECTED"
    assert s1["newer_versions"][0]["latest_version"] == 2 and not s1["changed_documents"]
    v1 = client.get(f"/api/documents/{DOC}/versions/1/verify").json()
    assert v1["match"] and v1["status"] == "HISTORICALLY_VERIFIED" and v1["latest_version"] == 2
    v2 = client.get(f"/api/documents/{DOC}/versions/2/verify").json()
    assert v2["match"] and v2["status"] == "NEW_VERSION_DETECTED"
    assert "differs from the historically committed version" in v2["explanation"]
    for text in (s1["explanation"], v1["explanation"], v2["explanation"]):
        assert "fraud" not in text.lower() and "invalid" not in text.lower()


def test_change_analysis_reports_extracted_fields_with_rule_checks(client, flow):
    diff = client.get(f"/api/documents/{DOC}/changes", params={"from_version": 1, "to_version": 2}).json()
    assert diff["from_version"] == "V1" and diff["to_version"] == "V2" and diff["hashes"]["differ"]
    by_field = {c["field"]: c for c in diff["changes"]}
    assert set(by_field) == {"avg_annual_turnover_cr", "iso9001_valid_until", "iso27001_valid_until"}
    iso = by_field["iso9001_valid_until"]
    assert (iso["old_value"], iso["new_value"], iso["change_type"]) == ("2027-06-30", "2029-06-30", "modified")
    assert iso["potentially_routine"] and iso["impact"] == "routine"
    turnover = by_field["avg_annual_turnover_cr"]
    assert turnover["affects_eligibility"] and turnover["requires_verification"]
    assert turnover["rule_check"]["before"] == "PASS" and turnover["rule_check"]["after"] == "PASS"
    assert {"company_name", "certificate_number"} <= {u["field"] for u in diff["unchanged"]}
    assert flow["created"]["comparison"]["counts"] == diff["counts"]


def test_template_explanation_is_the_safe_fallback(client, flow, monkeypatch):
    monkeypatch.setattr(changes_module, "llm_available", lambda: False)
    body = client.post(f"/api/documents/{DOC}/versions/2/explain", json={"method": "llm"}).json()
    exp = body["explanation"]
    assert exp["method"] == "template" and exp["warnings"]
    assert "renewal" in exp["summary"] and "turnover" in exp["summary"]
    assert exp["integrity_facts"]["historical_version_unchanged"] is True
    assert any("certification body" in c for c in exp["auditor_checks"])


def test_llm_explanation_is_used_when_available(client, flow, monkeypatch):
    seen = {}

    def fake(comparison, integrity):
        seen["integrity"] = integrity
        return {"summary": "Validity dates were extended; turnover changed and should be verified.",
                "what_changed": ["x"], "potentially_routine": ["y"], "affects_eligibility": ["z"],
                "requires_verification": ["t"], "auditor_checks": ["Confirm with the certification body."]}, "claude-test"

    monkeypatch.setattr(changes_module, "llm_available", lambda: True)
    monkeypatch.setattr(changes_module, "explain_with_llm", fake)
    exp = client.post(f"/api/documents/{DOC}/versions/2/explain", json={}).json()["explanation"]
    assert exp["method"] == "llm" and exp["model"] == "claude-test"
    assert seen["integrity"]["hashes_differ"] is True


def test_llm_cannot_issue_verdicts_or_change_integrity(client, flow, monkeypatch):
    def verdict(comparison, integrity):
        return {"summary": "This is a legitimate renewal, integrity is fine.", "what_changed": [],
                "potentially_routine": [], "affects_eligibility": [], "requires_verification": [],
                "auditor_checks": []}, "claude-test"

    monkeypatch.setattr(changes_module, "llm_available", lambda: True)
    monkeypatch.setattr(changes_module, "explain_with_llm", verdict)
    exp = client.post(f"/api/documents/{DOC}/versions/2/explain", json={}).json()["explanation"]
    assert exp["method"] == "template" and "verdict language" in exp["warnings"][0]

    def broken(comparison, integrity):
        raise RuntimeError("network down")

    monkeypatch.setattr(changes_module, "explain_with_llm", broken)
    exp = client.post(f"/api/documents/{DOC}/versions/2/explain", json={}).json()["explanation"]
    assert exp["method"] == "template"
    # Explaining never changes the version's review status.
    assert client.get(f"/api/documents/{DOC}/versions/2").json()["status"] == "PENDING_REVIEW"


def test_auditor_actions_are_recorded_and_accept_anchors_v2(client, flow):
    r = client.post(f"/api/documents/{DOC}/versions/2/review",
                    json={"decision": "REQUEST_VERIFICATION", "auditor": "A. Auditor", "notes": "Call the ISO body"})
    assert r.status_code == 200 and r.json()["version"]["status"] == "VERIFICATION_REQUESTED"
    assert r.json()["audit_entry"]["payload"]["decision"] == "REQUEST_VERIFICATION"
    assert client.post(f"/api/documents/{DOC}/versions/2/review",
                       json={"decision": "GUILTY", "auditor": "x"}).status_code == 422

    accepted = client.post(f"/api/documents/{DOC}/versions/2/review",
                           json={"decision": "ACCEPT", "auditor": "A. Auditor", "notes": "Confirmed renewal"}).json()
    v2, s2 = accepted["version"], accepted["snapshot"]
    assert v2["status"] == "ACTIVE" and s2 is not None
    assert v2["chain_payload"]["case_id"] == f"{s2['snapshot_id']}:{DOC}@v2"
    assert v2["chain_payload"]["evidence_hash"] == v2["sha256"] and v2["chain_payload"]["auditor_actions"] == ["V2_ACCEPTED"]
    listing = client.get(f"/api/documents/{DOC}/versions").json()
    assert listing["official_version"] == 2 and listing["versions"][0]["status"] == "SUPERSEDED"
    # V1's own anchor is never replaced.
    assert listing["versions"][0]["chain_payload"]["case_id"].startswith(flow["s1"]["snapshot_id"])

    log = client.get(f"/api/tenders/{TENDER}/audit-log").json()
    reviews = [e for e in log["entries"] if e["action"] == "VERSION_REVIEW"]
    assert [e["payload"]["decision"] for e in reviews] == ["REQUEST_VERIFICATION", "ACCEPT"]
    assert any(e["action"] == "DOCUMENT_VERSION_CREATED" for e in log["entries"]) and log["chain"]["valid"]
    # Decided versions cannot be decided again.
    assert client.post(f"/api/documents/{DOC}/versions/2/review",
                       json={"decision": "FLAG_FOR_INVESTIGATION", "auditor": "B"}).status_code == 409

    assert client.get(f"/api/evidence/snapshots/{s2['snapshot_id']}/verify").json()["status"] == "INTEGRITY_VERIFIED"
    assert client.get(f"/api/evidence/snapshots/{flow['s1']['snapshot_id']}/verify").json()["match"] is True


def test_in_place_change_of_v1_is_an_integrity_mismatch(client, flow):
    s1 = flow["s1"]["snapshot_id"]
    client.post("/api/demo/tamper", json={})
    v1 = client.get(f"/api/documents/{DOC}/versions/1/verify").json()
    assert v1["status"] == "INTEGRITY_MISMATCH" and not v1["match"]
    assert "no longer matches its original fingerprint" in v1["explanation"]
    bad = client.get(f"/api/evidence/snapshots/{s1}/verify").json()
    assert bad["status"] == "INTEGRITY_MISMATCH" and bad["changed_documents"][0]["version_id"] == f"{DOC}@v1"
    # V2 and the snapshot that committed it are unaffected.
    assert client.get(f"/api/documents/{DOC}/versions/2/verify").json()["status"] == "INTEGRITY_VERIFIED"
    client.post("/api/demo/restore")
    assert client.get(f"/api/documents/{DOC}/versions/1/verify").json()["status"] == "HISTORICALLY_VERIFIED"
    assert client.get(f"/api/evidence/snapshots/{s1}/verify").json()["match"] is True


def test_version_upload_endpoint_and_validation(client):
    other = "DOC-V003-COMP"
    pdf = client.get(f"/api/documents/{DOC}/versions/2/file").content
    r = client.post(f"/api/documents/{other}/versions", files={"file": ("renewal.pdf", pdf, "application/pdf")},
                    data={"created_by": "Bidder portal", "note": "test"})
    assert r.status_code == 200, r.text
    assert r.json()["version"]["version"] == 2 and r.json()["comparison"]["changes"]
    assert client.post(f"/api/documents/{other}/versions", files={"file": ("x.pdf", b"nope", "application/pdf")},
                       data={"created_by": "x"}).status_code == 400
    assert client.get("/api/documents/NOPE/versions").status_code == 404
    assert client.get(f"/api/documents/{DOC}/versions/9/verify").status_code == 404
