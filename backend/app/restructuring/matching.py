"""Stage 6-7: supplier capability matching and its evidence.

For a candidate package (one or more capabilities, with values), find suppliers whose *published
award records* show the needed capability, and test scale with the CPWD "similar work" rule used
in Indian works tenders: at least one similar completed work of 80% of the estimated cost, or two
of 50%, or three of 40% (CPWD Works Manual). That rule is applied per capability to the supplier's
largest awards in that capability.

The output is a potential supplier pool with evidence, never a winner:
  POTENTIALLY_SUITABLE      evidence for every capability and the scale rule is met
  LIMITED_SCALE_EVIDENCE    evidence for every capability, scale rule not met by published awards
  PARTIAL_CAPABILITY        evidence for some of the package's capabilities only
"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from ..market.profiles import is_sme_candidate
from .competition import expected_bidders
from .taxonomy import LABELS

SIMILAR_WORK_RULE = ((1, 0.8), (2, 0.5), (3, 0.4))
RECENT_YEARS = int(os.environ.get("TS_RECENT_YEARS", "7"))
WEIGHTS = {"coverage": 0.45, "depth": 0.20, "scale": 0.25, "recency": 0.10}


@dataclass
class MarketIndex:
    """In-memory view of the market store, built once per restructuring run."""
    countries: tuple[str, ...] | None = None
    by_cap: dict[str, dict[str, dict]] = field(default_factory=lambda: defaultdict(dict))
    suppliers: dict[str, dict] = field(default_factory=dict)
    total_awards: int = 0

    @classmethod
    def load(cls, conn: sqlite3.Connection | None, countries: tuple[str, ...] | None = None) -> "MarketIndex":
        idx = cls(countries=countries)
        if conn is None:
            return idx
        where, params = "", []
        if countries:
            where = " WHERE lower(COALESCE(country, '')) IN (%s)" % ",".join("?" * len(countries))
            params = [c.lower() for c in countries]
        cur = conn.execute(
            "SELECT award_id, supplier_key, capability, amount_inr_cr, signed_on, title, description, buyer, source_id,"
            " tender_ref FROM market_awards" + where, params)
        for r in cur:
            idx.total_awards += 1
            slot = idx.by_cap[r["capability"]].setdefault(r["supplier_key"], {"n": 0, "values": [], "last": None, "awards": []})
            slot["n"] += 1
            if r["amount_inr_cr"] is not None:
                slot["values"].append(r["amount_inr_cr"])
            if r["signed_on"] and (slot["last"] is None or r["signed_on"] > slot["last"]):
                slot["last"] = r["signed_on"]
            if len(slot["awards"]) < 40:
                slot["awards"].append({"award_id": r["award_id"], "amount_inr_cr": r["amount_inr_cr"], "signed_on": r["signed_on"],
                                       "title": r["title"] or (r["description"] or "")[:160], "buyer": r["buyer"],
                                       "source_id": r["source_id"], "tender_ref": r["tender_ref"]})
        keys = {k for caps in idx.by_cap.values() for k in caps}
        for i in range(0, len(keys), 900):
            chunk = list(keys)[i:i + 900]
            for r in conn.execute("SELECT supplier_key, name, country, msme_status, msme_evidence, n_awards, max_inr_cr,"
                                  " sources FROM market_suppliers WHERE supplier_key IN (%s)" % ",".join("?" * len(chunk)), chunk):
                idx.suppliers[r["supplier_key"]] = dict(r)
        for caps in idx.by_cap.values():
            for slot in caps.values():
                slot["values"].sort(reverse=True)
        return idx

    def pool(self, cap: str) -> set[str]:
        return set(self.by_cap.get(cap, {}))


def similar_work_met(values_desc: list[float], package_value: float | None) -> tuple[bool | None, str]:
    if not package_value:
        return None, "package value unknown"
    for count, share in SIMILAR_WORK_RULE:
        if len(values_desc) >= count and values_desc[count - 1] >= share * package_value:
            return True, f"{count} award(s) ≥ {int(share * 100)}% of ₹{package_value:.2f} Cr"
    best = values_desc[0] if values_desc else None
    return False, (f"largest published award ₹{best:.2f} Cr < 80% of ₹{package_value:.2f} Cr" if best is not None
                   else "no award values published")


def _recent(last: str | None) -> bool:
    if not last:
        return False
    try:
        return (date.today().year - int(last[:4])) <= RECENT_YEARS
    except ValueError:
        return False


def match_package(idx: MarketIndex, cap_values: dict[str, float | None], top_k: int = 15) -> dict:
    """``cap_values``: capability -> value (₹ Cr) of that capability's share of the package."""
    caps = list(cap_values)
    total_value = sum(v or 0 for v in cap_values.values()) or None
    if total_value and all(cap_values[c] for c in caps):
        weights = {c: cap_values[c] / total_value for c in caps}
    else:  # unknown values: weight capabilities equally rather than letting one known value dominate
        weights = {c: 1 / len(caps) for c in caps}
    candidates = set().union(*(idx.pool(c) for c in caps)) if caps else set()
    scored = []
    for key in candidates:
        cov = sum(weights[c] for c in caps if key in idx.by_cap.get(c, {}))
        depth = sum(weights[c] * min(1.0, idx.by_cap[c][key]["n"] / 5) for c in caps if key in idx.by_cap.get(c, {}))
        scale_checks, scale_ok = {}, []
        for c in caps:
            slot = idx.by_cap.get(c, {}).get(key)
            if slot is None:
                scale_checks[c] = {"met": False, "reason": "no published award in this capability"}
                scale_ok.append(0.0)
                continue
            met, why = similar_work_met(slot["values"], cap_values[c])
            scale_checks[c] = {"met": met, "reason": why}
            scale_ok.append(weights[c] * (1.0 if met else 0.0 if met is False else 0.5))
        scale = sum(scale_ok)
        recency = sum(weights[c] for c in caps if key in idx.by_cap.get(c, {}) and _recent(idx.by_cap[c][key]["last"]))
        score = (WEIGHTS["coverage"] * cov + WEIGHTS["depth"] * depth + WEIGHTS["scale"] * scale
                 + WEIGHTS["recency"] * recency)
        full = cov >= 0.999
        all_scale = all(v["met"] for v in scale_checks.values())
        status = ("POTENTIALLY_SUITABLE" if full and all_scale else
                  "LIMITED_SCALE_EVIDENCE" if full else "PARTIAL_CAPABILITY")
        scored.append((score, key, cov, depth, scale, recency, scale_checks, status))
    scored.sort(key=lambda t: (-t[0], t[1]))

    counts = defaultdict(int)
    sme_counts = defaultdict(int)
    for s in scored:
        counts[s[7]] += 1
        sup = idx.suppliers.get(s[1], {})
        if is_sme_candidate(sup.get("msme_status", "UNKNOWN")):
            sme_counts[s[7]] += 1

    shortlist = []
    for score, key, cov, depth, scale, rec, checks, status in scored[:top_k]:
        sup = idx.suppliers.get(key, {"name": key, "country": None, "msme_status": "UNKNOWN"})
        evidence = []
        for c in caps:
            slot = idx.by_cap.get(c, {}).get(key)
            if not slot:
                continue
            best = sorted(slot["awards"], key=lambda a: -(a["amount_inr_cr"] or 0))[:3]
            evidence.append({"capability": c, "label": LABELS.get(c, c), "awards_in_capability": slot["n"],
                             "largest_awards_inr_cr": [round(v, 3) for v in slot["values"][:3]],
                             "last_award": slot["last"], "scale_check": checks[c], "example_awards": best})
        shortlist.append({
            "supplier_key": key, "name": sup.get("name"), "country": sup.get("country"),
            "msme_status": sup.get("msme_status", "UNKNOWN"), "status": status, "score": round(score, 3),
            "components": {"capability_coverage": round(cov, 3), "evidence_depth": round(depth, 3),
                           "scale_fit": round(scale, 3), "recency": round(rec, 3)},
            "missing_capabilities": [c for c in caps if key not in idx.by_cap.get(c, {})],
            "evidence": evidence,
        })
    return {"capabilities": caps, "package_value_inr_cr": total_value, "pool": dict(counts),
            "sme_pool": dict(sme_counts), "shortlist": shortlist, "candidates_considered": len(candidates)}


def bundling_factor(idx: MarketIndex, caps: list[str], cap_values: dict[str, float | None]) -> tuple[float, dict]:
    """Share of the dominant capability's supplier pool that also has evidence for every other capability."""
    if len(caps) <= 1:
        return 1.0, {"reason": "single capability"}
    dominant = max(caps, key=lambda c: (cap_values.get(c) or 0, len(idx.pool(c))))
    base = idx.pool(dominant)
    if not base:
        return 1.0, {"reason": "no market data for dominant capability", "dominant": dominant}
    covering = set(base)
    for c in caps:
        covering &= idx.pool(c)
    factor = max(0.1, len(covering) / len(base))
    return factor, {"dominant": dominant, "dominant_pool": len(base), "covering_all": len(covering),
                    "factor": round(factor, 3)}


def package_competition(idx: MarketIndex, cap_values: dict[str, float | None]) -> dict:
    caps = list(cap_values)
    total = sum(v or 0 for v in cap_values.values()) or None
    dominant = max(caps, key=lambda c: cap_values.get(c) or 0)
    base = expected_bidders(dominant, total)
    factor, detail = bundling_factor(idx, caps, cap_values)
    return {"expected_bidders": round(base * factor, 3), "single_capability_expectation": round(base, 3),
            "bundling": detail, "dominant_capability": dominant}
