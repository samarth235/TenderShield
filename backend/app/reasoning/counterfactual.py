"""Counterfactual Evidence Analysis (Stage 11) - the Finding Robustness Test.

"Does this finding still hold if one supporting evidence item is removed?"
Re-applies the same explicit scoring rule to the remaining evidence and reports how the
level changes, which items are critical, and the smallest removal set that breaks it.
"""

from __future__ import annotations

from itertools import combinations

from .scoring import INDEPENDENT_FAMILIES, assess, level_rank

STILL_SUPPORTED, DOWNGRADED, DISSOLVED = "STILL_SUPPORTED", "DOWNGRADED", "DISSOLVED"


class NotTestable(ValueError):
    pass


def _check_testable(finding: dict) -> None:
    if finding["category"] != "INVESTIGATION_SIGNAL":
        raise NotTestable(
            "Robustness testing applies to investigation signals. Compliance findings are deterministic rule "
            "results and data-quality warnings describe missing evidence."
        )


def _explain(original: dict, after: dict, remaining: list[dict]) -> str:
    if after["level"] == original["level"]:
        return (f"Finding still supported at {after['level']}: {len(remaining)} evidence item(s) across "
                f"{', '.join(after['families']) or 'no'} evidence families remain (support {after['support']:.2f}).")
    if after["level"] == "NONE":
        return "No supporting evidence remains; the finding dissolves."
    if after["level"] == "LOW":
        what = "one weak supporting signal remains" if len(remaining) == 1 else \
            "the remaining evidence is not independently corroborated"
        return f"Finding downgraded from {original['level']} to LOW: {what}."
    missing = [f for f in INDEPENDENT_FAMILIES if f in original["families"] and f not in after["families"]]
    reason = f"{', '.join(missing)} evidence removed" if missing else f"support fell to {after['support']:.2f}"
    return f"Finding downgraded from {original['level']} to {after['level']}: {reason}."


def evaluate_removal(finding: dict, remove_ids: list[str]) -> dict:
    _check_testable(finding)
    known = {i["evidence_id"] for i in finding["evidence"]}
    unknown = sorted(set(remove_ids) - known)
    if unknown:
        raise KeyError(f"Unknown evidence ids: {', '.join(unknown)}")
    original = assess(finding["evidence"])
    remaining = [i for i in finding["evidence"] if i["evidence_id"] not in set(remove_ids)]
    after = assess(remaining)
    if after["level"] == original["level"]:
        status = STILL_SUPPORTED
    elif after["level"] == "NONE":
        status = DISSOLVED
    else:
        status = DOWNGRADED if level_rank(after["level"]) < level_rank(original["level"]) else STILL_SUPPORTED
    return {
        "finding_id": finding["finding_id"],
        "removed": [{"evidence_id": i["evidence_id"], "label": i["label"], "family": i["family"]}
                    for i in finding["evidence"] if i["evidence_id"] in set(remove_ids)],
        "remaining": [{"evidence_id": i["evidence_id"], "label": i["label"], "family": i["family"], "weight": i["weight"]}
                      for i in remaining],
        "original": original,
        "counterfactual": after,
        "status": status,
        "explanation": _explain(original, after, remaining),
    }


def robustness_report(finding: dict) -> dict:
    _check_testable(finding)
    items = finding["evidence"]
    original = assess(items)
    leave_one_out = []
    for item in items:
        result = evaluate_removal(finding, [item["evidence_id"]])
        leave_one_out.append({
            "evidence_id": item["evidence_id"], "label": item["label"], "family": item["family"],
            "weight": item["weight"], "level_after": result["counterfactual"]["level"],
            "support_after": result["counterfactual"]["support"], "status": result["status"],
            "critical": result["status"] != STILL_SUPPORTED,
        })

    family_ablation = []
    for family in [*INDEPENDENT_FAMILIES, "model"]:
        ids = [i["evidence_id"] for i in items if i["family"] == family]
        if ids:
            r = evaluate_removal(finding, ids)
            family_ablation.append({"family": family, "removed": ids, "level_after": r["counterfactual"]["level"],
                                    "status": r["status"], "explanation": r["explanation"]})

    # Smallest set of evidence whose removal drops the finding below escalation (MEDIUM).
    breaking_set = None
    if level_rank(original["level"]) >= level_rank("MEDIUM"):
        ids = [i["evidence_id"] for i in items]
        for size in range(1, len(ids) + 1):
            candidates = [
                list(combo) for combo in combinations(ids, size)
                if level_rank(assess([i for i in items if i["evidence_id"] not in combo])["level"]) < level_rank("MEDIUM")
            ]
            if candidates:
                weight = {i["evidence_id"]: i["weight"] for i in items}
                best = min(candidates, key=lambda c: sum(weight[e] for e in c))
                breaking_set = {"size": size, "evidence_ids": best,
                                "labels": [i["label"] for i in items if i["evidence_id"] in best]}
                break

    survived = sum(not r["critical"] for r in leave_one_out)
    return {
        "finding_id": finding["finding_id"],
        "original": original,
        "robustness_score": round(survived / len(leave_one_out), 3) if leave_one_out else 0.0,
        "interpretation": (
            "Robust: no single evidence item is decisive." if survived == len(leave_one_out)
            else f"{len(leave_one_out) - survived} evidence item(s) are individually decisive."
        ),
        "leave_one_out": leave_one_out,
        "family_ablation": family_ablation,
        "minimal_breaking_set": breaking_set,
    }
