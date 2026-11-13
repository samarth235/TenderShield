"""Train the models and build the market store from the downloaded real datasets.

Usage (from backend/):
    python -m scripts.build_market                    # train models + load every dataset found
    python -m scripts.build_market --skip-train
    python -m scripts.build_market --awards-csv ../data/real/india/cppp_awards.csv
    python -m scripts.build_market --ocds path/to/releases.jsonl --ocds-country India

Steps
  1. capability classifier  <- data/real/cpv_2008_codes.csv (+ data/annotations/capability_gold.csv)
  2. competition model      <- data/real/raw/prozorro/lots.csv.gz
  3. market store           <- World Bank awards (India), Prozorro contracts + bids, OCDS / CSV extras
  4. supplier profiles      <- aggregated from 3
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.market import profiles, sources
from app.market.store import market_db_path, market_session, status
from app.restructuring import classifier, competition

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "real" / "raw"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-train", action="store_true")
    ap.add_argument("--wb-country", default="India", help="World Bank borrower country to load ('' = all)")
    ap.add_argument("--no-prozorro", action="store_true")
    ap.add_argument("--awards-csv", nargs="*", default=[], help="CSV(s) compiled from official award notices")
    ap.add_argument("--ocds", nargs="*", default=[], help="OCDS release/record package files")
    ap.add_argument("--ocds-country", default=None)
    args = ap.parse_args(argv)

    if not args.skip_train:
        t = time.time()
        card = classifier.train()
        print(f"[model] capability classifier  CV macro-F1 {card['metrics']['cv_macro_f1']}  ({time.time() - t:.0f}s)")
        if competition.LOTS_PATH.exists():
            t = time.time()
            card = competition.train()
            m = card["metrics"]
            print(f"[model] competition model      Poisson deviance {m['poisson_deviance']} "
                  f"(baseline {m['poisson_deviance_baseline']}) on {m['test_rows']} held-out lots ({time.time() - t:.0f}s)")
        else:
            print(f"[model] competition model skipped: {competition.LOTS_PATH} missing (run fetch_real_data)")

    with market_session() as conn:
        wb = RAW / "worldbank" / "major_contract_awards.csv"
        if wb.exists():
            r = sources.ingest(conn, "worldbank_awards", wb, country=args.wb_country or None,
                               classify=classifier.classify_simple)
            print(f"[data ] World Bank awards ({args.wb_country or 'all'}): {r['awards']} awards")
        else:
            print(f"[data ] World Bank awards not found at {wb} (run fetch_real_data --only worldbank)")
        pz = RAW / "prozorro"
        if not args.no_prozorro and all((pz / f).exists() for f in sources.PROZORRO_FILES):
            r = sources.ingest(conn, "prozorro", pz, source_id="prozorro:ua")
            print(f"[data ] Prozorro: {r['awards']} contracts, {r['bids']} bids")
        for path in args.awards_csv:
            r = sources.ingest(conn, "awards_csv", Path(path), country="India", classify=classifier.classify_simple)
            print(f"[data ] {path}: {r['awards']} awards")
        for path in args.ocds:
            r = sources.ingest(conn, "ocds", Path(path), country=args.ocds_country, classify=classifier.classify_simple)
            print(f"[data ] {path}: {r['awards']} awards, {r['bids']} bids")
        p = profiles.rebuild_profiles(conn)
        print(f"[data ] supplier profiles: {p['suppliers']}")
        s = status(conn)
    print(json.dumps({"market_db": str(market_db_path()), **s["counts"]}, indent=2))


if __name__ == "__main__":
    main()
