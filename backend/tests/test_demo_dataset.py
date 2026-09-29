"""Properties of the simulated market that the demo narrative relies on."""

from collections import Counter

from app.db import fetch_all, get_artifact, session
from app.demo.market import gstin

from .conftest import TENDER


def test_gstin_check_digit():
    # Published example GSTIN with a valid check character.
    assert gstin("27", "AAPFU0939F") == "27AAPFU0939F1ZV"


def test_market_shape(analyzed):
    with session() as conn:
        bids = fetch_all(conn, "SELECT tender_id, vendor_id, outcome FROM bids WHERE tender_id != ?", (TENDER,))
        vendors = fetch_all(conn, "SELECT vendor_id, meta FROM vendors")
    per_tender = Counter(b["tender_id"] for b in bids)
    assert len(per_tender) == 480
    assert 3.0 <= sum(per_tender.values()) / len(per_tender) <= 5.0
    assert sum(1 for b in bids if b["outcome"] == "WON") == 480
    assert len(vendors) == 260 and all(v["meta"].get("constitution") for v in vendors)


def test_decoys_and_planted_actors(analyzed):
    with session() as conn:
        truth = get_artifact(conn, TENDER, "demo_ground_truth")
        rows = fetch_all(conn, "SELECT b.tender_id, b.vendor_id, t.bid_deadline FROM bids b "
                               "JOIN tenders t ON t.tender_id = b.tender_id WHERE b.tender_id != ?", (TENDER,))
    by_tender: dict[str, set] = {}
    for r in rows:
        by_tender.setdefault(r["tender_id"], set()).add(r["vendor_id"])
    # Group companies never bid against each other.
    assert not any({"V015", "V016"} <= v for v in by_tender.values())
    # The debarred firm stops bidding; its successor only starts afterwards.
    assert all(r["bid_deadline"][:10] < "2024-02-15" for r in rows if r["vendor_id"] == "V025")
    assert all(r["bid_deadline"][:10] > "2024-04-10" for r in rows if r["vendor_id"] == "V026")
    assert {k: len(v) for k, v in truth["planted_tenders"].items()} == {
        "A-B": 9, "PUNE-ROADS": 12, "NAGPUR-LIGHTING": 8, "meeting:V003+V004": 1}
