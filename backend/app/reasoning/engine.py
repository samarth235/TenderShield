"""Evidence Reasoning Engine (Stages 9-10).

Turns individual signals into findings with an explicit reasoning chain, linked source
records, data-quality assessment, alternative explanations and recommended checks.

Findings are separated into three categories (spec section 13):
  COMPLIANCE            objective rule result (mandatory rule FAIL)
  INVESTIGATION_SIGNAL  pattern deserving human examination (REVIEW)
  DATA_QUALITY          evidence incomplete or uncertain (INSUFFICIENT DATA)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from itertools import combinations

from ..db import dumps, fetch_all, get_artifact, put_artifact
from ..nlp.extract import load_rules
from .scoring import EVIDENCE_TYPES, MODERATE_DOCUMENT_WEIGHT, assess, level_rank, scoring_rule

DOC_SIM_STRONG, DOC_SIM_MODERATE = 0.75, 0.65
DOC_SIM_STRONG_LIFT, DOC_SIM_MODERATE_LIFT = 0.25, 0.15

DISCLAIMER = (
    "This finding is an investigation signal, not a determination of misconduct. Relationships and similarities "
    "can have legitimate explanations; the final decision rests with the human auditor."
)

ALTERNATIVES = {
    "SHARED_DIRECTOR": "The vendors may be legitimate group companies under common management, or share an independent director.",
    "SHARED_ADDRESS": "Shared office arrangements, co-working premises or a common registered-office service provider.",
    "SHARED_CONTACT": "A common administrative or bid-preparation service provider may be used by both vendors.",
    "REPEATED_CO_BIDDING": "Both vendors may specialise in the same work category and region; repeated participation can be legitimate.",
    "WINNER_ROTATION": "A small pool of qualified competitors in a segment can produce recurring outcome pairs.",
    "PRICE_PROXIMITY": "Prices converge when estimates are published and margins are thin.",
    "SUBMISSION_TIMING": "Last-day submission is common; close timing may be coincidental.",
    "DOCUMENT_SIMILARITY": "Common templates may explain some textual similarity "
                           "(industry-standard proposals, a shared consultant or subcontractor).",
    "BEHAVIOUR_ANOMALY": "Statistical outliers occur naturally; the model flags unusual combinations, not intent.",
}


def _pair_label(vendors: dict, a: str, b: str) -> str:
    return f"{vendors[a]['alias'] or vendors[a]['name']} <-> {vendors[b]['alias'] or vendors[b]['name']}"


def _vendor_ref(vendors: dict, vid: str) -> dict:
    v = vendors[vid]
    return {"vendor_id": vid, "alias": v["alias"], "name": v["name"]}


# ---------------------------------------------------------------------------------
# Investigation signals
# ---------------------------------------------------------------------------------

def collect_pair_evidence(a: str, b: str, links: list[dict], behaviour: dict | None, similarity: dict | None,
                          sim_baseline: float | None) -> list[dict]:
    items: list[dict] = []

    def add(etype: str, statement: str, sources: list[dict], metrics: dict | None = None, weight: float | None = None,
            strength: str = "strong", verification: list[str] | None = None) -> None:
        spec = EVIDENCE_TYPES[etype]
        items.append({
            "evidence_id": f"E{len(items) + 1}", "type": etype, "label": spec["label"], "family": spec["family"],
            "weight": spec["weight"] if weight is None else weight, "strength": strength, "statement": statement,
            "metrics": metrics or {}, "sources": sources, "alternative_explanation": ALTERNATIVES[etype],
            "recommended_verification": verification or [],
        })

    for link in links:
        records = link["records"]
        if link["type"] == "director":
            din = link["entity"].get("din")
            names = sorted({r["raw_name"] for r in records})
            add("SHARED_DIRECTOR",
                f"Both vendors list the same director ({' / '.join(names)}{f', DIN {din}' if din else ''}).",
                [{"kind": "vendor_registry", "vendor_id": r["vendor_id"], "field": "directors", "value": r["raw_name"],
                  "din": r.get("din")} for r in records],
                {"entity_id": link["entity_id"], "din": din,
                 "match_method": "identifier (DIN)" if din else "name similarity"},
                verification=[f"Verify directorship records{f' for DIN {din}' if din else ''} in the company registry (MCA)."])
        elif link["type"] == "address":
            add("SHARED_ADDRESS",
                "Registered addresses resolve to the same premises: " + " | ".join(r["raw"] for r in records) + ".",
                [{"kind": "vendor_registry", "vendor_id": r["vendor_id"], "field": "registered_address", "value": r["raw"]}
                 for r in records],
                {"entity_id": link["entity_id"], "pincode": link["entity"].get("pincode"),
                 "match_scores": link["entity"].get("match_scores")},
                verification=["Inspect registered-office proofs / lease agreements for the shared premises."])
        elif link["type"] == "contact":
            add("SHARED_CONTACT", f"Both vendors use the same {link['entity']['kind'].replace('_', ' ')} "
                f"({link['entity']['value']}).",
                [{"kind": "vendor_registry", "vendor_id": r["vendor_id"], "field": "contact", "value": r["raw"]}
                 for r in records],
                {"entity_id": link["entity_id"]},
                verification=["Confirm who operates the shared phone / e-mail account."])

    pair = next((p for p in (behaviour or {}).get("pairs", []) if p["vendors"] == [a, b]), None)
    if pair:
        history_sources = [{"kind": "award_record", "tender_id": h["tender_id"], "outcomes": {a: h[a], b: h[b]},
                            "amounts_cr": h["amounts_cr"], "submitted_at": h["submitted_at"]} for h in pair["history"]]
        flags = pair["flags"]
        if flags["repeated_co_bidding"]:
            add("REPEATED_CO_BIDDING",
                f"The vendors bid together in {pair['co_bids']} historical tenders "
                f"(about {pair['expected_co_bids']:g} expected if they participated independently).",
                history_sources, {"co_bids": pair["co_bids"], "expected_co_bids": pair["expected_co_bids"],
                                  "jaccard": pair["jaccard"]},
                verification=[f"Review bid-opening statements of the {pair['co_bids']} common tenders."])
        if flags["winner_rotation"]:
            add("WINNER_ROTATION",
                f"In {pair['rotation_count']} of {pair['co_bids']} common tenders one vendor won and the other was "
                "runner-up, with the winning position alternating between them.",
                [s for s in history_sources if set(s["outcomes"].values()) == {"WON", "RUNNER_UP"}],
                {"rotation_count": pair["rotation_count"], "co_bids": pair["co_bids"]},
                verification=["Compare the award sequence and check whether the runner-up bids were genuinely competitive."])
        if flags["price_proximity"]:
            add("PRICE_PROXIMITY",
                f"Median price gap in common tenders is {pair['price_gap_median'] * 100:.1f}% "
                f"(current tender: {pair['current_tender']['price_gap'] * 100:.1f}%).",
                history_sources, {"price_gap_median": pair["price_gap_median"],
                                  "current_price_gap": pair["current_tender"]["price_gap"]},
                verification=["Examine price build-ups for identical item rates or rounding patterns."])
        if flags["submission_timing"]:
            add("SUBMISSION_TIMING",
                f"Median gap between the two submissions is {pair['submission_gap_median_min']:g} minutes "
                f"(current tender: {pair['current_tender']['submission_gap_min']:g} minutes).",
                history_sources + [{"kind": "document", "document_id": "DOC-SUBMISSION-LOG", "page": 1,
                                    "detail": "Current tender submission timestamps"}],
                {"submission_gap_median_min": pair["submission_gap_median_min"],
                 "current_submission_gap_min": pair["current_tender"]["submission_gap_min"]},
                verification=["Obtain portal logs (IP address, digital signature certificate) for both submissions."])
        anomaly = pair.get("anomaly")
        if anomaly and anomaly["is_outlier"] and anomaly["coordinated_direction"]:
            add("BEHAVIOUR_ANOMALY",
                f"Isolation Forest ranks this pair #{anomaly['rank']} most unusual of "
                f"{behaviour['model']['training_pairs']} co-bidding pairs.",
                [{"kind": "model", "model": behaviour["model"]["type"], "features": behaviour["model"]["features"]}],
                {"anomaly_score": anomaly["score"], "rank": anomaly["rank"], "percentile": anomaly["percentile"],
                 "top_contributors": anomaly["top_contributors"]},
                strength="supporting")

    sim = next((p for p in (similarity or {}).get("pairs", []) if sorted(p["vendors"]) == [a, b]), None)
    if sim:
        score = sim["document_similarity"]
        lift = score - (sim_baseline or 0.0)
        strength = ("strong" if score >= DOC_SIM_STRONG and lift >= DOC_SIM_STRONG_LIFT
                    else "moderate" if score >= DOC_SIM_MODERATE and lift >= DOC_SIM_MODERATE_LIFT else None)
        if strength:
            add("DOCUMENT_SIMILARITY",
                f"Technical proposals are {score * 100:.1f}% semantically similar (tender median "
                f"{(sim_baseline or 0) * 100:.1f}%). High-overlap sections: {', '.join(sim['high_overlap_sections']) or 'none'}.",
                [{"kind": "document", "document_id": d, "filename": f} for d, f in zip(sim["documents"], sim["filenames"])]
                + [{"kind": "passage", **p} for p in sim["passages"][:4]],
                {"document_similarity": score, "tender_median": sim_baseline,
                 "high_overlap_sections": sim["high_overlap_sections"]},
                weight=None if strength == "strong" else MODERATE_DOCUMENT_WEIGHT, strength=strength,
                verification=["Compare the original submitted proposals side by side for sections: "
                              + ", ".join(sim["high_overlap_sections"][:4]) + "."])
    return items


REASONING_STAGES = [
    ("corporate", "Corporate overlap", {"SHARED_DIRECTOR", "SHARED_ADDRESS", "SHARED_CONTACT"}),
    ("participation", "Repeated joint participation", {"REPEATED_CO_BIDDING"}),
    ("document", "High bid-document similarity", {"DOCUMENT_SIMILARITY"}),
    ("outcomes", "Unusual historical outcome sequence", {"WINNER_ROTATION", "PRICE_PROXIMITY", "SUBMISSION_TIMING"}),
    ("model", "Population-level anomaly", {"BEHAVIOUR_ANOMALY"}),
]


def reasoning_chain(items: list[dict], assessment: dict) -> dict:
    steps = []
    for key, label, types in REASONING_STAGES:
        used = [i for i in items if i["type"] in types]
        if used:
            steps.append({"step": len(steps) + 1, "key": key, "label": label,
                          "evidence_ids": [i["evidence_id"] for i in used],
                          "statement": " ".join(i["statement"] for i in used)})
    conclusion = {
        "HIGH": "Investigation signal - multiple independent evidence families corroborate each other.",
        "MEDIUM": "Investigation signal - corroborated, but with limited behavioural support.",
        "LOW": "Relationship noted - evidence is not independently corroborated; no escalation recommended.",
        "NONE": "No signal.",
    }[assessment["level"]]
    nodes = [{"id": i["evidence_id"], "kind": "evidence", "label": i["label"], "family": i["family"]} for i in items]
    nodes += [{"id": f"S{s['step']}", "kind": "step", "label": s["label"]} for s in steps]
    nodes.append({"id": "C", "kind": "conclusion", "label": f"{assessment['level']}: {conclusion}"})
    edges = [{"source": eid, "target": f"S{s['step']}"} for s in steps for eid in s["evidence_ids"]]
    edges += [{"source": f"S{a['step']}", "target": f"S{b['step']}"} for a, b in zip(steps, steps[1:])]
    if steps:
        edges.append({"source": f"S{steps[-1]['step']}", "target": "C"})
    return {"steps": steps, "conclusion": conclusion, "graph": {"nodes": nodes, "edges": edges}}


def signal_data_quality(vendors: dict, a: str, b: str, items: list[dict]) -> dict:
    notes = []
    for vid in (a, b):
        if not vendors[vid]["directors"]:
            notes.append(f"{vendors[vid]['alias'] or vid}: director information unavailable - corporate links may be under-counted.")
    fuzzy = [i for i in items if i["type"] == "SHARED_DIRECTOR" and i["metrics"].get("match_method") != "identifier (DIN)"]
    if fuzzy:
        notes.append("Director link relies on name similarity rather than a registry identifier.")
    level = "LOW" if any("unavailable" in n for n in notes) else "MEDIUM" if notes else "HIGH"
    return {"level": level, "notes": notes or ["All linked records resolved via registry identifiers or exact normalisation."]}


# ---------------------------------------------------------------------------------
# Finding generation
# ---------------------------------------------------------------------------------

def generate_findings(conn: sqlite3.Connection, tender_id: str) -> dict:
    vendors = {v["vendor_id"]: v for v in fetch_all(conn, "SELECT * FROM vendors")}
    entities = get_artifact(conn, tender_id, "entities") or {"shared_links": [], "data_quality": []}
    behaviour = get_artifact(conn, tender_id, "behaviour")
    similarity = get_artifact(conn, tender_id, "similarity")
    rules = {r["rule_id"]: r for r in load_rules(conn, tender_id)}
    bidders = sorted({r["vendor_id"] for r in fetch_all(
        conn, "SELECT vendor_id FROM bids WHERE tender_id = ? AND vendor_id IS NOT NULL", (tender_id,))})
    links = {tuple(l["vendors"]): l["links"] for l in entities["shared_links"]}
    baseline = (similarity or {}).get("baseline", {}).get("median")

    signals, compliance, quality = [], [], []

    for a, b in combinations(bidders, 2):
        items = collect_pair_evidence(a, b, links.get((a, b), []), behaviour, similarity, baseline)
        if not items:
            continue
        assessment = assess(items)
        escalated = level_rank(assessment["level"]) >= level_rank("MEDIUM")
        checks = [c for i in items for c in i["recommended_verification"]]
        if escalated:
            checks.append("Check tender-specific rules on participation by related parties.")
        signals.append({
            "category": "INVESTIGATION_SIGNAL",
            "title": f"{_pair_label(vendors, a, b)}: "
                     + ("potential coordinated-bidding indicator" if escalated else "relationship noted"),
            "signal": "Potential coordinated-bidding indicator" if escalated else "Relationship noted (not escalated)",
            "recommendation": "REVIEW" if escalated else "NO_ACTION",
            "level": assessment["level"],
            "subject": {"type": "vendor_pair", "vendors": [_vendor_ref(vendors, a), _vendor_ref(vendors, b)]},
            "evidence": items,
            "assessment": {**assessment, "rule": scoring_rule()["levels"]},
            "reasoning": reasoning_chain(items, assessment),
            "data_quality": signal_data_quality(vendors, a, b, items),
            "alternative_explanations": sorted({i["alternative_explanation"] for i in items}),
            "recommended_verification": list(dict.fromkeys(checks)),
            "disclaimer": DISCLAIMER,
        })
    signals.sort(key=lambda f: (-level_rank(f["level"]), -f["assessment"]["support"]))

    for row in fetch_all(conn, "SELECT vendor_id, rule_id, result, body FROM compliance WHERE tender_id = ? "
                         "ORDER BY vendor_id, rule_id", (tender_id,)):
        ev, rule = row["body"], rules[row["rule_id"]]
        if row["result"] != "FAIL" or not rule["mandatory"]:
            continue
        v = vendors[row["vendor_id"]]
        clause_src = {"kind": "tender_clause", "document_id": rule["source"]["document_id"],
                      "filename": rule["source"]["filename"], "page": rule["source"]["page"],
                      "clause": rule["source"]["clause"], "text": rule["clause_text"]}
        items = [{
            "evidence_id": "E1", "type": "RULE_EVALUATION", "label": rule["requirement"], "family": "compliance",
            "weight": 1.0, "strength": "deterministic", "statement": ev["reason"],
            "metrics": {"expected": ev["expected"], "actual": ev["actual"]},
            "sources": [clause_src] + [{"kind": "document", **e} for e in ev["evidence"]],
        }]
        compliance.append({
            "category": "COMPLIANCE",
            "title": f"{v['alias'] or v['name']}: {rule['requirement']} - FAIL",
            "signal": "Mandatory requirement not satisfied",
            "recommendation": "VERIFY",
            "level": "FAIL",
            "subject": {"type": "vendor", "vendors": [_vendor_ref(vendors, row["vendor_id"])], "rule_id": rule["rule_id"]},
            "evidence": items,
            "assessment": {"deterministic": True, "rule_id": rule["rule_id"], "result": "FAIL"},
            "reasoning": {
                "steps": [
                    {"step": 1, "key": "clause", "label": "Tender clause",
                     "statement": f"Clause {rule['source']['clause']} (page {rule['source']['page']}): {rule['clause_text']}"},
                    {"step": 2, "key": "rule", "label": "Machine rule", "statement": f"{rule['rule_id']}: {rule['condition']}"},
                    {"step": 3, "key": "value", "label": "Vendor value", "statement": f"Declared value: {ev['actual']}"},
                    {"step": 4, "key": "result", "label": "Result", "statement": ev["reason"]},
                ],
                "conclusion": "Deterministic compliance failure on a mandatory requirement.",
            },
            "data_quality": {"level": "HIGH", "notes": ["Value read directly from the bidder's submitted document."]},
            "alternative_explanations": [
                "A valid or renewed document may exist but was not included in the submission.",
                "The tender may permit curing of documentary deficiencies before evaluation.",
            ],
            "recommended_verification": [
                "Confirm the value with the issuing authority (e.g. certification body, bank, CA).",
                "Check the tender's provisions on clarification / curable deficiencies.",
            ],
            "disclaimer": "Compliance results are rule outputs; the evaluation committee decides the consequence.",
        })

    registry_issues = {d["vendor_id"]: d for d in entities.get("data_quality", [])}
    unknowns: dict[str, list[dict]] = {}
    for row in fetch_all(conn, "SELECT vendor_id, rule_id, body FROM compliance WHERE tender_id = ? AND result = 'UNKNOWN'",
                         (tender_id,)):
        if rules[row["rule_id"]]["mandatory"]:
            unknowns.setdefault(row["vendor_id"], []).append(row["body"])
    for vid in bidders:
        if vid not in registry_issues and vid not in unknowns:
            continue
        v = vendors[vid]
        items = []
        if vid in registry_issues:
            items.append({"evidence_id": f"E{len(items) + 1}", "type": "REGISTRY_GAP", "label": "Director information unavailable",
                          "family": "data_quality", "weight": 0.0, "strength": "n/a",
                          "statement": registry_issues[vid]["detail"],
                          "sources": [{"kind": "vendor_registry", "vendor_id": vid, "field": "directors", "value": None}]})
        for ev in unknowns.get(vid, []):
            rule = rules[ev["rule_id"]]
            items.append({"evidence_id": f"E{len(items) + 1}", "type": "UNKNOWN_RESULT", "label": rule["requirement"],
                          "family": "data_quality", "weight": 0.0, "strength": "n/a", "statement": ev["reason"],
                          "sources": [{"kind": "tender_clause", "document_id": rule["source"]["document_id"],
                                       "page": rule["source"]["page"], "clause": rule["source"]["clause"]}]})
        quality.append({
            "category": "DATA_QUALITY",
            "title": f"{v['alias'] or v['name']}: insufficient data - " + "; ".join(i["label"] for i in items),
            "signal": "Evidence incomplete",
            "recommendation": "REQUEST_INFORMATION",
            "level": "INSUFFICIENT_DATA",
            "subject": {"type": "vendor", "vendors": [_vendor_ref(vendors, vid)]},
            "evidence": items,
            "assessment": {"deterministic": True, "result": "UNKNOWN"},
            "reasoning": {
                "steps": [{"step": n + 1, "key": i["type"].lower(), "label": i["label"], "statement": i["statement"]}
                          for n, i in enumerate(items)],
                "conclusion": "Missing data is not treated as wrongdoing; it limits what the system can verify.",
            },
            "data_quality": {"level": "LOW", "notes": ["Relationship analysis for this vendor may be incomplete."]},
            "alternative_explanations": ["The information may exist but was not captured in the registry extract or the submission."],
            "recommended_verification": ["Request the missing disclosure from the bidder.",
                                         "Query the company registry for current directors and beneficial owners."],
            "disclaimer": "Data-quality warnings are not adverse findings.",
        })

    findings = signals + compliance + quality
    conn.execute("DELETE FROM findings WHERE tender_id = ?", (tender_id,))
    for n, finding in enumerate(findings, start=1):
        finding["finding_id"] = f"{tender_id}-F{n:02d}"
        finding["tender_id"] = tender_id
        finding["status"] = "OPEN"
        conn.execute(
            "INSERT INTO findings (finding_id, tender_id, category, level, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            (finding["finding_id"], tender_id, finding["category"], finding["level"], "OPEN", dumps(finding)),
        )
    summary = {
        "tender_id": tender_id,
        "findings": len(findings),
        "by_category": {
            "INVESTIGATION_SIGNAL": len(signals), "COMPLIANCE": len(compliance), "DATA_QUALITY": len(quality),
        },
        "escalated_signals": sum(level_rank(f["level"]) >= level_rank("MEDIUM") for f in signals),
        "scoring_rule": scoring_rule(),
    }
    put_artifact(conn, tender_id, "findings", summary, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return summary


def load_finding(conn: sqlite3.Connection, finding_id: str) -> dict | None:
    row = conn.execute("SELECT status, body FROM findings WHERE finding_id = ?", (finding_id,)).fetchone()
    if row is None:
        return None
    body = json.loads(row["body"])
    body["status"] = row["status"]
    return body
