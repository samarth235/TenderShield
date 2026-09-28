"""Deterministic synthetic dataset for the demonstration tender (Demo Mode).

Produces 50 registered vendors, 120 historical tenders with award records, the current
tender TN-2026-014 with six bidders, and the full PDF document package.
"""

from __future__ import annotations

import random
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..config import get_settings
from ..db import dumps, put_artifact, reset_db, session
from ..ingestion.pdf_text import register_document
from . import documents as docs
from .scenario import (
    BIDDER_FACTS,
    BIDDERS,
    COLLUSIVE_COBIDS,
    COLLUSIVE_PAIR,
    CURRENT_BIDS,
    DEMO_TENDER,
    DEMO_TENDER_ID,
    WEAK_COBIDS,
    WEAK_PAIR,
)

IST = timezone(timedelta(hours=5, minutes=30))
N_BACKGROUND_VENDORS = 44
N_HISTORICAL_TENDERS = 120

_PREFIXES = [
    "Shree", "Sai", "Metro", "Urban", "Prime", "Galaxy", "Omkar", "Trident", "Sahyadri", "Konkan", "Vertex",
    "Pioneer", "Unity", "Zenith", "Nova", "Orbit", "Crest", "Horizon", "Summit", "Royal", "Pinnacle", "Supreme",
]
_CORES = [
    "Infra Projects", "Engineering", "Constructions", "Buildtech", "Infrastructure", "Civil Works",
    "Technologies", "Systems", "Developers",
]
_LEGAL = ["Pvt. Ltd.", "Private Limited", "LLP", "Ltd.", "Pvt Ltd"]
_FIRST = [
    "Amit", "Priya", "Sanjay", "Kavita", "Rahul", "Deepa", "Manoj", "Sunita", "Karan", "Pooja", "Nitin",
    "Lakshmi", "Harish", "Rekha", "Gaurav", "Swati", "Imran", "Divya", "Prakash", "Asha",
]
_LAST = [
    "Mehta", "Gupta", "Patel", "Reddy", "Singh", "Chopra", "Banerjee", "Pillai", "Verma", "Jain", "Kapoor",
    "Naidu", "Ghosh", "Saxena", "Shetty", "Malhotra", "Pandey", "Chauhan", "Rao", "Das",
]
_CITIES = [
    ("Pune", "Maharashtra", "4110"), ("Nagpur", "Maharashtra", "4400"), ("Thane", "Maharashtra", "4006"),
    ("Ahmedabad", "Gujarat", "3800"), ("Surat", "Gujarat", "3950"), ("Indore", "Madhya Pradesh", "4520"),
    ("Jaipur", "Rajasthan", "3020"), ("Lucknow", "Uttar Pradesh", "2260"), ("Kochi", "Kerala", "6820"),
    ("Bhubaneswar", "Odisha", "7510"), ("Nashik", "Maharashtra", "4220"), ("Vadodara", "Gujarat", "3900"),
]
_STATE_CODES = {"Maharashtra": "27", "Gujarat": "24", "Madhya Pradesh": "23", "Rajasthan": "08",
                "Uttar Pradesh": "09", "Kerala": "32", "Odisha": "21"}
_STREETS = ["MG Road", "Station Road", "Ring Road", "Industrial Estate", "Link Road"]
_WORKS = [
    "Road resurfacing", "Signal upgrade", "Storm-water drain", "Street lighting", "Flyover repair",
    "CCTV surveillance", "Footpath and junction improvement",
]
# Bidders that appear in award records but are not in the vendor registry.
_UNREGISTERED = ["Metro Traffic Solutions", "Sigma Signal Systems & Co.", "K. R. Enterprises"]


def _pan(rng: random.Random, entity_letter: str) -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return (
        "AA" + rng.choice(letters) + "C" + entity_letter + f"{rng.randint(1000, 9999)}" + rng.choice(letters)
    )


def build_vendor_pool(rng: random.Random) -> list[dict]:
    vendors = [dict(v, source="registry") for v in BIDDERS]
    used_names = {v["name"] for v in vendors}
    used_dins = {d["din"] for v in vendors for d in v["directors"]}
    idx = 7
    while len(vendors) < len(BIDDERS) + N_BACKGROUND_VENDORS:
        core = f"{rng.choice(_PREFIXES)} {rng.choice(_CORES)}"
        if core in used_names:
            continue
        used_names.add(core)
        name = f"{core} {rng.choice(_LEGAL)}"
        city, state, pin_prefix = rng.choice(_CITIES)
        directors = []
        for _ in range(2):
            din = f"0{rng.randint(6000000, 9999999)}"
            while din in used_dins:
                din = f"0{rng.randint(6000000, 9999999)}"
            used_dins.add(din)
            directors.append({"name": f"{rng.choice(_FIRST)} {rng.choice(_LAST)}", "din": din})
        slug = name.split()[0].lower()
        vendors.append(
            {
                "vendor_id": f"V{idx:03d}",
                "alias": None,
                "name": name,
                "pan": _pan(rng, name.split()[0][0].upper()),
                "state_code": _STATE_CODES[state],
                "registered_address": f"{rng.randint(1, 250)}, {rng.choice(_STREETS)}, {city}, {state} "
                f"{pin_prefix}{rng.randint(10, 99)}",
                "phone": f"+91 {rng.randint(20, 99)} {rng.randint(2000, 9999)} {rng.randint(1000, 9999)}",
                "email": f"tenders@{slug}{idx}.in",
                "incorporated": date(rng.randint(1998, 2020), rng.randint(1, 12), rng.randint(1, 28)).isoformat(),
                "msme": rng.random() < 0.25,
                "directors": directors,
                "source": "registry",
            }
        )
        idx += 1
    return vendors


def _typo(name: str) -> str:
    """Swap two adjacent letters in the longest word - a data-entry error."""
    words = name.split()
    i = max(range(len(words)), key=lambda k: len(words[k]))
    w = words[i]
    if len(w) > 6:
        words[i] = w[:3] + w[4] + w[3] + w[5:]
    return " ".join(words)


def name_variant(name: str, rng: random.Random) -> str:
    """Re-spell a company name the way different record systems do."""
    transforms = [
        lambda s: s.upper(),
        lambda s: s.replace("Pvt. Ltd.", "Private Limited"),
        lambda s: s.replace("Private Limited", "Pvt Ltd"),
        lambda s: s.replace("Pvt Ltd", "Pvt. Ltd."),
        lambda s: s.replace("Constructions", "Construction"),
        lambda s: s.replace("Limited", "Ltd."),
        lambda s: s.replace(".", ""),
        lambda s: s.replace(" & ", " and "),
        lambda s: re.sub(r"\s+(Pvt\.? Ltd\.?|Private Limited|Limited|Ltd\.?|LLP)$", "", s),
        _typo,
    ]
    out = name
    for fn in rng.sample(transforms, rng.randint(0, 2)):
        out = fn(out)
    return out


def _gstin(vendor: dict) -> str:
    return f"{vendor['state_code']}{vendor['pan']}1Z5"


def build_history(rng: random.Random, vendors: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (tenders, bids). Bids carry the raw bidder name and a ground-truth vendor id."""
    by_id = {v["vendor_id"]: v for v in vendors}
    ids = [v["vendor_id"] for v in vendors]
    weights = [1.0 for _ in ids]
    exclusive = [set(COLLUSIVE_PAIR), set(WEAK_PAIR)]

    collusive_slots = [11, 34, 58, 83, 107][:COLLUSIVE_COBIDS]
    weak_slots = [70][:WEAK_COBIDS]
    start = date(2021, 1, 15)
    span_days = (date(2026, 1, 20) - start).days

    tenders, bids = [], []
    rotation = 0
    for i in range(N_HISTORICAL_TENDERS):
        opened = start + timedelta(days=int(span_days * i / (N_HISTORICAL_TENDERS - 1)))
        tender_id = f"TN-{opened.year}-H{i + 1:03d}"
        estimate = round(rng.uniform(5, 80), 2)
        deadline = datetime(opened.year, opened.month, opened.day, 15, 0, tzinfo=IST)
        tenders.append(
            {
                "tender_id": tender_id,
                "title": f"{rng.choice(_WORKS)} works, package {i + 1}",
                "department": rng.choice(["Transport Engineering", "Public Works", "Smart City SPV", "Electrical"]),
                "estimated_value_cr": estimate,
                "published_on": (opened - timedelta(days=30)).isoformat(),
                "bid_deadline": deadline.isoformat(),
                "status": "AWARDED",
            }
        )

        planted_pair = COLLUSIVE_PAIR if i in collusive_slots else WEAK_PAIR if i in weak_slots else None
        chosen: list[str] = list(planted_pair) if planted_pair else []
        target = rng.randint(3, 7) if not planted_pair else len(chosen) + rng.randint(2, 3)
        while len(chosen) < target:
            vid = rng.choices(ids, weights=weights)[0]
            if vid in chosen:
                continue
            if any(vid in pair and (pair - {vid}) & set(chosen) for pair in exclusive):
                continue
            chosen.append(vid)

        amounts: dict[str, float] = {}
        times: dict[str, datetime] = {}
        if planted_pair == COLLUSIVE_PAIR:
            winner, cover = (COLLUSIVE_PAIR if rotation % 2 == 0 else COLLUSIVE_PAIR[::-1])
            rotation += 1
            amounts[winner] = estimate * rng.uniform(0.92, 0.95)
            amounts[cover] = amounts[winner] * rng.uniform(1.015, 1.03)
            first = deadline - timedelta(hours=rng.uniform(4, 30))
            times[winner] = first
            times[cover] = first + timedelta(minutes=rng.uniform(3, 12))
            for vid in chosen[2:]:
                amounts[vid] = estimate * rng.uniform(1.0, 1.12)
        elif planted_pair == WEAK_PAIR:
            amounts[WEAK_PAIR[0]] = estimate * 1.05
            amounts[WEAK_PAIR[1]] = estimate * 1.09
            for vid in chosen[2:]:
                amounts[vid] = estimate * rng.uniform(0.9, 1.02)
        else:
            for vid in chosen:
                amounts[vid] = estimate * rng.uniform(0.9, 1.15)
        for vid in chosen:
            times.setdefault(vid, deadline - timedelta(hours=rng.uniform(1, 72)))

        entries = [(vid, round(amounts[vid], 2), times[vid]) for vid in chosen]
        if rng.random() < 0.08:  # an unregistered bidder shows up in the award record
            entries.append((None, round(estimate * rng.uniform(1.05, 1.2), 2), deadline - timedelta(hours=rng.uniform(1, 48))))
        entries.sort(key=lambda e: e[1])
        for rank, (vid, amount, submitted) in enumerate(entries, start=1):
            if vid is None:
                raw_name, gstin = rng.choice(_UNREGISTERED), None
            else:
                raw_name = name_variant(by_id[vid]["name"], rng)
                gstin = _gstin(by_id[vid]) if rng.random() < 0.5 else None
            bids.append(
                {
                    "tender_id": tender_id,
                    "truth_vendor_id": vid,
                    "bidder_name": raw_name,
                    "bidder_gstin": gstin,
                    "amount_cr": amount,
                    "submitted_at": submitted.isoformat(timespec="seconds"),
                    "outcome": "WON" if rank == 1 else "RUNNER_UP" if rank == 2 else "LOST",
                    "rank": rank,
                }
            )
    return tenders, bids


def load_demo() -> dict:
    """Reset the database and load the complete demonstration dataset."""
    settings = get_settings()
    rng = random.Random(settings.random_seed)
    reset_db()
    tender_dir = settings.documents_dir / DEMO_TENDER_ID
    if tender_dir.exists():
        shutil.rmtree(tender_dir)
    tender_dir.mkdir(parents=True)

    vendors = build_vendor_pool(rng)
    history, hist_bids = build_history(rng, vendors)
    by_id = {v["vendor_id"]: v for v in vendors}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with session() as conn:
        for v in vendors:
            conn.execute(
                "INSERT INTO vendors (vendor_id, alias, name, gstin, pan, registered_address, phone, email,"
                " incorporated, msme, directors, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    v["vendor_id"], v["alias"], v["name"], _gstin(v), v["pan"], v["registered_address"], v["phone"],
                    v["email"], v["incorporated"], int(v["msme"]), dumps(v["directors"]),
                    dumps({"source": v["source"], "directors_available": bool(v["directors"])}),
                ),
            )
        for t in history:
            conn.execute(
                "INSERT INTO tenders (tender_id, title, department, estimated_value_cr, published_on, bid_deadline,"
                " status, is_current, source, meta) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'history', '{}')",
                (t["tender_id"], t["title"], t["department"], t["estimated_value_cr"], t["published_on"],
                 t["bid_deadline"], t["status"]),
            )
        t = DEMO_TENDER
        conn.execute(
            "INSERT INTO tenders (tender_id, title, department, estimated_value_cr, published_on, bid_deadline,"
            " status, is_current, source, meta) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'demo', ?)",
            (t["tender_id"], t["title"], t["department"], t["estimated_value_cr"], t["published_on"],
             t["bid_deadline"], t["status"], dumps({"demo": True})),
        )
        truth: dict[str, str | None] = {}
        for b in hist_bids:
            cur = conn.execute(
                "INSERT INTO bids (tender_id, vendor_id, bidder_name, bidder_gstin, amount_cr, submitted_at, outcome, rank)"
                " VALUES (?, NULL, ?, ?, ?, ?, ?, ?)",
                (b["tender_id"], b["bidder_name"], b["bidder_gstin"], b["amount_cr"], b["submitted_at"], b["outcome"], b["rank"]),
            )
            truth[str(cur.lastrowid)] = b["truth_vendor_id"]
        for vid, (amount, submitted) in CURRENT_BIDS.items():
            conn.execute(
                "INSERT INTO bids (tender_id, vendor_id, bidder_name, bidder_gstin, amount_cr, submitted_at, outcome, rank)"
                " VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL)",
                (DEMO_TENDER_ID, vid, by_id[vid]["name"], _gstin(by_id[vid]), amount, submitted),
            )
        put_artifact(conn, DEMO_TENDER_ID, "demo_ground_truth", {"bid_vendor": truth}, now)

        registered = render_documents(conn, tender_dir, settings.random_seed)

    return {
        "tender_id": DEMO_TENDER_ID,
        "title": DEMO_TENDER["title"],
        "bidders": len(BIDDERS),
        "tender_documents": len(registered),
        "historical_tenders": len(history),
        "registered_vendors": len(vendors),
        "historical_bid_records": len(hist_bids),
        "documents": registered,
    }


def render_documents(conn, tender_dir: Path, seed: int, overrides: dict | None = None) -> list[dict]:
    """Render and register every PDF of the demo tender package.

    ``overrides`` maps vendor_id -> {fact: value} and is used by the tamper demo.
    """
    overrides = overrides or {}
    registered = []
    path = tender_dir / f"Tender_{DEMO_TENDER_ID}.pdf"
    docs.write_pdf(path, f"Tender Document {DEMO_TENDER_ID}", docs.tender_pages())
    registered.append(register_document(conn, document_id="DOC-TENDER", tender_id=DEMO_TENDER_ID,
                                        vendor_id=None, kind="tender", path=path))

    sections = docs.technical_sections(BIDDERS, seed)
    log_rows = []
    for vendor in BIDDERS:
        vid = vendor["vendor_id"]
        facts = {**BIDDER_FACTS[vid], **overrides.get(vid, {})}
        letter = vendor["alias"].split()[-1]
        tech = tender_dir / f"TechnicalBid_{letter}.pdf"
        docs.write_pdf(tech, f"Technical Proposal - {vendor['name']}", docs.technical_pages(vendor, facts, sections[vid], seed))
        registered.append(register_document(conn, document_id=f"DOC-{vid}-TECH", tender_id=DEMO_TENDER_ID,
                                            vendor_id=vid, kind="technical_bid", path=tech))
        comp = tender_dir / f"ComplianceDocs_{letter}.pdf"
        docs.write_pdf(comp, f"Compliance Documents - {vendor['name']}", docs.compliance_pages(vendor, facts))
        registered.append(register_document(conn, document_id=f"DOC-{vid}-COMP", tender_id=DEMO_TENDER_ID,
                                            vendor_id=vid, kind="compliance", path=comp))
        amount, submitted = CURRENT_BIDS[vid]
        log_rows.append((vid, vendor["name"], submitted, amount))

    log = tender_dir / f"BidSubmissionLog_{DEMO_TENDER_ID}.pdf"
    docs.write_pdf(log, f"Bid Submission Log {DEMO_TENDER_ID}", docs.submission_log_pages(log_rows))
    registered.append(register_document(conn, document_id="DOC-SUBMISSION-LOG", tender_id=DEMO_TENDER_ID,
                                        vendor_id=None, kind="submission_log", path=log))
    return registered
