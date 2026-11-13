"""Secondary objective: observable cross-relationships among shortlisted suppliers.

Uses only what the published market records show:
  * co_bidding          the two firms bid on the same tender/lot (bid-level data, e.g. Prozorro / OCDS bids)
  * win_rotation        within those shared lots, the wins alternate between the two firms
  * joint_venture       a published award to a JV / consortium naming both firms
  * same_project        both won contracts on the same project (e.g. World Bank Project ID)
  * name_overlap        near-identical normalised company names (possible same group / entity)

Every edge is a *potential relationship requiring review* with its evidence and the ordinary
explanations listed next to it. Nothing here is a finding of collusion. For bidder-level checks
(directors, addresses, contacts, document similarity) the original TenderShield pipeline runs on the
actual bids once they are received.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from itertools import combinations

import networkx as nx
from rapidfuzz import fuzz

from ..entities.resolution import company_core
from ..market.sources import jv_partners

ALTERNATIVES = {
    "co_bidding": ["Firms specialising in the same niche meet often in open tenders",
                   "Few qualified firms in a region make repeated encounters likely"],
    "win_rotation": ["Alternating wins can follow from capacity limits or differing price strategies"],
    "joint_venture": ["JVs are lawful and common for large or multi-discipline works; disclose and assess, not exclude"],
    "same_project": ["Large projects legitimately award separate packages to different firms"],
    "name_overlap": ["Similar names can be unrelated firms; confirm with registry identifiers (CIN/GSTIN)"],
}
REVIEW_LEVEL = {"joint_venture": 0.35, "co_bidding": 0.25, "win_rotation": 0.25, "same_project": 0.10, "name_overlap": 0.20}


def screen_relationships(conn: sqlite3.Connection | None, supplier_keys: list[str], names: dict[str, str],
                         min_cobids: int = 2) -> dict:
    keys = sorted(set(supplier_keys))
    edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
    if conn is not None and len(keys) >= 2:
        qs = ",".join("?" * len(keys))
        lots: dict[tuple, list[tuple[str, int | None]]] = defaultdict(list)
        for r in conn.execute(f"SELECT tender_ref, lot_ref, supplier_key, won FROM market_bids WHERE supplier_key IN ({qs})", keys):
            lots[(r["tender_ref"], r["lot_ref"])].append((r["supplier_key"], r["won"]))
        shared: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        for lot, entries in lots.items():
            by_sup = {k: w for k, w in entries}
            for a, b in combinations(sorted(by_sup), 2):
                shared[(a, b)].append((lot, by_sup[a], by_sup[b]))
        for pair, rows in shared.items():
            if len(rows) < min_cobids:
                continue
            edges[pair].append({"type": "co_bidding", "count": len(rows),
                                "examples": [{"tender_ref": lot[0], "lot_ref": lot[1]} for lot, _, _ in rows[:5]]})
            wins_a = sum(1 for _, wa, _ in rows if wa)
            wins_b = sum(1 for _, _, wb in rows if wb)
            if wins_a >= 1 and wins_b >= 1 and wins_a + wins_b >= 0.8 * len(rows):
                edges[pair].append({"type": "win_rotation", "wins": {pair[0]: wins_a, pair[1]: wins_b},
                                    "shared_lots": len(rows)})

        core_to_key = {company_core(names.get(k, "")): k for k in keys if names.get(k)}
        for r in conn.execute("SELECT award_id, supplier_name, project_id, supplier_key FROM market_awards"
                              " WHERE supplier_name LIKE '%JV%' OR supplier_name LIKE '%onsortium%'"
                              " OR supplier_name LIKE '%oint venture%' LIMIT 20000"):
            partners = {core_to_key.get(company_core(p)) for p in jv_partners(r["supplier_name"])} - {None}
            for a, b in combinations(sorted(partners), 2):
                edges[(a, b)].append({"type": "joint_venture", "award_id": r["award_id"], "jv_name": r["supplier_name"]})

        projects: dict[str, set[str]] = defaultdict(set)
        for r in conn.execute(f"SELECT project_id, supplier_key FROM market_awards WHERE project_id IS NOT NULL"
                              f" AND supplier_key IN ({qs})", keys):
            projects[r["project_id"]].add(r["supplier_key"])
        for pid, sups in projects.items():
            for a, b in combinations(sorted(sups), 2):
                edges[(a, b)].append({"type": "same_project", "project_id": pid})

    cores = {k: company_core(names.get(k, "")) for k in keys}
    for a, b in combinations(keys, 2):
        if cores[a] and cores[b] and fuzz.token_sort_ratio(cores[a], cores[b]) >= 92:
            edges[(a, b)].append({"type": "name_overlap", "a": names.get(a), "b": names.get(b),
                                  "similarity": round(fuzz.token_sort_ratio(cores[a], cores[b]), 1)})

    out = []
    g = nx.Graph()
    for (a, b), ev in edges.items():
        types = sorted({e["type"] for e in ev})
        level = min(1.0, sum(REVIEW_LEVEL[t] for t in types))
        out.append({"a": a, "b": b, "a_name": names.get(a), "b_name": names.get(b), "types": types,
                    "evidence": ev[:8], "review_score": round(level, 3),
                    "signal": "Potential relationship requiring review" if level >= 0.35 else "Observed link (context)",
                    "alternative_explanations": sorted({x for t in types for x in ALTERNATIVES[t]})})
        g.add_edge(a, b, weight=level)
    out.sort(key=lambda e: -e["review_score"])
    clusters = [sorted(c) for c in nx.connected_components(g) if len(c) >= 3]
    return {"screened_suppliers": len(keys), "edges": out, "clusters": clusters,
            "requires_review": sum(1 for e in out if e["review_score"] >= 0.35),
            "note": "Signals for human review only. Relationships are not evidence of wrongdoing."}
