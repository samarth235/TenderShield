"""Five years of simulated award records for the demonstration market (Demo Mode).

Each historical tender is drawn from a buyer's typical workload - segment, value, bid
window and seasonality (fiscal-year-end rush in February and March, a thin 2021) - and
receives bids from the contractors who could realistically have bid: firms working in that
segment and region, large enough to meet the turnover criterion, incorporated before the
tender and not debarred. Quotes follow segment-level pricing with a per-firm bias; the
lowest technically qualified bid wins. Most bids are filed in the last day before the
deadline.

The planted rings (``scenario.RINGS``) are injected into matching tenders: every member
bids, the winner rotates, the cover bids sit a little above it and are filed minutes apart.
Award records carry the bidder name as typed by the buyer's clerk (legal-form variations,
"M/s." prefixes, capitalisation, abbreviations, typos) and a GSTIN only about half the time,
often the firm's registration for the tender's state rather than its home state.
"""

from __future__ import annotations

import random
import re
from datetime import date, datetime, timedelta, timezone

from .market import BUYERS, DEPARTMENTS, REGIONS, SEGMENTS, UNREGISTERED_BIDDERS, gstin
from .scenario import EXCLUSIVE_PAIRS, MEETINGS, RINGS

IST = timezone(timedelta(hours=5, minutes=30))
N_HISTORICAL_TENDERS = 480
HISTORY_START, HISTORY_END = date(2021, 1, 11), date(2026, 1, 23)
TURNOVER_CRITERION = 0.2  # average annual turnover must be at least 20% of the estimate
CROWD_SIZE = 20
MONTH_WEIGHT = {1: 1.1, 2: 1.35, 3: 1.6, 4: 0.6, 5: 0.7, 6: 0.55, 7: 0.6, 8: 0.8, 9: 0.9, 10: 1.0, 11: 1.1, 12: 1.2}
YEAR_WEIGHT = {2021: 0.65, 2022: 0.95, 2023: 1.05, 2024: 1.1, 2025: 1.2, 2026: 1.2}
REGION_STATE_CODE = {"GUJARAT": "24", "CHENNAI": "33", "HYDERABAD": "36", "BENGALURU": "29"}


# --- Record-keeping noise -------------------------------------------------------------

def _typo(name: str) -> str:
    """Swap two adjacent letters in the longest word - a data-entry error."""
    words = name.split()
    i = max(range(len(words)), key=lambda k: len(words[k]))
    w = words[i]
    if len(w) > 6:
        words[i] = w[:3] + w[4] + w[3] + w[5:]
    return " ".join(words)


NAME_TRANSFORMS = [
    lambda s: s.upper(),
    lambda s: ("M/S " + s.upper()) if s.isupper() else "M/s. " + s,
    lambda s: s.replace("Pvt. Ltd.", "Private Limited"),
    lambda s: s.replace("Private Limited", "Pvt Ltd"),
    lambda s: s.replace("Pvt Ltd", "Pvt. Ltd."),
    lambda s: s.replace("Constructions", "Construction"),
    lambda s: s.replace("Engineering", "Engg."),
    lambda s: s.replace("Infrastructure", "Infra"),
    lambda s: s.replace("Limited", "Ltd."),
    lambda s: s.replace("Shree ", "Shri "),
    lambda s: s.replace(".", ""),
    lambda s: s.replace(" & ", " and "),
    lambda s: re.sub(r"\s+(Pvt\.? Ltd\.?|Private Limited|Limited|Ltd\.?|LLP)$", "", s),
    _typo,
]


def name_variant(name: str, rng: random.Random) -> str:
    """Re-spell a company name the way different record systems do."""
    out = name
    for fn in rng.sample(NAME_TRANSFORMS, rng.choices([0, 1, 2], weights=[0.4, 0.4, 0.2])[0]):
        out = fn(out)
    return out


def recorded_gstin(vendor: dict, region: str, rng: random.Random) -> str | None:
    if rng.random() >= 0.5 or vendor["profile"]["constitution"] == "Proprietorship" and rng.random() < 0.5:
        return None
    state = REGION_STATE_CODE.get(region, "27")
    if state == vendor["state_code"]:
        return gstin(vendor["state_code"], vendor["pan"])
    return gstin(state, vendor["pan"], "1")  # state-specific registration


# --- Tender calendar ------------------------------------------------------------------

def _dates(rng: random.Random, n: int) -> list[date]:
    span = (HISTORY_END - HISTORY_START).days
    out: list[date] = []
    while len(out) < n:
        d = HISTORY_START + timedelta(days=rng.randrange(span))
        if d.weekday() >= 5:
            continue
        if rng.random() < MONTH_WEIGHT[d.month] * YEAR_WEIGHT[d.year] / 1.95:
            out.append(d)
    return sorted(out)


def _title(rng: random.Random, segment: str, region: str, year: int) -> str:
    city, localities = rng.choice(REGIONS[region]["cities"])
    loc, loc2 = rng.sample([name for name, _ in localities], 2) if len(localities) > 1 else (localities[0][0],) * 2
    return rng.choice(SEGMENTS[segment]["titles"]).format(
        n=rng.choice([4, 6, 8, 12, 16, 24, 32]), loc=loc, loc2=loc2, city=city, ph=rng.choice(["I", "II", "III"]),
        w=rng.randint(1, 30), d=rng.choice([300, 450, 600, 750, 900]), yr=year)


def build_calendar(rng: random.Random) -> list[dict]:
    tenders = []
    seq: dict[tuple[str, int], int] = {}
    for deadline_day in _dates(rng, N_HISTORICAL_TENDERS):
        region = rng.choices(list(REGIONS), weights=[r["tender_share"] for r in REGIONS.values()])[0]
        code, buyer, _, mix, value_mult = rng.choices(BUYERS[region], weights=[b[2] for b in BUYERS[region]])[0]
        mix = mix or {k: s["share"] for k, s in SEGMENTS.items()}
        segment = rng.choices(list(mix), weights=list(mix.values()))[0]
        spec = SEGMENTS[segment]
        low, high = spec["range"]
        estimate = round(min(high, max(low, rng.lognormvariate(0, spec["sigma"]) * spec["median_cr"] * value_mult)), 2)
        dept, dept_code = DEPARTMENTS[segment]
        key = (code, deadline_day.year)
        seq[key] = seq.get(key, rng.randint(20, 80)) + rng.randint(1, 9)
        deadline = datetime(deadline_day.year, deadline_day.month, deadline_day.day, 15, 0, tzinfo=IST)
        tenders.append({
            "tender_id": f"{code}-{deadline_day.year}-{dept_code}-{seq[key]:04d}",
            "title": _title(rng, segment, region, deadline_day.year),
            "department": f"{buyer} - {dept}",
            "estimated_value_cr": estimate,
            "published_on": (deadline_day - timedelta(days=rng.choice([21, 21, 28, 30, 35]))).isoformat(),
            "bid_deadline": deadline.isoformat(),
            "status": "AWARDED",
            "meta": {"buyer": buyer, "buyer_code": code, "region": region, "segment": segment,
                     "segment_label": spec["label"], "procurement": "Open tender (two-envelope, e-procurement)"},
        })
    return tenders


# --- Participation --------------------------------------------------------------------

def _active(vendor: dict, day: date) -> bool:
    profile = vendor["profile"]
    if date.fromisoformat(vendor["incorporated"]) > day - timedelta(days=365):
        return False  # firms need a year of accounts before they qualify
    until = profile.get("active_until")
    return not (until and day >= date.fromisoformat(until))


def eligible(vendor: dict, tender: dict) -> bool:
    profile, meta = vendor["profile"], tender["meta"]
    value = tender["estimated_value_cr"]
    if meta["segment"] not in profile["segments"] or value < profile.get("min_value_cr", 0):
        return False
    if profile["turnover_cr"] < TURNOVER_CRITERION * value:
        return False
    out = profile.get("outstation")
    in_market = meta["region"] in profile["regions"] or (out and meta["region"] in out["regions"]
                                                        and value >= out["min_value_cr"])
    return bool(in_market) and _active(vendor, datetime.fromisoformat(tender["bid_deadline"]).date())


def _participants(rng: random.Random, vendors: list[dict], tender: dict, excluded: dict[str, set[str]]) -> list[str]:
    pool = [v for v in vendors if eligible(v, tender)]
    rng.shuffle(pool)
    crowding = min(1.0, CROWD_SIZE / max(len(pool), 1))  # in crowded markets each firm bids more selectively
    chosen: list[str] = []
    for v in pool:
        p = v["profile"]["propensity"] * crowding
        if tender["meta"]["region"] not in v["profile"]["regions"]:
            p *= 0.6  # outstation work is bid selectively
        if rng.random() < p and not (excluded.get(v["vendor_id"], set()) & set(chosen)):
            chosen.append(v["vendor_id"])
    if not chosen:
        # No local taker: firms from other markets pick the tender up (re-tendered in practice).
        pool = pool or [v for v in vendors if tender["meta"]["segment"] in v["profile"]["segments"]
                        and v["profile"]["turnover_cr"] >= TURNOVER_CRITERION * tender["estimated_value_cr"]
                        and _active(v, datetime.fromisoformat(tender["bid_deadline"]).date())
                        and not v["profile"].get("min_value_cr") and v["profile"]["propensity"] > 0.1]
        chosen = [v["vendor_id"] for v in pool[:rng.randint(1, 2)]]
    return chosen


def _submission_offset_h(rng: random.Random) -> float:
    """Hours before the deadline: most bids arrive on the last day."""
    r = rng.random()
    if r < 0.55:
        return max(0.08, rng.expovariate(1 / 5.0))
    if r < 0.9:
        return rng.uniform(24, 96)
    return rng.uniform(96, 240)


def _quote(rng: random.Random, vendor: dict | None, tender: dict) -> float:
    spec = SEGMENTS[tender["meta"]["segment"]]
    bias = vendor["profile"]["price_bias"] if vendor else 0.03
    ratio = 1 + spec["discount"] + bias + rng.gauss(0, spec["spread"])
    return round(tender["estimated_value_cr"] * min(1.25, max(0.72, ratio)), 2)


def _retag(rng: random.Random, tender: dict, segment: str, value: tuple[float, float]) -> None:
    """Turn a calendar tender into one of the segment and size a planted pattern needs."""
    meta = tender["meta"]
    year = datetime.fromisoformat(tender["bid_deadline"]).year
    if meta["segment"] != segment:
        dept, dept_code = DEPARTMENTS[segment]
        code, number = meta["buyer_code"], tender["tender_id"].rsplit("-", 1)[1]
        tender["tender_id"] = f"{code}-{year}-{dept_code}-{number}"
        tender["department"] = f"{meta['buyer']} - {dept}"
        tender["title"] = _title(rng, segment, meta["region"], year)
        meta.update(segment=segment, segment_label=SEGMENTS[segment]["label"])
    if not value[0] <= tender["estimated_value_cr"] <= value[1]:
        tender["estimated_value_cr"] = round(rng.uniform(*value), 2)


def _pick_slots(rng: random.Random, tenders: list[dict], used: set[str], region: str, segment: str, count: int,
                value: tuple[float, float], period: tuple[str, str]) -> list[dict]:
    start, end = (date.fromisoformat(p) for p in period)
    candidates = [t for t in tenders if t["tender_id"] not in used and t["meta"]["region"] == region
                  and start <= datetime.fromisoformat(t["bid_deadline"]).date() <= end]
    if len(candidates) < count:
        raise RuntimeError(f"Only {len(candidates)} {region} tenders available for a planted pattern")
    # Spread the planted tenders across the period, preferring ones that already fit.
    step = len(candidates) / count
    picks = []
    for i in range(count):
        window = candidates[int(step * i):max(int(step * (i + 1)), int(step * i) + 1)]
        fitting = [t for t in window if t["meta"]["segment"] == segment
                   and value[0] <= t["estimated_value_cr"] <= value[1]]
        pick = rng.choice(fitting or window)
        _retag(rng, pick, segment, value)
        picks.append(pick)
    used.update(t["tender_id"] for t in picks)
    return picks


def build_history(rng: random.Random, vendors: list[dict]) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
    """Return (tenders, bids, planted). Bids carry the raw bidder name and a ground-truth vendor id;
    ``planted`` maps each ring / forced meeting to the tenders it was injected into."""
    by_id = {v["vendor_id"]: v for v in vendors}
    excluded: dict[str, set[str]] = {}
    for a, b in EXCLUSIVE_PAIRS:
        excluded.setdefault(a, set()).add(b)
        excluded.setdefault(b, set()).add(a)
    ring_members = {vid for ring in RINGS for vid in ring["members"] + ring["covers"]}

    tenders = build_calendar(rng)
    used: set[str] = set()
    planted: dict[str, dict] = {}
    for ring in RINGS:
        slots = _pick_slots(rng, tenders, used, ring["region"], ring["segment"], ring["tenders"],
                            ring["value_cr"], ring["period"])
        outsider = set(rng.sample(range(len(slots)), ring["outsider_wins"]))
        covers = set(rng.sample(range(len(slots)), ring["cover_joins"]))
        for i, t in enumerate(slots):
            planted[t["tender_id"]] = {"ring": ring, "turn": i, "outsider_wins": i in outsider,
                                       "with_covers": i in covers}
    for meeting in MEETINGS:
        for t in _pick_slots(rng, tenders, used, meeting["region"], meeting["segment"], meeting["count"],
                             meeting["value_cr"], meeting["period"]):
            planted[t["tender_id"]] = {"meeting": meeting}

    bids: list[dict] = []
    for tender in tenders:
        plan = planted.get(tender["tender_id"], {})
        deadline = datetime.fromisoformat(tender["bid_deadline"])
        amounts: dict[str, float] = {}
        times: dict[str, datetime] = {}
        disqualified: set[str] = set()
        estimate = tender["estimated_value_cr"]

        if "ring" in plan:
            ring = plan["ring"]
            members = ring["members"]
            winner = members[plan["turn"] % len(members)]
            others = [m for m in members if m != winner]
            genuine = [v for v in _participants(rng, vendors, tender, excluded)
                       if v not in ring_members][:rng.randint(1, 3)]
            if plan["outsider_wins"] and not genuine:
                genuine = [next(v["vendor_id"] for v in vendors
                                if eligible(v, tender) and v["vendor_id"] not in ring_members)]
            base = estimate * (1 + SEGMENTS[tender["meta"]["segment"]]["discount"] + rng.uniform(-0.035, -0.01))
            amounts[winner] = round(base, 2)
            first = deadline - timedelta(hours=rng.uniform(1.5, 20))
            times[winner] = first
            for k, vid in enumerate(others, start=1):
                amounts[vid] = round(amounts[winner] * (1 + rng.uniform(*ring["cover_gap"]) * k), 2)
                times[vid] = first + timedelta(minutes=rng.uniform(*ring["filing_gap_min"]) * k)
            if plan["with_covers"]:
                for vid in ring["covers"]:
                    amounts[vid] = round(amounts[winner] * rng.uniform(1.05, 1.09), 2)
                    times[vid] = first + timedelta(minutes=rng.uniform(15, 40))
                    if not eligible(by_id[vid], tender):
                        disqualified.add(vid)  # a cover bid that never met the qualification criteria
            top_cover = max(amounts.values())
            for vid in genuine:
                if plan["outsider_wins"] and vid == genuine[0]:
                    amounts[vid] = round(amounts[winner] * rng.uniform(0.95, 0.985), 2)
                else:
                    amounts[vid] = round(top_cover * rng.uniform(1.01, 1.08), 2)
        else:
            chosen = list(plan["meeting"]["vendors"]) if "meeting" in plan else []
            chosen += [v for v in _participants(rng, vendors, tender, excluded) if v not in chosen
                       and not (excluded.get(v, set()) & set(chosen))]
            for vid in chosen:
                amounts[vid] = _quote(rng, by_id[vid], tender)
                if len(chosen) > 1 and rng.random() < 0.06:
                    disqualified.add(vid)  # rejected at technical evaluation
        for vid in amounts:
            times.setdefault(vid, deadline - timedelta(hours=_submission_offset_h(rng)))
        if len(disqualified) == len(amounts):
            disqualified.clear()

        entries = [(vid, amounts[vid], times[vid]) for vid in amounts]
        if "ring" not in plan and rng.random() < 0.05:  # a firm missing from the vendor registry
            entries.append((None, _quote(rng, None, tender), deadline - timedelta(hours=_submission_offset_h(rng))))
        entries.sort(key=lambda e: e[1])
        rank = 0
        for vid, amount, submitted in entries:
            if vid in disqualified:
                outcome, position = "DISQUALIFIED", None
            else:
                rank += 1
                outcome, position = ("WON" if rank == 1 else "RUNNER_UP" if rank == 2 else "LOST"), rank
            if vid is None:
                raw_name, bid_gstin = rng.choice(UNREGISTERED_BIDDERS), None
            else:
                raw_name = name_variant(by_id[vid]["name"], rng)
                bid_gstin = recorded_gstin(by_id[vid], tender["meta"]["region"], rng)
            bids.append({
                "tender_id": tender["tender_id"], "truth_vendor_id": vid, "bidder_name": raw_name,
                "bidder_gstin": bid_gstin, "amount_cr": amount, "submitted_at": submitted.isoformat(timespec="seconds"),
                "outcome": outcome, "rank": position,
            })
        tender["meta"]["bidders"] = len(entries)
    rings = {}
    for tid, plan in planted.items():
        key = plan["ring"]["key"] if "ring" in plan else "meeting:" + "+".join(plan["meeting"]["vendors"])
        rings.setdefault(key, []).append(tid)
    return tenders, bids, rings
