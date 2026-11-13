"""Competition model: expected number of bidders for a single-capability package of a given value.

Training data (real): 92,802 Prozorro (Ukraine) public procurement lots, 2019-2023, with the
number of bids each lot received, its expected value and its CPV division - derived from the
public Prozorro API and published under CC BY 4.0 by the Thesis Institute.

Model: histogram gradient boosting with a Poisson loss on [log10(value in ₹ Cr), capability].
Evaluated on a time split (train 2019-2021, test 2022+) against a per-capability mean baseline.

How it is used: the model gives the expected bidders for a package that needs one capability.
Bundling several capabilities into one package also shrinks the pool to firms that can deliver
all of them - that penalty is measured separately from real supplier co-capability evidence in the
market store (``bundling_factor``), not assumed.

Limitations stated on every output: the competition curve is learned from Ukrainian lots and is
used as a *relative* indicator (scenario A vs B), not as a forecast of Indian bidder counts. It
should be recalibrated with Indian bid-opening data when available.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..market.fx import to_inr_cr
from .classifier import MODELS_DIR, REPO_DIR
from .taxonomy import CAPABILITY_KEYS, capability_for_cpv

MODEL_PATH = MODELS_DIR / "competition_model.joblib"
CARD_PATH = MODELS_DIR / "competition_model.card.json"
LOTS_PATH = Path(os.environ.get("TS_PROZORRO_DIR", REPO_DIR / "data" / "real" / "raw" / "prozorro")) / "lots.csv.gz"


def _features(log_values: list[float], caps: list[str]) -> np.ndarray:
    onehot = np.zeros((len(caps), len(CAPABILITY_KEYS)))
    for i, c in enumerate(caps):
        onehot[i, CAPABILITY_KEYS.index(c)] = 1.0
    return np.column_stack([np.asarray(log_values), onehot])


def load_lots(path: Path = LOTS_PATH) -> list[dict]:
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r["lot_expected_value"] or not r["n_bids_lot"] or r.get("cancelled") == "1.0":
                continue
            v = to_inr_cr(float(r["lot_expected_value"]), "UAH")
            if not v or v <= 0:
                continue
            out.append({"log_v": math.log10(v), "cap": capability_for_cpv(r["cpv_division"]),
                        "n": float(r["n_bids_lot"]), "year": int(r["year"])})
    return out


def train(lots_path: Path = LOTS_PATH, out_dir: Path = MODELS_DIR) -> dict:
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_poisson_deviance

    lots = load_lots(lots_path)
    train_rows = [r for r in lots if r["year"] <= 2021]
    test_rows = [r for r in lots if r["year"] >= 2022]

    def xy(rows):
        return _features([r["log_v"] for r in rows], [r["cap"] for r in rows]), np.array([r["n"] for r in rows])

    Xtr, ytr = xy(train_rows)
    Xte, yte = xy(test_rows)
    params = dict(loss="poisson", max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=80,
                  categorical_features=None, random_state=7)
    model = HistGradientBoostingRegressor(**params).fit(Xtr, ytr)
    pred = model.predict(Xte)
    cap_mean = {c: float(np.mean([r["n"] for r in train_rows if r["cap"] == c] or [np.mean(ytr)])) for c in CAPABILITY_KEYS}
    base = np.array([cap_mean[r["cap"]] for r in test_rows])
    metrics = {
        "train_rows": len(train_rows), "test_rows": len(test_rows), "split": "time: train 2019-2021, test 2022+",
        "poisson_deviance": round(float(mean_poisson_deviance(yte, pred)), 4),
        "poisson_deviance_baseline": round(float(mean_poisson_deviance(yte, base)), 4),
        "mae": round(float(mean_absolute_error(yte, pred)), 4),
        "mae_baseline": round(float(mean_absolute_error(yte, base)), 4),
        "mean_bidders_test": round(float(np.mean(yte)), 3),
    }
    final = HistGradientBoostingRegressor(**params).fit(*xy(lots))
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, out_dir / MODEL_PATH.name, compress=3)
    curves = {c: [{"value_inr_cr": v, "expected_bidders": round(b, 3)} for v, b in
                  zip(CURVE_POINTS, final.predict(_features([math.log10(v) for v in CURVE_POINTS], [c] * len(CURVE_POINTS))))]
              for c in CAPABILITY_KEYS}
    card = {
        "model": "competition_model",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "HistGradientBoostingRegressor (Poisson loss) on log10(value ₹ Cr) + capability one-hot",
        "training_data": [{"name": "Prozorro lots (Ukraine public procurement, 2019-2023)",
                           "origin": "Prozorro public API; derived table by Thesis Institute, CC BY 4.0",
                           "url": "https://github.com/ThesisInstitute/procurement", "rows": len(lots),
                           "value_conversion": "UAH -> ₹ at the reference rate in app/market/fx.py"}],
        "metrics": metrics,
        "learned_curves": curves,
        "limitations": [
            "Learned on Ukrainian open tenders; used as a relative indicator between scenarios, not a forecast "
            "of Indian bidder counts. Recalibrate with CPPP bid-opening data.",
            "Lots in the data carry one CPV division, so the model has no notion of bundling; the bundling "
            "penalty comes from real supplier co-capability evidence instead.",
            "Observational data: larger lots in this data attract slightly more bidders; that is a "
            "correlation (buyers, procedures and markets differ), not a causal effect of lot size.",
        ],
    }
    (out_dir / CARD_PATH.name).write_text(json.dumps(card, indent=2, ensure_ascii=False))
    load_model.cache_clear()
    return card


CURVE_POINTS = [0.1, 0.3, 1, 3, 10, 30, 100, 300]


@lru_cache(maxsize=1)
def load_model():
    if not MODEL_PATH.exists():
        return None
    import logging

    import joblib

    try:
        return joblib.load(MODEL_PATH)
    except Exception as exc:  # noqa: BLE001 - e.g. scikit-learn version mismatch with the committed pickle
        logging.getLogger(__name__).warning("Could not load %s (%s); run `python -m scripts.build_market` to retrain",
                                            MODEL_PATH.name, exc)
        return None


def model_card() -> dict | None:
    return json.loads(CARD_PATH.read_text(encoding="utf-8")) if CARD_PATH.exists() else None


FALLBACK_BIDDERS = 2.5  # mean bidders per lot in the training data; used only if the model file is missing


def expected_bidders(capability: str, value_inr_cr: float | None) -> float:
    model = load_model()
    if model is None or not value_inr_cr or value_inr_cr <= 0:
        return FALLBACK_BIDDERS
    cap = capability if capability in CAPABILITY_KEYS else CAPABILITY_KEYS[-1]
    return float(model.predict(_features([math.log10(value_inr_cr)], [cap]))[0])
