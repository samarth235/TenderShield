"""Evaluate extraction precision and capability classification on hand-labelled real tender lines.

Usage (from backend/):  python -m scripts.evaluate_real_lines [--split test] [--json out.json]
Labels: data/annotations/india_wb_notice_lines.csv (see data/annotations/README.md).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter

from app.restructuring.classifier import CPV_PATH, classify, model_card
from app.restructuring.taxonomy import OTHER

LABELS = CPV_PATH.parents[1] / "annotations" / "india_wb_notice_lines.csv"

def f1_table(gold: list[str], pred: list[str]) -> dict:
    classes = sorted(set(gold))
    per = {}
    for c in classes:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"support": tp + fn, "precision": round(prec, 3), "recall": round(rec, 3),
                  "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0}
    return {"accuracy": round(sum(g == p for g, p in zip(gold, pred)) / len(gold), 3),
            "macro_f1": round(sum(v["f1"] for v in per.values()) / len(per), 3), "per_class": per}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--json")
    args = ap.parse_args()
    rows = [r for r in csv.DictReader(open(LABELS, encoding="utf-8")) if r["split"] == args.split]
    scope = [r for r in rows if r["label"] != "NOT_SCOPE"]
    preds = [c for c, *_ in classify([r["text"] for r in scope])]
    result = {
        "split": args.split, "notices": len({r["notice_id"] for r in rows}), "lines": len(rows),
        "extraction_precision": round(len(scope) / len(rows), 3),
        "not_scope_by_source": dict(Counter(r["extractor_source"] for r in rows if r["label"] == "NOT_SCOPE")),
        "classification": f1_table([r["label"] for r in scope], preds),
        "predicted_other": sum(p == OTHER for p in preds),
        "model": {k: (model_card() or {}).get(k) for k in ("trained_at",)},
        "errors": [{"text": r["text"][:120], "gold": r["label"], "pred": p} for r, p in zip(scope, preds) if r["label"] != p],
    }
    print(json.dumps({k: v for k, v in result.items() if k != "errors"}, indent=1))
    print(f"{len(result['errors'])} misclassified lines")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=1)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
