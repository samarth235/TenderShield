"""Supplier capability profiles built from real award and bid records.

A profile summarises, per supplier, what the published records show: how many awards in each
capability, their values (₹ crore at reference FX), the time span, and any MSME evidence.

MSME status is never inferred from a name. It is either
  * ``VERIFIED_MICRO|SMALL|MEDIUM`` - imported from Udyam registration evidence, or
  * ``SIZE_PROXY_SMALL`` / ``SIZE_PROXY_LARGE`` - derived from the largest published award, and
    always presented as a proxy that needs Udyam verification, or
  * ``UNKNOWN``.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import statistics
from collections import defaultdict

from ..entities.resolution import company_core

# Largest single award (₹ Cr) at or below which a supplier is shown as a *possible* smaller enterprise.
SME_PROXY_MAX_AWARD_CR = float(os.environ.get("TS_SME_PROXY_MAX_AWARD_CR", "30"))


def rebuild_profiles(conn: sqlite3.Connection) -> dict:
    existing_msme = {r["supplier_key"]: (r["msme_status"], r["msme_evidence"]) for r in conn.execute(
        "SELECT supplier_key, msme_status, msme_evidence FROM market_suppliers WHERE msme_status LIKE 'VERIFIED%'")}
    agg: dict[str, dict] = defaultdict(lambda: {"names": defaultdict(int), "countries": defaultdict(int),
                                                "sources": set(), "values": [], "dates": [],
                                                "caps": defaultdict(int), "cap_values": defaultdict(float),
                                                "n": 0, "bids": 0})
    for r in conn.execute("SELECT supplier_key, supplier_name, supplier_country, source_id, amount_inr_cr, signed_on,"
                          " capability FROM market_awards"):
        a = agg[r["supplier_key"]]
        a["names"][r["supplier_name"]] += 1
        if r["supplier_country"]:
            a["countries"][r["supplier_country"]] += 1
        a["sources"].add(r["source_id"])
        a["n"] += 1
        a["caps"][r["capability"]] += 1
        if r["amount_inr_cr"] is not None:
            a["values"].append(r["amount_inr_cr"])
            a["cap_values"][r["capability"]] = max(a["cap_values"][r["capability"]], r["amount_inr_cr"])
        if r["signed_on"]:
            a["dates"].append(r["signed_on"])
    for r in conn.execute("SELECT supplier_key, MIN(supplier_name) supplier_name, MIN(source_id) source_id, COUNT(*) n FROM market_bids"
                          " GROUP BY supplier_key"):
        a = agg[r["supplier_key"]]
        a["bids"] = r["n"]
        a["sources"].add(r["source_id"])
        if not a["names"]:
            a["names"][r["supplier_name"]] += 1

    conn.execute("DELETE FROM market_suppliers")
    out = []
    for key, a in agg.items():
        name = max(a["names"].items(), key=lambda kv: kv[1])[0]
        country = max(a["countries"].items(), key=lambda kv: kv[1])[0] if a["countries"] else None
        vals = a["values"]
        max_v = max(vals) if vals else None
        if key in existing_msme:
            status, evidence = existing_msme[key]
        elif max_v is None:
            status, evidence = "UNKNOWN", None
        else:
            status = "SIZE_PROXY_SMALL" if max_v <= SME_PROXY_MAX_AWARD_CR else "SIZE_PROXY_LARGE"
            evidence = json.dumps({"basis": "largest published award", "largest_award_inr_cr": round(max_v, 3),
                                   "threshold_inr_cr": SME_PROXY_MAX_AWARD_CR,
                                   "note": "Proxy only - verify Udyam registration before relying on it"})
        ident = {"scheme_id": key.split(":", 1)[1]} if not key.startswith("NAME:") else {}
        if ident:
            ident["scheme"] = key.split(":", 1)[0]
        out.append((key, name, country, json.dumps(sorted(a["sources"])), a["n"],
                    round(sum(vals), 4) if vals else None, round(max_v, 4) if max_v is not None else None,
                    round(statistics.median(vals), 4) if vals else None,
                    min(a["dates"]) if a["dates"] else None, max(a["dates"]) if a["dates"] else None,
                    json.dumps(dict(a["caps"])), json.dumps({k: round(v, 4) for k, v in a["cap_values"].items()}),
                    a["bids"], status, evidence if isinstance(evidence, (str, type(None))) else json.dumps(evidence),
                    json.dumps(ident)))
    conn.executemany("INSERT INTO market_suppliers VALUES (" + ",".join("?" * 16) + ")", out)
    return {"suppliers": len(out)}


def import_udyam_evidence(conn: sqlite3.Connection, csv_text: str) -> dict:
    """Attach Udyam (MSME) evidence that the team has checked on udyamregistration.gov.in.

    Columns: supplier_name (or supplier_key), category (micro|small|medium), udyam_number, verified_on, source_url.
    Matching is by supplier_key, else by normalised company name.
    """
    by_core: dict[str, list[str]] = defaultdict(list)
    for r in conn.execute("SELECT supplier_key, name FROM market_suppliers"):
        by_core[company_core(r["name"])].append(r["supplier_key"])
    matched, unmatched = 0, []
    for row in csv.DictReader(io.StringIO(csv_text)):
        cat = (row.get("category") or "").strip().upper()
        if cat not in ("MICRO", "SMALL", "MEDIUM"):
            unmatched.append({"row": row, "reason": "category must be micro/small/medium"})
            continue
        keys = [row["supplier_key"]] if row.get("supplier_key") else by_core.get(company_core(row.get("supplier_name", "")), [])
        if not keys:
            unmatched.append({"row": row, "reason": "no supplier with this name in the market data"})
            continue
        evidence = json.dumps({"basis": "Udyam registration", "udyam_number": row.get("udyam_number"),
                               "verified_on": row.get("verified_on"), "source_url": row.get("source_url")})
        for k in keys:
            conn.execute("UPDATE market_suppliers SET msme_status = ?, msme_evidence = ? WHERE supplier_key = ?",
                         (f"VERIFIED_{cat}", evidence, k))
            matched += 1
    return {"updated": matched, "unmatched": unmatched}


def is_sme_candidate(status: str) -> bool:
    return status.startswith("VERIFIED_") or status == "SIZE_PROXY_SMALL"
