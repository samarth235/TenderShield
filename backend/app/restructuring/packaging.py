"""Stage 5 + 8: candidate package formation and procurement-structure comparison.

Every feasible way of grouping the components into packages is enumerated (components joined by a
*strong* dependency always stay together), each structure is scored on the six criteria from the
project definition, and the alternatives are ranked:

    Procurement value =  w1 Competition benefit + w2 Capability coverage + w3 SME accessibility
                       - w4 Coordination cost   - w5 Integration risk    - w6 Loss of scale

All weights and thresholds are explicit (``DEFAULT_WEIGHTS`` / ``DEFAULT_PARAMS``) and can be changed
per request. A weight-sensitivity test re-ranks the structures under randomly perturbed weights
and reports how often the recommended structure stays on top.

The objective is not to maximise the number of packages: the single integrated contract is always
scored as Scenario A, and it wins whenever splitting does not pay for itself.
"""

from __future__ import annotations

import random

from .matching import MarketIndex, match_package, package_competition
from .taxonomy import LABELS

DEFAULT_WEIGHTS = {"competition": 0.20, "coverage": 0.25, "sme_access": 0.25,
                   "coordination": 0.10, "integration_risk": 0.15, "scale_loss": 0.05}
DEFAULT_PARAMS = {
    "bidder_saturation": 5.0,        # expected bidders at which competition benefit is full
    "min_capable_pool": 3,           # suppliers with full capability evidence for a competitive package
    "turnover_share_required": 0.30,  # typical eligibility: avg annual turnover >= 30% of estimated cost
    "small_enterprise_turnover_cr": 100.0,  # MSME 'small' turnover ceiling (MSMED Act, revised from 1 Apr 2025)
    "min_viable_package_cr": 2.0,    # below this a separate contract is unlikely to justify its overhead
    "per_package_overhead": 0.05,    # coordination cost per additional contract
    "max_supernodes": 8,
}
RISK_FACTOR = {"safety": 1.5, "interface": 1.0, "installation": 0.8, "schedule": 0.5, "independence": 0.0}


def set_partitions(items: list) -> list[list[list]]:
    if not items:
        return [[]]
    first, rest = items[0], items[1:]
    out = []
    for part in set_partitions(rest):
        for i in range(len(part)):
            out.append(part[:i] + [[first] + part[i]] + part[i + 1:])
        out.append([[first]] + part)
    return out


def _supernodes(components: list[dict], dep: dict, max_nodes: int) -> list[list[str]]:
    groups = [list(g) for g in dep["strong_groups"]]
    grouped = {c for g in groups for c in g}
    groups += [[c["component_id"]] for c in components if c["component_id"] not in grouped]
    value = {c["component_id"]: c["value_inr_cr"] or 0 for c in components}
    weight = {frozenset((e["source"], e["target"])): e["weight"] for e in dep["edges"]}
    while len(groups) > max_nodes:  # merge the smallest group into its most strongly coupled neighbour
        groups.sort(key=lambda g: sum(value[c] for c in g))
        small = groups.pop(0)
        best = max(groups, key=lambda g: max(weight.get(frozenset((a, b)), 0) for a in small for b in g))
        best.extend(small)
    return groups


def compare_structures(components: list[dict], dep: dict, idx: MarketIndex, weights: dict | None = None,
                       params: dict | None = None, sensitivity_draws: int = 300, seed: int = 9) -> dict:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    p = {**DEFAULT_PARAMS, **(params or {})}
    comp = {c["component_id"]: c for c in components}
    total_value = sum(c["value_inr_cr"] or 0 for c in components) or None
    edges = dep["edges"]
    # Normalise against cutting a spanning tree of the components: (n-1) links of full weight.
    span = max(1, len(components) - 1)
    strong = {frozenset((e["source"], e["target"])) for e in edges if e["strength"] == "strong"}
    sme_ceiling = p["small_enterprise_turnover_cr"] / p["turnover_share_required"]

    supernodes = _supernodes(components, dep, p["max_supernodes"])
    cache: dict[frozenset, dict] = {}

    def evaluate_package(ids: frozenset) -> dict:
        if ids in cache:
            return cache[ids]
        cap_values = {comp[i]["capability"]: comp[i]["value_inr_cr"] for i in ids}
        value = sum(v or 0 for v in cap_values.values()) or None
        match = match_package(idx, cap_values)
        competition = package_competition(idx, cap_values)
        capable = match["pool"].get("POTENTIALLY_SUITABLE", 0) + match["pool"].get("LIMITED_SCALE_EVIDENCE", 0)
        sme_capable = match["sme_pool"].get("POTENTIALLY_SUITABLE", 0) + match["sme_pool"].get("LIMITED_SCALE_EVIDENCE", 0)
        sme_size_ok = value is not None and value <= sme_ceiling
        cache[ids] = {"components": sorted(ids), "capabilities": sorted(cap_values), "value_inr_cr": value,
                      "match": match, "competition": competition, "capable_pool": capable, "sme_capable_pool": sme_capable,
                      "sme_size_accessible": sme_size_ok,
                      "required_turnover_cr": round(value * p["turnover_share_required"], 3) if value else None}
        return cache[ids]

    scenarios = []
    for partition in set_partitions(supernodes):
        packages = [frozenset(c for g in block for c in g) for block in partition]
        cut = [e for e in edges if not any({e["source"], e["target"]} <= pk for pk in packages)]
        if any(frozenset((e["source"], e["target"])) in strong for e in cut):
            continue
        evals = [evaluate_package(pk) for pk in packages]
        vals = [ev["value_inr_cr"] or 0 for ev in evals]
        share = [v / total_value if total_value else 1 / len(evals) for v in vals]
        m = {
            "competition": sum(s * min(1.0, ev["competition"]["expected_bidders"] / p["bidder_saturation"])
                               for s, ev in zip(share, evals)),
            "coverage": sum(s * min(1.0, ev["capable_pool"] / p["min_capable_pool"]) for s, ev in zip(share, evals)),
            "sme_access": sum(s for s, ev in zip(share, evals) if ev["sme_size_accessible"] and ev["sme_capable_pool"] >= 1),
            "coordination": min(1.0, sum(e["weight"] for e in cut) / span + p["per_package_overhead"] * (len(evals) - 1)),
            "integration_risk": min(1.0, sum(e["weight"] * max(RISK_FACTOR.get(t, 1.0) for t in e["types"]) for e in cut)
                                    / (max(RISK_FACTOR.values()) * span)),
            "scale_loss": sum(s for s, v in zip(share, vals) if len(evals) > 1 and v < p["min_viable_package_cr"]),
        }
        scenarios.append({"packages": evals, "metrics": {k: round(v, 4) for k, v in m.items()},
                          "cut_dependencies": [{"source": e["source"], "target": e["target"], "weight": e["weight"],
                                                "types": e["types"]} for e in cut]})

    def score(m: dict, wt: dict) -> float:
        return (wt["competition"] * m["competition"] + wt["coverage"] * m["coverage"] + wt["sme_access"] * m["sme_access"]
                - wt["coordination"] * m["coordination"] - wt["integration_risk"] * m["integration_risk"]
                - wt["scale_loss"] * m["scale_loss"])

    for s in scenarios:
        s["score"] = round(score(s["metrics"], w), 4)
        s["n_packages"] = len(s["packages"])
    scenarios.sort(key=lambda s: (-s["score"], s["n_packages"]))
    integrated = next(s for s in scenarios if s["n_packages"] == 1) if any(s["n_packages"] == 1 for s in scenarios) else None
    best = scenarios[0]
    finest = max(scenarios, key=lambda s: (s["n_packages"], s["score"]))

    # Weight sensitivity: how often does the recommended structure stay on top?
    rng = random.Random(seed)
    key_of = lambda s: tuple(sorted(tuple(pk["components"]) for pk in s["packages"]))  # noqa: E731
    best_key, wins, runner_ups = key_of(best), 0, {}
    for _ in range(sensitivity_draws):
        wt = {k: v * rng.uniform(0.5, 1.5) for k, v in w.items()}
        top = max(scenarios, key=lambda s: score(s["metrics"], wt))
        if key_of(top) == best_key:
            wins += 1
        else:
            runner_ups[key_of(top)] = runner_ups.get(key_of(top), 0) + 1

    def label_s(s, tag):
        names = [" + ".join(LABELS.get(c, c) for c in pk["capabilities"]) for pk in s["packages"]]
        return {**s, "tag": tag, "summary": f"{s['n_packages']} package(s): " + " | ".join(names)}

    named = {"A_integrated": label_s(integrated, "Current structure: one integrated contract") if integrated else None,
             "B_recommended": label_s(best, "Highest procurement value under the stated weights"),
             "C_max_separation": label_s(finest, "Finest split that respects strong dependencies")}
    return {
        "weights": w, "params": {**p, "sme_package_ceiling_cr": round(sme_ceiling, 2)},
        "supernodes": supernodes, "feasible_structures": len(scenarios),
        "scenarios": named,
        "ranking": [{"rank": i + 1, "score": s["score"], "n_packages": s["n_packages"], "metrics": s["metrics"],
                     "packages": [pk["components"] for pk in s["packages"]]} for i, s in enumerate(scenarios[:10])],
        "sensitivity": {"draws": sensitivity_draws, "perturbation": "each weight x U(0.5, 1.5)",
                        "recommended_stays_best": round(wins / sensitivity_draws, 3),
                        "most_common_alternative": max(runner_ups.items(), key=lambda kv: kv[1])[0] if runner_ups else None},
        "recommendation_differs_from_current": bool(integrated) and key_of(best) != key_of(integrated),
    }

