"""Entity Resolution (Stage 5).

Links differently formatted records to the same real-world entity while keeping the
original values as evidence:
  * bidder names in historical award records  -> registered vendors
  * director records across vendors            -> person entities (DIN first, then name)
  * registered addresses                       -> premises entities
  * phone numbers / e-mail domains             -> contact entities
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from rapidfuzz import fuzz

from ..db import fetch_all, put_artifact

NAME_MATCH_THRESHOLD = 92.0
ADDRESS_MATCH_THRESHOLD = 85.0

ABBREVIATIONS = {
    "pvt": "private", "ltd": "limited", "co": "company", "corp": "corporation", "engg": "engineering",
    "intl": "international", "&": "and", "sec": "sector", "no": "", "rd": "road", "st": "street",
    "infra": "infrastructure", "shri": "shree", "sri": "shree", "bros": "brothers", "off": "office",
}
LEGAL_SUFFIXES = {"private", "limited", "llp", "company", "corporation", "inc"}
GENERIC_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.co.in", "ymail.com", "outlook.com", "hotmail.com",
                         "rediffmail.com"}
HONORIFIC = re.compile(r"^\s*m\s*/\s*s\.?\s+")  # "M/s." prefix used in Indian award records


def normalise_tokens(text: str) -> list[str]:
    text = HONORIFIC.sub("", text.lower()).replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = []
    for token in text.split():
        token = ABBREVIATIONS.get(token, token)
        if not token:
            continue
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]  # constructions -> construction
        tokens.append(token)
    return tokens


def normalise_company(name: str) -> str:
    return " ".join(normalise_tokens(name))


def company_core(name: str) -> str:
    """Normalised name without legal-form words - used for fuzzy comparison."""
    return " ".join(t for t in normalise_tokens(name) if t not in LEGAL_SUFFIXES)


def normalise_address(address: str) -> tuple[str, str | None]:
    pin = re.search(r"\b(\d{6})\b", address)
    tokens = [t for t in normalise_tokens(address) if not re.fullmatch(r"\d{6}", t)]
    return " ".join(tokens), pin.group(1) if pin else None


def premises_numbers(normalised_address: str) -> set[str]:
    """Plot / unit / sector numbers - two addresses on the same street with different numbers are different premises."""
    return set(re.findall(r"\d+", normalised_address))


def normalise_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-10:]


def person_name_compatible(a: str, b: str) -> float:
    """Score two person names allowing initials ('Rajesh K. Sharma' ~ 'Rajesh Kumar Sharma')."""
    ta = normalise_tokens(a)
    tb = normalise_tokens(b)
    if not ta or not tb or ta[0] != tb[0] or ta[-1] != tb[-1]:
        return fuzz.token_sort_ratio(" ".join(ta), " ".join(tb)) * 0.8
    mid_a, mid_b = ta[1:-1], tb[1:-1]
    for x, y in zip(mid_a, mid_b):
        if not (x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))):
            return 60.0
    return 100.0 if mid_a == mid_b else 95.0


def resolve_bidders(conn: sqlite3.Connection, vendors: list[dict]) -> dict:
    """Resolve historical bid records (raw names / GSTINs) to registered vendors; writes bids.vendor_id."""
    by_gstin = {v["gstin"]: v for v in vendors if v.get("gstin")}
    # A GSTIN embeds the holder's PAN (characters 3-12): a firm registered in several states
    # bids with a different GSTIN in each, but the PAN still identifies it.
    by_pan = {v["pan"]: v for v in vendors if v.get("pan")}
    cores = [(v, company_core(v["name"]), normalise_company(v["name"])) for v in vendors]
    bids = fetch_all(conn, "SELECT bid_id, bidder_name, bidder_gstin, vendor_id FROM bids")
    stats = {"records": len(bids), "by_identifier": 0, "exact_normalised": 0, "fuzzy": 0, "unmatched": 0,
             "already_linked": 0}
    variants: dict[str, set[str]] = defaultdict(set)
    unmatched: dict[str, int] = defaultdict(int)
    fuzzy_links: list[dict] = []

    for bid in bids:
        if bid["vendor_id"]:
            stats["already_linked"] += 1
            variants[bid["vendor_id"]].add(bid["bidder_name"])
            continue
        match, method, score = None, None, 0.0
        if bid["bidder_gstin"] and bid["bidder_gstin"] in by_gstin:
            match, method, score = by_gstin[bid["bidder_gstin"]], "identifier", 100.0
        elif bid["bidder_gstin"] and bid["bidder_gstin"][2:12] in by_pan:
            match, method, score = by_pan[bid["bidder_gstin"][2:12]], "identifier", 100.0
        else:
            norm = normalise_company(bid["bidder_name"])
            core = company_core(bid["bidder_name"])
            exact = [v for v, _, vnorm in cores if vnorm == norm]
            if len(exact) == 1:
                match, method, score = exact[0], "exact_normalised", 100.0
            else:
                ranked = sorted(
                    ((fuzz.token_sort_ratio(core, vcore), fuzz.token_sort_ratio(norm, vnorm), v) for v, vcore, vnorm in cores),
                    key=lambda item: (item[0], item[1]),
                    reverse=True,
                )
                best = ranked[0]
                tied = len(ranked) > 1 and ranked[1][:2] == best[:2]
                if best[0] >= NAME_MATCH_THRESHOLD and not tied:
                    match, method, score = best[2], "fuzzy", best[0]
        if match is None:
            stats["unmatched"] += 1
            unmatched[bid["bidder_name"]] += 1
            continue
        stats["by_identifier" if method == "identifier" else method] += 1
        variants[match["vendor_id"]].add(bid["bidder_name"])
        if method == "fuzzy":
            fuzzy_links.append({"bid_id": bid["bid_id"], "raw": bid["bidder_name"], "vendor_id": match["vendor_id"],
                                "score": round(score, 1)})
        conn.execute("UPDATE bids SET vendor_id = ? WHERE bid_id = ?", (match["vendor_id"], bid["bid_id"]))

    return {
        "stats": stats,
        "name_variants": {k: sorted(v) for k, v in variants.items() if len(v) > 1},
        "unmatched_bidders": dict(unmatched),
        "fuzzy_links": fuzzy_links[:50],
    }


def resolve_shared_entities(vendors: list[dict]) -> dict:
    """Cluster directors, addresses and contacts across vendors into shared entities."""
    directors: list[dict] = []  # {entity_id, name, din, records:[{vendor_id, raw_name, din}], method}
    for vendor in vendors:
        for d in vendor.get("directors") or []:
            record = {"vendor_id": vendor["vendor_id"], "raw_name": d["name"], "din": d.get("din")}
            target = None
            for ent in directors:
                if d.get("din") and ent["din"] == d.get("din"):
                    target, method = ent, "identifier (DIN)"
                    break
                if not d.get("din") and person_name_compatible(ent["name"], d["name"]) >= 95:
                    target, method = ent, "name similarity"
                    break
            if target is None:
                directors.append({"entity_id": f"DIR-{len(directors) + 1:03d}", "name": d["name"], "din": d.get("din"),
                                  "records": [record], "match_methods": []})
            else:
                target["records"].append(record)
                target["match_methods"].append({
                    "raw_name": d["name"], "method": method,
                    "name_score": person_name_compatible(target["name"], d["name"]),
                })

    addresses: list[dict] = []
    for vendor in vendors:
        if not vendor.get("registered_address"):
            continue
        norm, pin = normalise_address(vendor["registered_address"])
        record = {"vendor_id": vendor["vendor_id"], "raw": vendor["registered_address"]}
        target = None
        for ent in addresses:
            if pin and ent["pincode"] == pin and premises_numbers(ent["normalised"]) == premises_numbers(norm):
                score = fuzz.token_set_ratio(ent["normalised"], norm)
                if score >= ADDRESS_MATCH_THRESHOLD:
                    target = ent
                    ent["match_scores"].append({"raw": vendor["registered_address"], "score": round(score, 1)})
                    break
        if target is None:
            addresses.append({"entity_id": f"ADDR-{len(addresses) + 1:03d}", "normalised": norm, "pincode": pin,
                              "records": [record], "match_scores": []})
        else:
            target["records"].append(record)

    contacts: dict[str, dict] = {}
    for vendor in vendors:
        keys = []
        if vendor.get("phone"):
            keys.append(("phone", normalise_phone(vendor["phone"])))
        if vendor.get("email") and "@" in vendor["email"]:
            domain = vendor["email"].split("@", 1)[1].lower()
            keys.append(("email_domain", domain) if domain not in GENERIC_EMAIL_DOMAINS else ("email", vendor["email"].lower()))
        for kind, value in keys:
            ent = contacts.setdefault(f"{kind}:{value}", {"kind": kind, "value": value, "records": []})
            ent["records"].append({"vendor_id": vendor["vendor_id"], "raw": vendor["phone"] if kind == "phone" else vendor["email"]})
    contact_list = []
    for i, ent in enumerate(contacts.values(), start=1):
        contact_list.append({"entity_id": f"CONT-{i:03d}", **ent})

    return {"directors": directors, "addresses": addresses, "contacts": contact_list}


def shared_links(entities: dict) -> dict[tuple[str, str], list[dict]]:
    """(vendor_a, vendor_b) -> list of shared-entity links with the raw evidence on each side."""
    links: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for kind, key in (("director", "directors"), ("address", "addresses"), ("contact", "contacts")):
        for ent in entities[key]:
            vendor_ids = sorted({r["vendor_id"] for r in ent["records"]})
            for i, a in enumerate(vendor_ids):
                for b in vendor_ids[i + 1:]:
                    ra = [r for r in ent["records"] if r["vendor_id"] == a]
                    rb = [r for r in ent["records"] if r["vendor_id"] == b]
                    links[(a, b)].append({"type": kind, "entity_id": ent["entity_id"], "records": ra + rb, "entity": {
                        k: v for k, v in ent.items() if k not in ("records",)}})
    return links


def run_entity_resolution(conn: sqlite3.Connection, tender_id: str) -> dict:
    vendors = fetch_all(conn, "SELECT * FROM vendors ORDER BY vendor_id")
    bidder_stats = resolve_bidders(conn, vendors)
    entities = resolve_shared_entities(vendors)
    links = shared_links(entities)
    data_quality = [
        {"vendor_id": v["vendor_id"], "issue": "DIRECTORS_UNAVAILABLE",
         "detail": "Director / ownership information is not available in the vendor registry."}
        for v in vendors if not v.get("directors")
    ]
    result = {
        "tender_id": tender_id,
        "bidder_resolution": bidder_stats,
        "entities": entities,
        "shared_links": [{"vendors": list(k), "links": v} for k, v in sorted(links.items())],
        "data_quality": data_quality,
        "summary": {
            "vendors": len(vendors),
            "director_entities": len(entities["directors"]),
            "shared_directors": sum(len({r["vendor_id"] for r in d["records"]}) > 1 for d in entities["directors"]),
            "address_entities": len(entities["addresses"]),
            "shared_addresses": sum(len({r["vendor_id"] for r in a["records"]}) > 1 for a in entities["addresses"]),
            "contact_entities": len(entities["contacts"]),
            "shared_contacts": sum(len({r["vendor_id"] for r in c["records"]}) > 1 for c in entities["contacts"]),
            "historical_records_resolved": bidder_stats["stats"]["records"] - bidder_stats["stats"]["unmatched"],
            "historical_records_unmatched": bidder_stats["stats"]["unmatched"],
        },
    }
    put_artifact(conn, tender_id, "entities", result, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return result
