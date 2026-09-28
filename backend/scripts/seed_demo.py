"""Load the demonstration tender and run the full analysis pipeline.

Usage (from backend/):  python -m scripts.seed_demo
"""

from __future__ import annotations

import json

from app.db import init_db
from app.demo.generator import load_demo
from app.demo.scenario import DEMO_TENDER_ID
from app.pipeline import run_analysis


def main() -> None:
    init_db()
    summary = load_demo()
    summary.pop("documents")
    print(json.dumps(summary, indent=2))
    report = run_analysis(DEMO_TENDER_ID)
    for stage in report["stages"]:
        print(f"  {stage['stage']:<22} {stage['duration_ms']:>8.1f} ms  {json.dumps(stage['summary'])[:110]}")
    print(f"Pipeline finished in {report['duration_ms']:.0f} ms")


if __name__ == "__main__":
    main()
