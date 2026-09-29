import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import app

from .conftest import TENDER


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_hero_demo_flow(client):
    loaded = client.post("/api/demo/load", params={"analyze": "true"}).json()
    assert loaded["bidders"] == 6 and loaded["historical_tenders"] == 480 and loaded["registered_vendors"] == 260
    assert loaded["analysis"]["stages"][2]["summary"]["evaluations"] == 108

    rules = client.get(f"/api/tenders/{TENDER}/rules").json()["rules"]
    assert len(rules) == 18

    graph = client.get(f"/api/tenders/{TENDER}/graph").json()
    vendors = {n["vendor_id"]: n for n in graph["nodes"] if n["type"] == "vendor"}
    assert sum(n["is_bidder"] for n in vendors.values()) == 6
    # Second-degree network: Vendor A's director's family firm and the shell sharing Vendor B's phone.
    assert {"V007", "V008"} <= {vid for vid, n in vendors.items() if not n["is_bidder"]}
    paths = client.get(f"/api/tenders/{TENDER}/graph/paths", params={"a": "V001", "b": "V002"}).json()["paths"]
    assert {p["via"]["type"] for p in paths} == {"director", "address"}

    findings = client.get(f"/api/tenders/{TENDER}/findings").json()
    hero = findings[0]
    assert hero["level"] == "HIGH"
    card = client.get(f"/api/findings/{hero['finding_id']}").json()
    director = next(e["evidence_id"] for e in card["evidence"] if e["type"] == "SHARED_DIRECTOR")

    cf = client.post(f"/api/findings/{hero['finding_id']}/counterfactual", json={"remove": [director]}).json()
    assert cf["status"] == "STILL_SUPPORTED" and cf["run_id"]
    assert client.get(f"/api/findings/{hero['finding_id']}/robustness").status_code == 200
    bad = client.post(f"/api/findings/{hero['finding_id']}/counterfactual", json={"remove": ["E99"]})
    assert bad.status_code == 400

    disp = client.post(f"/api/findings/{hero['finding_id']}/disposition",
                       json={"decision": "FURTHER_REVIEW", "auditor": "A. Auditor", "notes": "Check MCA records"})
    assert disp.status_code == 200 and disp.json()["status"] == "FURTHER_REVIEW"

    dossier = client.get(f"/api/tenders/{TENDER}/dossier-data").json()
    assert dossier["auditor_dispositions"][0]["payload"]["decision"] == "FURTHER_REVIEW"
    assert len(dossier["evidence_manifest"]) == 14

    snap = client.post(f"/api/tenders/{TENDER}/evidence/finalize", json={"auditor": "A. Auditor"}).json()
    assert len(snap["bundle_hash"]) == 64 and snap["chain_payload"]["evidence_hash"] == snap["bundle_hash"]
    sid = snap["snapshot_id"]
    full = client.get(f"/api/evidence/snapshots/{sid}", params={"include_bundle": "true"}).json()
    assert hashlib.sha256(full["canonical_json"].encode()).hexdigest() == snap["bundle_hash"]

    ok = client.get(f"/api/evidence/snapshots/{sid}/verify").json()
    assert ok["status"] == "INTEGRITY_VERIFIED" and ok["current_hash"] == snap["bundle_hash"]
    assert ok["audit_chain"]["valid"]

    # Later auditor activity does not alter the frozen snapshot.
    client.post(f"/api/findings/{hero['finding_id']}/disposition", json={"decision": "VERIFIED", "auditor": "B"})
    assert client.get(f"/api/evidence/snapshots/{sid}/verify").json()["match"] is True

    tampered = client.post("/api/demo/tamper", json={}).json()
    assert tampered["document_id"] == "DOC-V001-COMP"
    bad = client.get(f"/api/evidence/snapshots/{sid}/verify").json()
    assert bad["status"] == "INTEGRITY_MISMATCH"
    assert bad["changed_documents"][0]["document_id"] == "DOC-V001-COMP"
    assert "documents" in bad["changed_components"]

    client.post("/api/demo/restore")
    assert client.get(f"/api/evidence/snapshots/{sid}/verify").json()["match"] is True


def test_not_found_and_validation(client):
    assert client.get("/api/tenders/NOPE").status_code == 404
    assert client.get("/api/findings/NOPE").status_code == 404
    r = client.post(f"/api/findings/{TENDER}-F01/disposition", json={"decision": "GUILTY", "auditor": "x"})
    assert r.status_code == 422


def test_exploration_upload(client):
    from app.config import get_settings

    pdf = (get_settings().documents_dir / TENDER / f"Tender_{TENDER}.pdf").read_bytes()
    up = client.post("/api/uploads/tender", files={"file": ("my tender.pdf", pdf, "application/pdf")},
                     data={"tender_id": "UP-TEST-1", "title": "Uploaded tender"})
    assert up.status_code == 200, up.text
    assert up.json()["rulebook"]["rules_extracted"] == 18
    csv_text = ("name,amount_cr,submitted_at,avg_annual_turnover_cr,iso9001_valid_until\n"
                "Test Infra Pvt Ltd,12.5,2026-03-14T10:00:00+05:30,11,2027-01-01\n"
                "Other Works LLP,13.0,2026-03-16T10:00:00+05:30,8,2025-01-01\n")
    added = client.post("/api/uploads/UP-TEST-1/bidders.csv", files={"file": ("b.csv", csv_text, "text/csv")})
    assert added.status_code == 200, added.text
    report = client.post("/api/tenders/UP-TEST-1/analyze").json()
    assert report["stages"][2]["summary"]["evaluations"] == 36
    matrix = client.get("/api/tenders/UP-TEST-1/compliance").json()
    statuses = {v["name"]: v["status"] for v in matrix["vendors"]}
    assert statuses["Other Works LLP"] == "NOT_QUALIFIED"
    assert statuses["Test Infra Pvt Ltd"] == "INCOMPLETE_EVIDENCE"
    assert client.post("/api/uploads/tender", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 400
