"""Adapters that load real, published procurement datasets into the market store.

Supported formats (all published by their owners as open data):

``worldbank_awards``
    World Bank "Major Contract Awards" CSV (finances.worldbank.org). Filter to a borrower country
    with ``country="India"``. Columns are matched by name, tolerant of the variants the dataset has
    used over the years.
``ocds``
    Open Contracting Data Standard release packages / record packages (.json) or one release per
    line (.jsonl). Uses tender items' classification (CPV when the scheme is CPV), awards,
    suppliers and the bids extension when present.
``prozorro``
    The Prozorro (Ukraine) tender / bid / contract tables derived from the public Prozorro API and
    published under CC BY 4.0 by the Thesis Institute (github.com/ThesisInstitute/procurement).
    Real multi-bidder data with CPV codes: used for the competition model and relationship
    screening examples.
``awards_csv``
    A plain CSV for records compiled by hand from official notices, e.g. CPPP / eProcure
    "Award of Contract" pages. Columns: award_id, tender_ref, title, description, buyer,
    supplier_name, supplier_country, amount, currency, signed_on, cpv, country, source_url.

No adapter invents values: anything missing in the source stays NULL.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from ..entities.resolution import company_core
from ..restructuring.taxonomy import OTHER, capability_for_cpv
from .fx import to_inr_cr
from .store import drop_source

Classifier = Callable[[list[str]], list[tuple[str, float]]]


# --------------------------------------------------------------------------- helpers

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_text(path: Path) -> io.TextIOBase:
    if path.suffix == ".gz":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8-sig", newline="")
    return open(path, encoding="utf-8-sig", newline="")


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


def _pick(row: dict, *names: str):
    for n in names:
        v = row.get(_norm_header(n))
        if v not in (None, ""):
            return v
    return None


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _date(v) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-01-01"
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%d-%b-%Y", "%b %d, %Y", "%d.%m.%Y", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def supplier_key(name: str, country: str | None, identifier: str | None = None, scheme: str | None = None) -> str:
    if identifier:
        return f"{(scheme or 'ID').upper()}:{identifier.strip()}"
    core = company_core(name) or name.lower().strip()
    return f"NAME:{(country or 'XX').upper()[:3]}:{core}"


JV_SPLIT = re.compile(r"\s*(?:\bjv\b|\bconsortium\b|\bin association with\b|\bjoint venture\b)\s*", re.I)


def jv_partners(name: str) -> list[str]:
    """Split "A Ltd - B Pvt Ltd JV" / "A & B (JV)" style supplier strings into partner names."""
    if not re.search(r"\b(jv|consortium|joint venture|in association with)\b", name, re.I):
        return []
    cleaned = JV_SPLIT.sub(" | ", re.sub(r"[()]", " ", name))
    parts = [p.strip(" -,;|") for p in re.split(r"\s+(?:&|and|\+|-|/|,|\|)\s+|\|", cleaned)]
    parts = [p for p in parts if len(p) > 3]
    return parts if len(parts) >= 2 else []


# --------------------------------------------------------------------------- adapters

def iter_worldbank_awards(path: Path, country: str | None = None) -> Iterator[dict]:
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            r = {_norm_header(k): v for k, v in raw.items() if k}
            borrower = _pick(r, "Borrower Country", "country", "Country")
            if country and (borrower or "").strip().lower() != country.lower():
                continue
            supplier = _pick(r, "Supplier", "vendor_name", "Supplier Name")
            if not supplier:
                continue
            amount = _num(_pick(r, "Supplier Contract Amount (USD)", "Total Contract Amount (USD)", "amount",
                                "Contract Amount (USD)"))
            contract_no = _pick(r, "WB Contract Number", "Contract Number")
            desc = _pick(r, "Contract Description", "description", "Contract Title") or ""
            yield {
                "award_id": f"WB-{contract_no or hashlib.sha1((supplier + desc).encode()).hexdigest()[:12]}"
                            f"-{hashlib.sha1(supplier.encode()).hexdigest()[:6]}",
                "tender_ref": _pick(r, "Borrower Contract Reference Number") or contract_no,
                "project_id": _pick(r, "Project ID"),
                "buyer": _pick(r, "Project Name"),
                "title": desc[:200],
                "description": desc,
                "category": _pick(r, "Procurement Category", "Procurement Type"),
                "method": _pick(r, "Procurement Method"),
                "country": borrower,
                "region": _pick(r, "Region"),
                "signed_on": _date(_pick(r, "Contract Signing Date", "year")),
                "supplier_name": supplier.strip(),
                "supplier_country": _pick(r, "Supplier Country", "vendor_country"),
                "amount": amount,
                "currency": "USD",
                "sector": _pick(r, "Major Sector"),
            }


def _ocds_releases(path: Path) -> Iterator[dict]:
    if path.suffix in (".jsonl", ".gz") or path.name.endswith(".jsonl.gz"):
        with _open_text(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield from _unwrap_ocds(json.loads(line))
        return
    with open(path, encoding="utf-8") as fh:
        yield from _unwrap_ocds(json.load(fh))


def _unwrap_ocds(doc: dict) -> Iterator[dict]:
    if "releases" in doc:
        yield from doc["releases"]
    elif "records" in doc:
        for rec in doc["records"]:
            yield rec.get("compiledRelease") or (rec.get("releases") or [{}])[-1]
    else:
        yield doc


def iter_ocds(path: Path, country: str | None = None) -> Iterator[tuple[dict | None, list[dict]]]:
    """Yield (award, bids) pairs; award may be None for releases that only carry bids."""
    for rel in _ocds_releases(path):
        tender = rel.get("tender") or {}
        parties = {p.get("id"): p for p in rel.get("parties") or []}
        buyer = (rel.get("buyer") or {}).get("name")
        items = tender.get("items") or []
        cpv = next((i["classification"]["id"] for i in items
                    if (i.get("classification") or {}).get("scheme", "").upper() == "CPV"), None)
        text = " ".join(filter(None, [tender.get("title"), tender.get("description")] +
                                [i.get("description") for i in items]))
        tref = rel.get("ocid") or tender.get("id")
        bids = []
        for d in ((rel.get("bids") or {}).get("details") or []):
            for t in d.get("tenderers") or []:
                party = parties.get(t.get("id"), {})
                ident = (party.get("identifier") or {})
                bids.append({"tender_ref": tref, "lot_ref": None, "supplier_name": t.get("name") or party.get("name"),
                             "supplier_key": supplier_key(t.get("name") or "", None, ident.get("id"), ident.get("scheme")),
                             "amount": (d.get("value") or {}).get("amount"),
                             "currency": (d.get("value") or {}).get("currency"),
                             "won": None, "rank": None, "bid_date": d.get("date"), "cpv": cpv})
        awards = rel.get("awards") or []
        if not awards and bids:
            yield None, bids
        for a in awards:
            if a.get("status") not in (None, "active", "pending"):
                continue
            for s in a.get("suppliers") or []:
                party = parties.get(s.get("id"), {})
                ident = (party.get("identifier") or {})
                addr = party.get("address") or {}
                yield {
                    "award_id": f"OCDS-{tref}-{a.get('id')}-{s.get('id') or s.get('name')}",
                    "tender_ref": tref, "project_id": None, "buyer": buyer,
                    "title": a.get("title") or tender.get("title"), "description": a.get("description") or text,
                    "cpv": cpv, "category": tender.get("mainProcurementCategory"),
                    "method": tender.get("procurementMethodDetails") or tender.get("procurementMethod"),
                    "country": country or addr.get("countryName"), "region": addr.get("region"),
                    "signed_on": _date(a.get("date")), "supplier_name": s.get("name") or party.get("name") or "",
                    "supplier_country": addr.get("countryName"),
                    "supplier_identifier": ident.get("id"), "supplier_scheme": ident.get("scheme"),
                    "amount": (a.get("value") or {}).get("amount"), "currency": (a.get("value") or {}).get("currency"),
                    "n_bidders": tender.get("numberOfTenderers"),
                }, bids
                bids = []  # attach bids once per release


def iter_awards_csv(path: Path, country: str | None = None) -> Iterator[dict]:
    with _open_text(path) as fh:
        for i, raw in enumerate(csv.DictReader(fh)):
            r = {_norm_header(k): v for k, v in raw.items() if k}
            name = _pick(r, "supplier_name", "supplier", "awarded_to", "contractor")
            if not name:
                continue
            yield {
                "award_id": _pick(r, "award_id") or f"CSV-{path.stem}-{i}",
                "tender_ref": _pick(r, "tender_ref", "tender_id", "reference_no"),
                "project_id": _pick(r, "project_id"),
                "buyer": _pick(r, "buyer", "organisation", "organization", "department"),
                "title": _pick(r, "title", "work_name", "tender_title"),
                "description": _pick(r, "description", "title", "work_name") or "",
                "cpv": _pick(r, "cpv"),
                "category": _pick(r, "category"),
                "method": _pick(r, "method"),
                "country": _pick(r, "country") or country,
                "region": _pick(r, "region", "state"),
                "signed_on": _date(_pick(r, "signed_on", "award_date", "date")),
                "supplier_name": name.strip(),
                "supplier_country": _pick(r, "supplier_country") or country,
                "supplier_identifier": _pick(r, "supplier_gstin", "gstin", "supplier_id"),
                "supplier_scheme": "IN-GSTIN" if _pick(r, "supplier_gstin", "gstin") else None,
                "amount": _num(_pick(r, "amount", "value", "contract_value")),
                "currency": _pick(r, "currency") or "INR",
                "source_url": _pick(r, "source_url", "url"),
            }


PROZORRO_FILES = ("tenders.csv.gz", "contracts.csv.gz", "bids.csv.gz")


def iter_prozorro(folder: Path) -> tuple[Iterator[dict], Iterator[dict]]:
    """Join the derived Prozorro tables: contracts -> tenders (CPV, buyer); bids carry lot CPV."""
    tenders: dict[str, dict] = {}
    with _open_text(folder / "tenders.csv.gz") as fh:
        for r in csv.DictReader(fh):
            tenders[r["tender_id"]] = {"tenderID": r["tenderID"], "buyer": r["buyer_name"], "region": r["region"],
                                       "cpv_group": r["cpv_group"], "cpv_division": r["cpv_division"],
                                       "category": r["main_category"], "method": r["method"], "n_bids": r["n_bids"]}

    def awards() -> Iterator[dict]:
        with _open_text(folder / "contracts.csv.gz") as fh:
            for r in csv.DictReader(fh):
                t = tenders.get(r["tender_id"])
                if not t or not r.get("supplier_name"):
                    continue
                yield {
                    "award_id": f"UA-{r['contract_id']}", "tender_ref": t["tenderID"], "lot_ref": r.get("lot_id") or None,
                    "project_id": None, "buyer": t["buyer"], "title": None, "description": "",
                    "cpv": t["cpv_group"] or t["cpv_division"], "category": t["category"], "method": t["method"],
                    "country": "Ukraine", "region": t["region"], "signed_on": _date(r.get("tc_dateSigned") or r.get("award_date")),
                    "supplier_name": r["supplier_name"], "supplier_country": "Ukraine",
                    "supplier_identifier": r.get("supplier_id"), "supplier_scheme": "UA-EDR",
                    "amount": _num(r.get("award_value")), "currency": "UAH",
                    "n_bidders": int(float(t["n_bids"])) if t["n_bids"] else None,
                }

    def bids() -> Iterator[dict]:
        with _open_text(folder / "bids.csv.gz") as fh:
            for r in csv.DictReader(fh):
                t = tenders.get(r["tender_id"])
                yield {
                    "tender_ref": t["tenderID"] if t else r["tender_id"], "lot_ref": r.get("lot_id") or None,
                    "supplier_name": r["bidder_name"],
                    "supplier_key": supplier_key(r["bidder_name"], "UA", r.get("bidder_id"), "UA-EDR"),
                    "amount": _num(r.get("amount")), "currency": "UAH",
                    "won": 1 if r.get("won_lot") == "True" else 0,
                    "rank": int(float(r["rank_in_lot"])) if r.get("rank_in_lot") else None,
                    "bid_date": r.get("bid_date"), "cpv": r.get("lot_cpv_group") or r.get("lot_cpv_division"),
                }

    return awards(), bids()


ADAPTERS = ("worldbank_awards", "ocds", "prozorro", "awards_csv")
DEFAULT_META = {
    "worldbank_awards": ("World Bank Major Contract Awards",
                         "https://finances.worldbank.org/Procurement/Major-Contract-Awards/kdui-wcs3", "CC BY 4.0"),
    "ocds": ("Open Contracting Data Standard publication", "https://data.open-contracting.org/", "publisher licence"),
    "prozorro": ("Prozorro tenders, bids and contracts (derived tables, Thesis Institute)",
                 "https://github.com/ThesisInstitute/procurement/tree/main/prozorro", "CC BY 4.0"),
    "awards_csv": ("Award records compiled from official notices", "https://eprocure.gov.in/epublish/app",
                   "as published"),
}


# --------------------------------------------------------------------------- ingestion

def ingest(conn: sqlite3.Connection, adapter: str, path: Path, *, source_id: str | None = None,
           country: str | None = None, classify: Classifier | None = None, title: str | None = None,
           origin_url: str | None = None, licence: str | None = None, notes: str | None = None,
           limit: int | None = None) -> dict:
    """Load one dataset. Re-importing the same ``source_id`` replaces its rows."""
    if adapter not in ADAPTERS:
        raise ValueError(f"Unknown adapter {adapter}; expected one of {ADAPTERS}")
    path = Path(path)
    source_id = source_id or f"{adapter}:{path.stem}{':' + country.lower() if country else ''}"
    drop_source(conn, source_id)
    sha = sha256_file(path) if path.is_file() else hashlib.sha256(
        "".join(sha256_file(path / f) for f in PROZORRO_FILES).encode()).hexdigest()

    if adapter == "worldbank_awards":
        award_iter, bid_iter = iter_worldbank_awards(path, country), iter(())
    elif adapter == "awards_csv":
        award_iter, bid_iter = iter_awards_csv(path, country), iter(())
    elif adapter == "prozorro":
        award_iter, bid_iter = iter_prozorro(path)
    else:
        pairs = list(iter_ocds(path, country))
        award_iter = (a for a, _ in pairs if a)
        bid_iter = (b for _, bs in pairs for b in bs)

    n_awards = _write_awards(conn, source_id, award_iter, classify, limit)
    n_bids = _write_bids(conn, source_id, bid_iter, limit)
    d_title, d_url, d_lic = DEFAULT_META[adapter]
    conn.execute(
        "INSERT OR REPLACE INTO market_sources (source_id, adapter, title, origin_url, licence, country_scope,"
        " file_sha256, rows_awards, rows_bids, imported_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (source_id, adapter, title or d_title, origin_url or d_url, licence or d_lic, country, sha, n_awards, n_bids,
         datetime.now(timezone.utc).isoformat(timespec="seconds"), notes),
    )
    return {"source_id": source_id, "awards": n_awards, "bids": n_bids, "sha256": sha}


def _write_awards(conn, source_id, awards, classify, limit, batch=2000) -> int:
    count, buf = 0, []

    def flush():
        texts = [b["description"] or b["title"] or "" for b in buf]
        need = [i for i, b in enumerate(buf) if not b.get("cpv") and texts[i].strip()]
        predicted = dict(zip(need, classify([texts[i] for i in need]))) if classify and need else {}
        out = []
        for i, a in enumerate(buf):
            if a.get("cpv"):
                cap, basis = capability_for_cpv(a["cpv"]), "cpv"
            elif i in predicted:
                cap, conf = predicted[i]
                basis = f"text_model:{conf:.2f}"
            else:
                cap, basis = OTHER, "none"
            key = supplier_key(a["supplier_name"], a.get("supplier_country"), a.get("supplier_identifier"),
                               a.get("supplier_scheme"))
            out.append((a["award_id"], source_id, a.get("tender_ref"), a.get("lot_ref"), a.get("project_id"),
                        a.get("buyer"), a.get("title"), a.get("description"), a.get("cpv"), cap, basis,
                        a.get("category"), a.get("method"), a.get("country"), a.get("region"), a.get("signed_on"),
                        key, a["supplier_name"], a.get("supplier_country"), a.get("amount"), a.get("currency"),
                        to_inr_cr(a.get("amount"), a.get("currency")), a.get("n_bidders")))
        conn.executemany("INSERT OR REPLACE INTO market_awards VALUES (" + ",".join("?" * 23) + ")", out)
        buf.clear()

    for a in awards:
        buf.append(a)
        count += 1
        if len(buf) >= batch:
            flush()
        if limit and count >= limit:
            break
    if buf:
        flush()
    return count


def _write_bids(conn, source_id, bids, limit, batch=5000) -> int:
    count, buf = 0, []
    for b in bids:
        buf.append((source_id, b["tender_ref"], b.get("lot_ref"), b["supplier_key"], b["supplier_name"] or "",
                    b.get("amount"), b.get("currency"), b.get("won"), b.get("rank"), b.get("bid_date"),
                    capability_for_cpv(b.get("cpv")) if b.get("cpv") else None))
        count += 1
        if len(buf) >= batch:
            conn.executemany("INSERT INTO market_bids (source_id, tender_ref, lot_ref, supplier_key, supplier_name,"
                             " amount, currency, won, rank, bid_date, capability) VALUES (?,?,?,?,?,?,?,?,?,?,?)", buf)
            buf.clear()
        if limit and count >= limit * 3:
            break
    if buf:
        conn.executemany("INSERT INTO market_bids (source_id, tender_ref, lot_ref, supplier_key, supplier_name,"
                         " amount, currency, won, rank, bid_date, capability) VALUES (?,?,?,?,?,?,?,?,?,?,?)", buf)
    return count
