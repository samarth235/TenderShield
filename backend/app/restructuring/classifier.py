"""Capability classifier: tender / award text -> capability (and CPV division).

Training data (real, official): the EU Common Procurement Vocabulary, CPV 2008 (Commission
Regulation (EC) No 213/2008): 9,454 coded descriptions of works, goods and services. Each code's
capability label comes from ``taxonomy.capability_for_cpv`` (a deterministic prefix mapping), so no
labels are hand-assigned. Extra labelled rows (e.g. annotated Indian BOQ lines in
``data/annotations/capability_gold.csv``) are added when present and reported separately.

Model: TF-IDF (word 1-2 grams + character 3-5 grams) -> multinomial logistic regression.
At inference the model's probabilities are blended with the curated Indian-phrasing lexicon from
``taxonomy`` (a bounded boost, never an override) because CPV wording ("site preparation work")
differs from CPWD BOQ wording ("excavation in foundation trenches").
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from .taxonomy import CAPABILITY_KEYS, LABELS, OTHER, capability_for_cpv, lexicon_hits

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
MODELS_DIR = Path(os.environ.get("TS_MODELS_DIR", BACKEND_DIR / "models"))
MODEL_PATH = MODELS_DIR / "capability_classifier.joblib"
CARD_PATH = MODELS_DIR / "capability_classifier.card.json"
CPV_PATH = REPO_DIR / "data" / "real" / "cpv_2008_codes.csv"
GOLD_PATH = REPO_DIR / "data" / "annotations" / "capability_gold.csv"

LEXICON_BOOST = 0.8  # per matching capability (max 2 keyword hits), then renormalised; tuned on the train half of
# data/annotations/india_wb_notice_lines.csv with a CPV-only model (0.25: 0.717, 0.4: 0.755, 0.8: 0.774, 1.0: 0.736)


# Indian tender lines open with procedural lead-ins ("Providing and installation of", "Supply, installation,
# testing and commissioning of", "C/O") while CPV - the training vocabulary - names the object alone. The model
# sees the object phrase; the lexicon still reads the full text.
_LEAD_IN = re.compile(
    r"^\W*(?:(?:providing|provision|supply(?:ing)?|delivery|install(?:ation|ing)?|testing|commissioning|erection|"
    r"fabrication|design(?:ing)?|procurement|construction|c/o|laying|jointing|and|&|,|of|for|the|with|"
    r"including|incl\.?|complete|necessary|required|all)\b[\s,&/]*)+", re.I)


def model_text(text: str) -> str:
    stripped = _LEAD_IN.sub("", text).strip()
    return stripped if len(stripped) >= 8 else text


def load_cpv(path: Path = CPV_PATH) -> tuple[list[str], list[str], list[str]]:
    texts, labels, codes = [], [], []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            texts.append(r["label"])
            labels.append(capability_for_cpv(r["code"]))
            codes.append(r["code"])
    return texts, labels, codes


def load_gold(path: Path = GOLD_PATH) -> tuple[list[str], list[str]]:
    if not path.exists():
        return [], []
    texts, labels = [], []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("text") and r.get("capability") in CAPABILITY_KEYS:
                texts.append(r["text"])
                labels.append(r["capability"])
    return texts, labels


def build_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, stop_words="english")),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])
    return Pipeline([("features", features),
                     ("clf", LogisticRegression(C=8.0, max_iter=3000, class_weight="balanced"))])


def train(out_dir: Path = MODELS_DIR, cpv_path: Path = CPV_PATH, gold_path: Path = GOLD_PATH, folds: int = 5) -> dict:
    import joblib
    from sklearn.metrics import classification_report, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    texts, labels, _ = load_cpv(cpv_path)
    texts = [model_text(t) for t in texts]
    gold_texts, gold_labels = load_gold(gold_path)

    # Cross-validated quality on the CPV vocabulary itself.
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=7)
    predicted = cross_val_predict(build_pipeline(), texts, labels, cv=cv, n_jobs=1)
    report = classification_report(labels, predicted, output_dict=True, zero_division=0)
    metrics = {"cv_folds": folds, "cv_accuracy": round(report["accuracy"], 4),
               "cv_macro_f1": round(f1_score(labels, predicted, average="macro"), 4),
               "per_class_f1": {k: round(v["f1-score"], 4) for k, v in report.items() if k in CAPABILITY_KEYS}}

    gold_metrics = None
    if gold_texts:
        # Train on CPV only, test on the human-annotated tender lines: the honest transfer estimate.
        model_cpv = build_pipeline().fit(texts, labels)
        preds = [_blend(model_cpv, [t])[0][0] for t in gold_texts]
        gold_metrics = {"rows": len(gold_texts),
                        "accuracy": round(float(np.mean([p == g for p, g in zip(preds, gold_labels)])), 4),
                        "macro_f1": round(f1_score(gold_labels, preds, average="macro"), 4)}

    # Real tender lines are few next to 9,454 CPV phrases; weight them so they shift the decision
    # boundary for Indian phrasing (TS_GOLD_WEIGHT, default 8).
    gold_weight = float(os.environ.get("TS_GOLD_WEIGHT", "8"))
    weights = [1.0] * len(texts) + [gold_weight] * len(gold_texts)
    model = build_pipeline().fit(texts + [model_text(t) for t in gold_texts], labels + gold_labels, clf__sample_weight=weights)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / MODEL_PATH.name, compress=3)
    card = {
        "model": "capability_classifier",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "TF-IDF (word 1-2g + char 3-5g) + multinomial logistic regression, lexicon-blended at inference",
        "training_data": [{
            "name": "Common Procurement Vocabulary (CPV 2008)",
            "origin": "Commission Regulation (EC) No 213/2008 - official EU procurement vocabulary",
            "rows": len(texts), "labels": "capability from CPV code prefix (taxonomy.py), no manual labels",
        }] + ([{"name": "Annotated tender lines", "path": str(gold_path.relative_to(REPO_DIR)),
                "rows": len(gold_texts), "sample_weight": gold_weight}] if gold_texts else []),
        "class_counts": {k: labels.count(k) for k in CAPABILITY_KEYS},
        "metrics": metrics,
        "transfer_eval_on_annotated_tender_lines": gold_metrics or
            "not run - add rows to data/annotations/capability_gold.csv (text,capability) and retrain",
        "limitations": [
            "CPV descriptions are short catalogue phrases; long Indian BOQ lines are a domain shift - "
            "the lexicon blend and the annotated-line evaluation exist for this reason.",
            "Single label per text; a mixed BOQ line is assigned its dominant capability.",
        ],
    }
    (out_dir / CARD_PATH.name).write_text(json.dumps(card, indent=2))
    load_model.cache_clear()
    return card


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
    return json.loads(CARD_PATH.read_text()) if CARD_PATH.exists() else None


def _blend(model, texts: list[str]) -> list[tuple[str, float, dict[str, float], dict[str, list[str]]]]:
    classes = list(model.classes_) if model is not None else list(CAPABILITY_KEYS)
    if model is not None:
        probs = model.predict_proba([model_text(t) for t in texts])
    else:
        probs = np.full((len(texts), len(classes)), 1.0 / len(classes))
    out = []
    for text, p in zip(texts, probs):
        p = p.copy()
        hits = lexicon_hits(text)
        for cap, kws in hits.items():
            if cap in classes:
                p[classes.index(cap)] += LEXICON_BOOST * min(len(kws), 2)
        p = p / p.sum()
        order = np.argsort(-p)
        dist = {str(classes[i]): round(float(p[i]), 4) for i in order[:3]}
        out.append((str(classes[order[0]]), float(p[order[0]]), dist, hits))
    return out


def classify(texts: list[str]) -> list[tuple[str, float, dict[str, float], dict[str, list[str]]]]:
    """Return (capability, confidence, top-3 distribution, lexicon hits) per text."""
    if not texts:
        return []
    return _blend(load_model(), texts)


def classify_simple(texts: list[str]) -> list[tuple[str, float]]:
    return [(c, conf) for c, conf, _, _ in classify(texts)]


def label(key: str) -> str:
    return LABELS.get(key, LABELS[OTHER])
