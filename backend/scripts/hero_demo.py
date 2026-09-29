"""Rehearse the 3-4 minute hero demo (spec section 28) against the API.

Usage (from backend/):
  python -m scripts.hero_demo                      # in-process, no server needed
  python -m scripts.hero_demo --url http://localhost:8000
"""

from __future__ import annotations

import argparse
import sys

TENDER = "TN-2026-014"


def make_client(url: str | None):
    if url:
        import httpx

        return httpx.Client(base_url=url, timeout=60)
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def step(n: int, text: str) -> None:
    print(f"\n[{n:02d}] {text}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Base URL of a running backend (default: in-process)")
    args = parser.parse_args()
    c = make_client(args.url)

    def ok(resp):
        if resp.status_code >= 400:
            print(f"  !! {resp.status_code} {resp.text}")
            sys.exit(1)
        return resp.json()

    step(1, "LOAD DEMONSTRATION TENDER")
    loaded = ok(c.post("/api/demo/load"))
    print(f"  Tender ID: {loaded['tender_id']} | Bidders: {loaded['bidders']} | "
          f"Documents: {loaded['tender_documents']} | Historical tenders: {loaded['historical_tenders']}")

    step(2, "Analyse (AI extraction -> compliance -> graph -> intelligence -> reasoning)")
    report = ok(c.post(f"/api/tenders/{TENDER}/analyze"))
    for s in report["stages"]:
        print(f"  {s['stage']:<22} {s['duration_ms']:>7.1f} ms")

    step(3, "Rulebook: tender clause -> machine rule -> source page")
    rules = ok(c.get(f"/api/tenders/{TENDER}/rules"))["rules"]
    r = next(x for x in rules if x["metric"] == "similar_projects_value_cr")
    print(f"  {len(rules)} rules extracted. Example {r['rule_id']}: \"{r['clause_text'][:90]}...\"")
    print(f"    -> {r['condition']}   [{r['source']['filename']}, page {r['source']['page']}, clause {r['source']['clause']}]")

    step(4, "Compliance matrix")
    matrix = ok(c.get(f"/api/tenders/{TENDER}/compliance"))
    print(f"  {matrix['evaluations']} checks completed")
    for v in matrix["vendors"]:
        print(f"    {v['alias']:<9} {v['status']:<20} {v['counts']}")

    step(5, "Vendor graph: Vendor A <-> Vendor B relationship network")
    paths = ok(c.get(f"/api/tenders/{TENDER}/graph/paths", params={"a": "V001", "b": "V002"}))["paths"]
    for p in paths:
        print(f"    via {p['via']['type']}: {p['via']['label']}")

    step(6, "Open the top investigation finding")
    findings = ok(c.get(f"/api/tenders/{TENDER}/findings"))
    for f in findings:
        print(f"    {f['finding_id']}  {f['category']:<21} {f['level']:<18} {f['title']}")
    hero = findings[0]["finding_id"]
    card = ok(c.get(f"/api/findings/{hero}"))
    for e in card["evidence"]:
        print(f"    [{e['evidence_id']}] {e['label']}: {e['statement'][:100]}")

    step(7, "WHY WAS THIS FLAGGED?")
    reasoning = ok(c.get(f"/api/findings/{hero}/reasoning"))
    for s in reasoning["steps"]:
        print(f"    {s['label']}  <- {', '.join(s['evidence_ids'])}")
    print(f"    => {reasoning['conclusion']}")

    step(8, "TEST ROBUSTNESS: remove the shared director")
    director = next(e["evidence_id"] for e in card["evidence"] if e["type"] == "SHARED_DIRECTOR")
    cf = ok(c.post(f"/api/findings/{hero}/counterfactual", json={"remove": [director]}))
    print(f"    {cf['status']}: {cf['explanation']}")

    step(9, "Remove the major behavioural signals")
    behavioural = [e["evidence_id"] for e in card["evidence"] if e["family"] in ("behavioural", "model")]
    cf = ok(c.post(f"/api/findings/{hero}/counterfactual", json={"remove": behavioural}))
    print(f"    {cf['status']}: {cf['explanation']}")

    step(10, "Auditor selects FURTHER REVIEW")
    ok(c.post(f"/api/findings/{hero}/disposition",
              json={"decision": "FURTHER_REVIEW", "auditor": "Demo Auditor", "notes": "Verify MCA records"}))

    step(11, "Dossier data + evidence commitment")
    dossier = ok(c.get(f"/api/tenders/{TENDER}/dossier-data"))
    print(f"    Dossier sections: {', '.join(k for k in dossier if k != 'generated_at')}")
    snap = ok(c.post(f"/api/tenders/{TENDER}/evidence/finalize", json={"auditor": "Demo Auditor"}))
    print(f"    Snapshot {snap['snapshot_id']}  evidence hash {snap['bundle_hash'][:4].upper()}...{snap['bundle_hash'][-4:].upper()}")

    step(12, "VERIFY (original)")
    v = ok(c.get(f"/api/evidence/snapshots/{snap['snapshot_id']}/verify"))
    print(f"    {v['status']}  current {v['current_hash'][:12]} == committed {v['committed_hash'][:12]}")

    step(13, "Modify one document, then VERIFY")
    t = ok(c.post("/api/demo/tamper", json={}))
    print(f"    Tampered {t['filename']}: {t['change']}")
    v = ok(c.get(f"/api/evidence/snapshots/{snap['snapshot_id']}/verify"))
    print(f"    {v['status']}  current {v['current_hash'][:12]} != committed {v['committed_hash'][:12]}")
    print(f"    Changed: {[d['filename'] for d in v['changed_documents']]}")
    print("\n    Evidence integrity failure detected.")
    ok(c.post("/api/demo/restore"))

    step(14, "Bidder uploads a renewed V2 (new version, not a mismatch)")
    doc = t["document_id"]
    created = ok(c.post("/api/demo/new-version", json={"document_id": doc}))
    v = ok(c.get(f"/api/evidence/snapshots/{snap['snapshot_id']}/verify"))
    print(f"    {created['version']['label']} {created['version']['sha256'][:12]}  snapshot: {v['status']} (match={v['match']})")
    for ch in created["comparison"]["changes"]:
        print(f"    {ch['label']}: {ch['old_display']} -> {ch['new_display']}  [{ch['impact']}]")
    explained = ok(c.post(f"/api/documents/{doc}/versions/2/explain", json={}))["explanation"]
    print(f"    Explanation ({explained['method']}): {explained['summary']}")

    step(15, "Auditor accepts V2; it is sealed and anchored separately")
    accepted = ok(c.post(f"/api/documents/{doc}/versions/2/review",
                         json={"decision": "ACCEPT", "auditor": "Demo Auditor", "notes": "Renewal confirmed"}))
    print(f"    V2 {accepted['version']['status']}  MST record {accepted['version']['chain_payload']['case_id']}")
    print(f"    V1 still verifies: {ok(c.get(f'/api/documents/{doc}/versions/1/verify'))['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
