"""Bid Behaviour Intelligence (Stage 8).

Builds historical pair features from resolved award records and scores them with an
Isolation Forest. The model surfaces *unusual combinations* of behaviour; it never
labels a vendor as fraudulent. Deterministic thresholds provide the individually
explainable signals; the model adds a corroborating population-level view.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

import numpy as np
from sklearn.ensemble import IsolationForest

from ..config import get_settings
from ..db import fetch_all, put_artifact

FEATURES = ["co_bids", "jaccard", "rotation_count", "price_proximity", "timing_proximity"]
FEATURE_LABELS = {
    "co_bids": "tenders bid together",
    "jaccard": "overlap of tender portfolios",
    "rotation_count": "winner/runner-up pairings",
    "price_proximity": "closeness of quoted prices",
    "timing_proximity": "closeness of submission times",
}
THRESHOLDS = {
    "repeated_co_bidding": 3,        # common tenders
    "co_bid_lift": 1.75,             # ... and at least 1.75x what independent participation predicts
    "rotation_min": 2,               # winner/runner-up pairings with alternation
    "price_gap_max": 0.03,           # median relative price gap
    "timing_gap_max_min": 15.0,      # median minutes between submissions
    "min_common_for_pattern": 2,
}


def _minutes(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()) / 60.0


def load_participation(conn: sqlite3.Connection, exclude_tender: str) -> dict[str, dict[str, dict]]:
    """tender_id -> vendor_id -> bid (historical, resolved records only)."""
    rows = fetch_all(
        conn,
        "SELECT b.* FROM bids b JOIN tenders t ON t.tender_id = b.tender_id"
        " WHERE b.vendor_id IS NOT NULL AND b.tender_id != ? AND t.status = 'AWARDED'",
        (exclude_tender,),
    )
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        out[r["tender_id"]][r["vendor_id"]] = r
    return out


def pair_features(participation: dict[str, dict[str, dict]]) -> tuple[dict[tuple[str, str], dict], dict[str, dict]]:
    vendor_stats: dict[str, dict] = defaultdict(lambda: {"participations": 0, "wins": 0, "runner_up": 0})
    common: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tender_id, bids in participation.items():
        for vid, bid in bids.items():
            vendor_stats[vid]["participations"] += 1
            vendor_stats[vid]["wins"] += bid["outcome"] == "WON"
            vendor_stats[vid]["runner_up"] += bid["outcome"] == "RUNNER_UP"
        for a, b in combinations(sorted(bids), 2):
            common[(a, b)].append(tender_id)

    n_tenders = max(len(participation), 1)
    features: dict[tuple[str, str], dict] = {}
    for (a, b), tenders in common.items():
        na, nb = vendor_stats[a]["participations"], vendor_stats[b]["participations"]
        rotation, winners, price_gaps, time_gaps, history = 0, set(), [], [], []
        for t in sorted(tenders):
            ba, bb = participation[t][a], participation[t][b]
            outcomes = {ba["outcome"], bb["outcome"]}
            if outcomes == {"WON", "RUNNER_UP"}:
                rotation += 1
                winners.add(a if ba["outcome"] == "WON" else b)
            if ba["amount_cr"] and bb["amount_cr"]:
                price_gaps.append(abs(ba["amount_cr"] - bb["amount_cr"]) / min(ba["amount_cr"], bb["amount_cr"]))
            if ba["submitted_at"] and bb["submitted_at"]:
                time_gaps.append(_minutes(ba["submitted_at"], bb["submitted_at"]))
            history.append({"tender_id": t, a: ba["outcome"], b: bb["outcome"],
                            "amounts_cr": {a: ba["amount_cr"], b: bb["amount_cr"]},
                            "submitted_at": {a: ba["submitted_at"], b: bb["submitted_at"]}})
        price_gap = statistics.median(price_gaps) if price_gaps else None
        time_gap = statistics.median(time_gaps) if time_gaps else None
        features[(a, b)] = {
            "co_bids": len(tenders),
            "expected_co_bids": round(na * nb / n_tenders, 2),
            "jaccard": round(len(tenders) / (na + nb - len(tenders)), 4),
            "rotation_count": rotation,
            "alternating_winners": len(winners) == 2,
            "price_gap_median": round(price_gap, 4) if price_gap is not None else None,
            "submission_gap_median_min": round(time_gap, 1) if time_gap is not None else None,
            "price_proximity": 1 - min(price_gap if price_gap is not None else 0.2, 0.2) / 0.2,
            "timing_proximity": 1 - min(time_gap if time_gap is not None else 1440, 1440) / 1440,
            "history": history,
        }
    return features, dict(vendor_stats)


def score_pairs(features: dict[tuple[str, str], dict], seed: int) -> dict:
    keys = sorted(features)
    if len(keys) < 10:
        return {"trained": False, "reason": "not enough co-bidding pairs to train the model"}
    X = np.array([[features[k][f] for f in FEATURES] for k in keys], dtype=float)
    model = IsolationForest(n_estimators=300, contamination=0.02, random_state=seed)
    model.fit(X)
    raw = -model.score_samples(X)  # higher = more anomalous
    predicted = model.predict(X)
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1
    order = raw.argsort()
    percentile = np.empty(len(raw))
    percentile[order] = np.arange(1, len(raw) + 1) / len(raw) * 100
    for i, k in enumerate(keys):
        z = (X[i] - mean) / std
        contributions = sorted(
            ({"feature": f, "label": FEATURE_LABELS[f], "z_score": round(float(z[j]), 2),
              "value": round(float(X[i, j]), 4), "population_mean": round(float(mean[j]), 4)}
             for j, f in enumerate(FEATURES)),
            key=lambda c: -c["z_score"],
        )
        features[k]["anomaly"] = {
            "score": round(float(raw[i]), 4),
            "rank": int(len(raw) - order.tolist().index(i)),
            "percentile": round(float(percentile[i]), 1),
            "is_outlier": bool(predicted[i] == -1),
            # Outliers only count as a signal when the unusual direction is "more coordinated".
            "coordinated_direction": sum(c["z_score"] > 1.5 for c in contributions) >= 2,
            "top_contributors": [c for c in contributions if c["z_score"] > 1.0][:4],
        }
    return {
        "trained": True, "type": "IsolationForest", "n_estimators": 300, "contamination": 0.02,
        "random_state": seed, "features": FEATURES, "training_pairs": len(keys),
        "outliers": int((predicted == -1).sum()),
    }


def deterministic_flags(f: dict) -> dict:
    t = THRESHOLDS
    enough = f["co_bids"] >= t["min_common_for_pattern"]
    return {
        "repeated_co_bidding": f["co_bids"] >= t["repeated_co_bidding"]
        and f["co_bids"] >= t["co_bid_lift"] * f["expected_co_bids"],
        "winner_rotation": f["rotation_count"] >= t["rotation_min"] and f["alternating_winners"],
        "price_proximity": enough and f["price_gap_median"] is not None and f["price_gap_median"] <= t["price_gap_max"],
        "submission_timing": enough and f["submission_gap_median_min"] is not None
        and f["submission_gap_median_min"] <= t["timing_gap_max_min"],
    }


def run_behaviour(conn: sqlite3.Connection, tender_id: str) -> dict:
    settings = get_settings()
    participation = load_participation(conn, tender_id)
    features, vendor_stats = pair_features(participation)
    model = score_pairs(features, settings.random_seed)

    current = {b["vendor_id"]: b for b in fetch_all(
        conn, "SELECT * FROM bids WHERE tender_id = ? AND vendor_id IS NOT NULL", (tender_id,))}
    bidders = sorted(current)
    pairs = []
    for a, b in combinations(bidders, 2):
        f = features.get((a, b))
        base = f or {
            "co_bids": 0, "expected_co_bids": 0.0, "jaccard": 0.0, "rotation_count": 0, "alternating_winners": False,
            "price_gap_median": None, "submission_gap_median_min": None, "price_proximity": 0.0,
            "timing_proximity": 0.0, "history": [], "anomaly": None,
        }
        ca, cb = current[a], current[b]
        pairs.append({
            "vendors": [a, b],
            **{k: v for k, v in base.items()},
            "flags": deterministic_flags(base),
            "current_tender": {
                "price_gap": round(abs(ca["amount_cr"] - cb["amount_cr"]) / min(ca["amount_cr"], cb["amount_cr"]), 4),
                "submission_gap_min": round(_minutes(ca["submitted_at"], cb["submitted_at"]), 1),
            },
        })
    result = {
        "tender_id": tender_id,
        "historical_tenders": len(participation),
        "model": model,
        "thresholds": THRESHOLDS,
        "pairs": pairs,
        "vendors": {
            vid: {**vendor_stats.get(vid, {"participations": 0, "wins": 0, "runner_up": 0}),
                  "win_rate": round(vendor_stats[vid]["wins"] / vendor_stats[vid]["participations"], 3)
                  if vendor_stats.get(vid, {}).get("participations") else 0.0}
            for vid in bidders
        },
        "population_outliers": [
            {"vendors": list(k), "co_bids": f["co_bids"], "percentile": f["anomaly"]["percentile"]}
            for k, f in sorted(features.items(), key=lambda kv: -kv[1].get("anomaly", {}).get("score", 0))
            if f.get("anomaly", {}).get("is_outlier")
        ][:15],
    }
    put_artifact(conn, tender_id, "behaviour", result, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return result
