"""Download the real, public datasets TenderShield trains on and matches against.

Usage (from backend/):
    python -m scripts.fetch_real_data                 # everything
    python -m scripts.fetch_real_data --only prozorro worldbank

Every download is recorded in data/real/raw/MANIFEST.json with its URL, size, SHA-256 and time,
so the demo can show exactly which published files the models and supplier pools came from.

Sources
  cpv        EU Common Procurement Vocabulary (CPV 2008), 9,454 codes     -> capability classifier
  prozorro   Prozorro lots/tenders/bids/contracts (CC BY 4.0, Thesis Inst.) -> competition model, co-bidding
  worldbank  World Bank Major Contract Awards, all countries (CC BY 4.0)   -> Indian supplier capability evidence
  wb_notices World Bank procurement notices for India (API)               -> real tender texts for testing

The World Bank portals block some cloud/CI networks; run this on a normal internet connection.
If a download fails, use the browser and save the file at the path printed below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "real" / "raw"
TI = "https://raw.githubusercontent.com/ThesisInstitute/procurement/main/prozorro/results/"

SOURCES = {
    "cpv": [("https://raw.githubusercontent.com/KhawarMehfooz/tender-management-system/HEAD/database/data/cpv_codes.csv",
             REPO / "data" / "real" / "cpv_2008_codes.csv")],
    "prozorro": [(TI + f, RAW / "prozorro" / f) for f in ("lots.csv.gz", "tenders.csv.gz", "bids.csv.gz", "contracts.csv.gz")],
    "worldbank": [
        ("https://finances.worldbank.org/api/views/kdui-wcs3/rows.csv?accessType=DOWNLOAD",
         RAW / "worldbank" / "major_contract_awards.csv"),
    ],
    "wb_notices": [
        ("https://search.worldbank.org/api/v2/procnotices?" + urllib.parse.urlencode(
            {"format": "json", "project_ctry_name_exact": "India", "rows": 500, "os": 0,
             "fl": "id,bid_description,project_ctry_name,project_id,project_name,notice_type,notice_status,"
                   "submission_date,noticedate,procurement_group,procurement_method_name,notice_text"}),
         RAW / "worldbank" / "procurement_notices_india.json"),
    ],
}
FALLBACKS = {
    "worldbank": [("https://data.openstate.eu/dataset/f3525ebe-2c14-4f8f-8d2a-5b03a93a0304/resource/"
                   "8f73b2b2-fb01-4058-960e-664801aaa834/download/world_bank_major_contract_awards.csv",
                   RAW / "worldbank" / "major_contract_awards.csv")],
}


RETRIES = 4


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS ship without system CA certificates; use certifi's bundle when present.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}


def download(url: str, dest: Path) -> dict:
    """Download with exponential backoff on network errors and transient HTTP statuses."""
    for attempt in range(1, RETRIES + 1):
        try:
            return _download_once(url, dest)
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP or attempt == RETRIES:
                raise
            wait = int(exc.headers.get("Retry-After", 0) or 0) or 2 ** attempt
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == RETRIES:
                raise
            wait = 2 ** attempt
        print(f"  retry {attempt}/{RETRIES - 1} in {wait}s: {url}", file=sys.stderr)
        time.sleep(wait)
    raise AssertionError("unreachable")


def _download_once(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "TenderShield-Nexus/1.0 (research; open data)"})
    digest = hashlib.sha256()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=300, context=SSL_CONTEXT) as resp, open(tmp, "wb") as fh:
        for chunk in iter(lambda: resp.read(1 << 20), b""):
            fh.write(chunk)
            digest.update(chunk)
    tmp.replace(dest)
    return {"url": url, "path": str(dest.relative_to(REPO)), "bytes": dest.stat().st_size,
            "sha256": digest.hexdigest(), "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=sorted(SOURCES), help="subset of sources")
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = ap.parse_args(argv)
    manifest_path = RAW / "MANIFEST.json"
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    failed = []
    for name in args.only or SOURCES:
        for url, dest in SOURCES[name]:
            if dest.exists() and not args.force:
                print(f"[skip] {dest.relative_to(REPO)} exists")
                continue
            attempts = [(url, dest)] + [fb for fb in FALLBACKS.get(name, []) if fb[1] == dest]
            for u, d in attempts:
                try:
                    print(f"[get ] {u}")
                    manifest[str(d.relative_to(REPO))] = download(u, d)
                    print(f"       -> {d.relative_to(REPO)} ({d.stat().st_size / 1e6:.1f} MB)")
                    break
                except Exception as exc:  # noqa: BLE001 - report and try the next mirror
                    print(f"       failed: {exc}")
            else:
                failed.append((name, url, dest))
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if failed:
        print("\nSome downloads failed. Save them manually in a browser:")
        for name, url, dest in failed:
            print(f"  {name}: {url}\n     -> {dest}")
        return 1
    print("\nDone. Next: python -m scripts.build_market")
    return 0


if __name__ == "__main__":
    sys.exit(main())
