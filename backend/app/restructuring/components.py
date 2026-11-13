"""Stage 2-3: tender understanding -> work items -> capability components.

Works on real tender bundles (NIT / RFP / Scope of Work / Technical Specifications PDFs) and,
when supplied, a Bill of Quantities (CSV / XLSX). Every item keeps its provenance: document,
page and the exact source text, so the auditor can check what the system read.

Values are never invented. Order of preference for a component's value:
  1. BOQ amounts (``value_basis = "boq"``)
  2. amounts written next to the item in the tender text (``"document"``)
  3. a share of the tender's stated estimated value by number of scope items
     (``"assumed_item_share"`` - shown as an assumption and editable by the user)
  4. otherwise ``None`` (``"unknown"``)
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

from .classifier import classify, label
from .taxonomy import OTHER

ITEM_START = re.compile(r"^\s*(?:\(?\d{1,3}(?:\.\d{1,3}){0,3}[.)]?|\(?[a-z][.)]|\(?[ivx]{1,5}[.)]|[•●▪\-–*])\s+", re.I)
WORK_VERBS = re.compile(
    r"\b(supply(?:ing)?|install(?:ation|ing)?|provid(?:e|ing)|lay(?:ing)?|construct(?:ion|ing)?|commission(?:ing)?|"
    r"erect(?:ion|ing)?|fabricat(?:e|ion|ing)|design(?:ing)?|develop(?:ment|ing)?|testing|maintenance|"
    r"operat(?:e|ion)|dismantl(?:e|ing)|excavat(?:e|ion|ing)|implement(?:ation|ing)?|integrat(?:e|ion|ing)|"
    r"deploy(?:ment|ing)?|upgrad(?:e|ation)|augment(?:ation)?|repair(?:ing|s)?|painting|replacement|"
    r"retrofit(?:ting)?|survey(?:ing)?|calibrat(?:e|ion)|establish(?:ment|ing)?|improvement|marking|"
    r"setting up|creation|provision|procurement of|strengthening|rehabilitation|restor(?:e|ation|ing)|"
    r"renovat(?:e|ion|ing)|turfing|protection works?|widening|modernisation|modernization)\b", re.I)
SCOPE_SECTION = re.compile(r"\b(scope of (?:work|supply|services)|schedule of (?:quantities|requirements)|bill of quantities|"
                           r"\bboq\b|technical specifications?|work components?|description of works?|project components?|"
                           r"terms of reference)\b", re.I)
HEADING = re.compile(r"^(?:(?:section|part|chapter)\s+[\divxlc]+[.:\-]?\s*|\d{1,2}\.?\s+)?[A-Z][A-Za-z ,&/()\-]{3,80}$")
BOILERPLATE = re.compile(
    r"\b(turnover|earnest money|emd\b|bid security|performance security|penalt(?:y|ies)|liquidated damages|"
    r"arbitration|jurisdiction|blacklist|debarr|power of attorney|affidavit|eligib|pre-?qualification|"
    r"bank guarantee|tender fee|document fee|signature|seal|net worth|solvency|pan card|integrity pact|"
    r"force majeure|termination|similar work|bid validity|corrigend|online bid|e-?procurement portal|"
    r"digital signature|dsc\b|undertaking|declaration|indemnit|insurance|notice inviting tender|nit no|tender no|"
    # Notice / RFB boilerplate seen in real World Bank and state e-procurement notices
    r"received financing|applied for financing|financing from|loan no|credit no|grant no|procurement regulations|"
    r"bidding documents?|construction period|completion period|period of completion|e-?mail|mobile no|telephone|"
    r"tel\.? no|ifsc|account no|name of bank|evaluat\w*|weightings?|registration|user id|password|website|www\.|"
    r"https?://|implementation unit|pre-?bid|bid submission|opening of|last date|conflict of interest|"
    r"other details|liable|employer|(?:single|two)[- ]envelope|completion certificate|site not ready|"
    r"rfq document|rfb document|addend(?:um|a)|department(?=\s*[:;])|inviting authority|mode of tendering)\b", re.I)
# Labelled scope fields ("Name of work: ...", "Contract title: ...") and quoted work names in invitations.
SCOPE_FIELD = re.compile(r"^\s*(?:name of (?:the )?works?|contract title|title of (?:the )?(?:work|contract)|detail of works?|"
                         r"description of (?:the )?works?|scope of works?)\s*[:\-–]\s*(?P<v>.{12,700})$", re.I)
QUOTED_WORK = re.compile(r"[\"“]\s*(?P<v>[^\"”]{15,300}?)\s*[\"”]")
# Line-item tables: a header naming the description column, then rows "<n>" / "<description>" / other cells.
TABLE_HEADER = re.compile(r"^\s*(?:description of (?:goods|works?|items?|services)|item description|name of (?:the )?works?|"
                          r"detail of works?|line item|particulars of (?:work|item)s?)\b", re.I)
ROW_NO = re.compile(r"^\s*(\d{1,3})\.?\s*$")
# Unnumbered work lists: "Details of Works" followed by one work per line, each optionally followed by
# "Estimated Cost: 11,51,66,390.81" (plain rupees, Indian digit grouping, often without "Rs.").
WORK_LIST_HEADER = re.compile(r"^\s*(?:details? of (?:the )?works?|list of works?|works? details|description of works?)\s*:?\s*$", re.I)
COST_LINE = re.compile(r"^\s*(?:estimated (?:cost|value)|cost|amount|value)\b[^:\d]*[:\-–]?\s*(?:rs\.?|inr|₹)?\s*"
                       r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crores?|cr\.?|lakhs?|lacs?)?", re.I)
NUMBERED_PARA = re.compile(r"^\s*\d{1,2}\.\s+\S.{40,}")
PAGE_NOISE = re.compile(r"^(page \d+( of \d+)?|\d+|-\s*\d+\s*-)$", re.I)

MONEY = re.compile(
    r"(?:(?:rs\.?|inr|₹)\s*)(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crores?|cr\.?|lakhs?|lacs?|lakh)?"
    r"|(?P<num2>\d[\d,]*(?:\.\d+)?)\s*(?P<unit2>crores?|lakhs?|lacs?)\b", re.I)
ESTIMATE = re.compile(r"(estimated (?:cost|value)|tender value|cost of (?:the )?work|project cost|contract value)", re.I)


def parse_money_cr(text: str) -> float | None:
    """First money amount in ``text`` converted to ₹ crore, or None."""
    m = MONEY.search(text)
    if not m:
        return None
    num = (m.group("num") or m.group("num2") or "").replace(",", "")
    unit = (m.group("unit") or m.group("unit2") or "").lower()
    try:
        value = float(num)
    except ValueError:
        return None
    if unit.startswith("cr"):
        return value
    if unit.startswith(("lakh", "lac")):
        return value / 100
    return value / 1e7  # plain rupees


def stated_estimate_cr(pages: list[tuple[str, int, str]]) -> tuple[float | None, dict | None]:
    for doc, page, text in pages:
        for line in text.splitlines():
            if ESTIMATE.search(line):
                v = parse_money_cr(line)
                if v and v >= 0.01:
                    return round(v, 4), {"document_id": doc, "page": page, "quote": line.strip()[:240]}
    return None, None


def segment_blocks(pages: list[tuple[str, int, str]]) -> list[dict]:
    """Group lines into candidate scope blocks with page provenance."""
    blocks: list[dict] = []
    cur: dict | None = None
    section = ""
    for doc, page, text in pages:
        for raw in text.splitlines():
            line = raw.strip()
            if not line or PAGE_NOISE.match(line):
                continue
            if HEADING.match(line) and not line.endswith((".", ";")) and len(line.split()) <= 10:
                section = line
                cur = None
                continue
            starts = bool(ITEM_START.match(line))
            ends_prev = cur is not None and cur["text"].rstrip().endswith((".", ":", ";"))
            if cur is None or starts or (ends_prev and line[:1].isupper()) or cur["doc"] != doc or len(cur["text"]) > 700:
                cur = {"doc": doc, "page": page, "text": line, "section": section}
                blocks.append(cur)
            else:
                cur["text"] = f"{cur['text']} {line}"
    return blocks


def is_scope_text(text: str, section: str = "") -> bool:
    t = text.strip()
    if not 30 <= len(t) <= 900 or BOILERPLATE.search(t):
        return False
    return bool(WORK_VERBS.search(t)) or (bool(SCOPE_SECTION.search(section)) and bool(ITEM_START.match(t)))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip("\"“”").strip()).rstrip(" .;,")


def line_item_rows(pages: list[tuple[str, int, str]]) -> list[dict]:
    """Rows of line-item tables whose cells were flattened one per line (common in real notices and PDFs).

    After a header such as "Description of Goods", a bare row number equal to the next expected row
    ("1", "2." ...) followed by a text line starts an item; the description continues over lines that
    open with "(" or a lowercase letter and stops at the next numeric cell.
    """
    rows: list[dict] = []
    for doc, page, text in pages:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        in_table, expected, i = False, 1, 0
        while i < len(lines):
            line = lines[i]
            if TABLE_HEADER.match(line):
                in_table, expected = True, 1
            elif in_table and NUMBERED_PARA.match(line):
                in_table = False
            elif in_table and (m := ROW_NO.match(line)) and int(m.group(1)) == expected:
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if re.search(r"[A-Za-z]{3}", nxt) and not ROW_NO.match(nxt) and not nxt[:1].isdigit():
                    desc, j = nxt, i + 2
                    while j < len(lines) and (lines[j][:1] == "(" or lines[j][:1].islower()) and not ROW_NO.match(lines[j]):
                        desc, j = f"{desc} {lines[j]}", j + 1
                    rows.append({"doc": doc, "page": page, "text": _clean(desc), "section": "line items"})
                    expected += 1
                    i = j
                    continue
            i += 1
    return rows


def _cost_cr(line: str) -> float | None:
    m = COST_LINE.match(line)
    if not m:
        return None
    unit = (m.group("unit") or "").lower()
    try:
        value = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    if unit.startswith("cr"):
        return value
    if unit.startswith(("lakh", "lac")):
        return value / 100
    return value / 1e7  # plain rupees


def listed_work_rows(pages: list[tuple[str, int, str]]) -> list[dict]:
    """Works listed one per line under "Details of Works", with the cost line that follows each."""
    rows: list[dict] = []
    for doc, page, text in pages:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        in_list, skip_to = False, -1
        for i, line in enumerate(lines):
            if i <= skip_to:
                continue
            if WORK_LIST_HEADER.match(line):
                in_list = True
                continue
            if not in_list or COST_LINE.match(line):
                continue
            # The list ends at the next short heading ("Tender Schedule") or a key: value field.
            if (len(line.split()) <= 4 and not line.endswith(".")) or re.match(r"^[A-Za-z /&()]{3,40}:\s", line):
                in_list = False
                continue
            # A work wrapped over several PDF lines continues until a line ends with "." or a cost line follows.
            j = i
            while not lines[j].rstrip().endswith(".") and j + 1 < len(lines) and not COST_LINE.match(lines[j + 1]) \
                    and not WORK_LIST_HEADER.match(lines[j + 1]) and j - i < 4:
                j += 1
            work = " ".join(lines[i:j + 1])
            skip_to = j
            if not WORK_VERBS.search(work) or BOILERPLATE.search(work):
                continue
            nxt = lines[j + 1] if j + 1 < len(lines) else ""
            rows.append({"doc": doc, "page": page, "text": _clean(work), "section": "listed works", "amount_inr_cr": _cost_cr(nxt)})
    return rows


def scope_field_blocks(pages: list[tuple[str, int, str]]) -> list[dict]:
    """Explicitly labelled or quoted work names: "Name of work: ...", 'invited for " Restoration of ... "'."""
    out = []
    for doc, page, text in pages:
        for line in text.splitlines():
            m = SCOPE_FIELD.match(line)
            values = [m.group("v")] if m else [q.group("v") for q in QUOTED_WORK.finditer(line)]
            for v in values:
                v = _clean(v)
                if WORK_VERBS.search(v) and not BOILERPLATE.search(v):
                    out.append({"doc": doc, "page": page, "text": v, "section": "scope field"})
    return out


def items_from_documents(pages: list[tuple[str, int, str]], min_conf: float = 0.35,
                         title: str | None = None) -> tuple[list[dict], list[dict]]:
    """Scope items from tender text, most specific evidence first.

    1. line-item table rows, 2. labelled / quoted work names, 3. scope-like paragraphs,
    4. the tender title, used only when the documents yield nothing else.
    """
    tagged = [(b, "listed_work") for b in listed_work_rows(pages)]
    tagged += [(b, "line_item") for b in line_item_rows(pages)]
    tagged += [(b, "scope_field") for b in scope_field_blocks(pages)]
    tagged += [(b, "document") for b in segment_blocks(pages) if is_scope_text(b["text"], b.get("section", ""))]
    if not tagged and title and WORK_VERBS.search(title):
        tagged = [({"doc": None, "page": None, "text": _clean(title), "section": "tender title"}, "title")]
    seen, unique = set(), []
    for b, src in tagged:
        b = {**b, "source": src}
        key = re.sub(r"\W+", " ", b["text"].lower()).strip()
        # Skip exact repeats and paragraphs that only restate an item already taken.
        if key in seen or any(key in k or k in key for k in seen if min(len(k), len(key)) >= 25):
            continue
        seen.add(key)
        unique.append(b)
    preds = classify([ITEM_START.sub("", b["text"]) for b in unique])
    items, unassigned = [], []
    for b, (cap, conf, dist, hits) in zip(unique, preds):
        item = {"text": b["text"][:600], "document_id": b["doc"], "page": b["page"], "section": b.get("section") or None,
                "capability": cap,
                "confidence": round(conf, 3), "alternatives": dist, "keywords": sorted({k for v in hits.values() for k in v}),
                "amount_inr_cr": b.get("amount_inr_cr") or (None if ESTIMATE.search(b["text"]) else parse_money_cr(b["text"])),
                "source": b["source"]}
        # Table rows, labelled work names and the title are explicit scope: keep them even at low
        # confidence (flagged in data quality). Free-text paragraphs need min_conf.
        explicit = b["source"] != "document"
        (items if cap != OTHER and (explicit or conf >= min_conf) else unassigned).append(item)
    return items, unassigned


BOQ_DESC = ("description", "item description", "description of item", "particulars", "item", "work description")
BOQ_AMOUNT = ("amount", "total amount", "amount (rs)", "amount in rs", "total", "value", "estimated amount")
BOQ_QTY = ("quantity", "qty")
BOQ_UNIT = ("unit", "units", "uom")
BOQ_RATE = ("rate", "unit rate", "rate (rs)", "estimated rate")


def _find_col(header: list[str], names: tuple[str, ...]) -> int | None:
    norm = [re.sub(r"[^a-z ()]", "", (h or "").lower()).strip() for h in header]
    for n in names:
        if n in norm:
            return norm.index(n)
    for i, h in enumerate(norm):
        if any(h.startswith(n) for n in names):
            return i
    return None


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def parse_boq(content: bytes, filename: str) -> list[dict]:
    """Rows of a BOQ (CSV or XLSX). Finds the header row by its 'description' column."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        table = [[c for c in r] for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]
    elif filename.lower().endswith(".xls"):
        try:
            import xlrd  # CPPP BOQs are often legacy .xls
        except ImportError as exc:
            raise ValueError("Legacy .xls BOQ needs the 'xlrd' package - or save the sheet as .xlsx/.csv") from exc
        book = xlrd.open_workbook(file_contents=content)
        table = [sh.row_values(i) for sh in book.sheets() for i in range(sh.nrows)]
    else:
        table = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    header_idx = next((i for i, r in enumerate(table[:60]) if _find_col([str(c or "") for c in r], BOQ_DESC) is not None), None)
    if header_idx is None:
        raise ValueError("Could not find a BOQ header row with a 'Description' column")
    header = [str(c or "") for c in table[header_idx]]
    d, a, q, u, r_ = (_find_col(header, BOQ_DESC), _find_col(header, BOQ_AMOUNT), _find_col(header, BOQ_QTY),
                      _find_col(header, BOQ_UNIT), _find_col(header, BOQ_RATE))
    rows = []
    for n, r in enumerate(table[header_idx + 1:], start=header_idx + 2):
        desc = str(r[d] or "").strip() if d is not None and d < len(r) else ""
        if len(desc) < 8:
            continue
        amount = _num(r[a]) if a is not None and a < len(r) else None
        qty = _num(r[q]) if q is not None and q < len(r) else None
        rate = _num(r[r_]) if r_ is not None and r_ < len(r) else None
        if amount is None and qty is not None and rate is not None:
            amount = qty * rate
        rows.append({"row": n, "description": desc, "quantity": qty, "unit": str(r[u]).strip() if u is not None and u < len(r) and r[u] else None,
                     "rate": rate, "amount_inr": amount})
    return rows


def items_from_boq(rows: list[dict], document_id: str) -> tuple[list[dict], list[dict]]:
    preds = classify([r["description"] for r in rows])
    items, unassigned = [], []
    for r, (cap, conf, dist, hits) in zip(rows, preds):
        item = {"text": r["description"][:600], "document_id": document_id, "page": None, "row": r["row"],
                "capability": cap, "confidence": round(conf, 3), "alternatives": dist,
                "keywords": sorted({k for v in hits.values() for k in v}),
                "amount_inr_cr": round(r["amount_inr"] / 1e7, 6) if r["amount_inr"] else None,
                "quantity": r["quantity"], "unit": r["unit"], "source": "boq"}
        (items if cap != OTHER else unassigned).append(item)
    return items, unassigned


def build_components(items: list[dict], estimate_cr: float | None, overrides: dict[str, float] | None = None) -> list[dict]:
    by_cap: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_cap[it["capability"]].append(it)
    comps = []
    for cap, its in sorted(by_cap.items(), key=lambda kv: -len(kv[1])):
        boq_vals = [i["amount_inr_cr"] for i in its if i["source"] == "boq" and i["amount_inr_cr"]]
        doc_vals = [i["amount_inr_cr"] for i in its if i["source"] != "boq" and i["amount_inr_cr"]]
        if boq_vals:
            value, basis = sum(boq_vals), "boq"
        elif doc_vals:
            value, basis = sum(doc_vals), "document"
        else:
            value, basis = None, "unknown"
        comps.append({"capability": cap, "label": label(cap), "items": sorted(its, key=lambda i: -i["confidence"]),
                      "n_items": len(its), "value_inr_cr": round(value, 4) if value else None, "value_basis": basis,
                      "pages": sorted({i["page"] for i in its if i["page"]}),
                      "mean_confidence": round(sum(i["confidence"] for i in its) / len(its), 3)})
    # Allocate the remainder of the stated estimate across components without a value.
    known = sum(c["value_inr_cr"] or 0 for c in comps)
    missing = [c for c in comps if c["value_inr_cr"] is None]
    if estimate_cr and missing and estimate_cr > known:
        remainder = estimate_cr - known
        total_items = sum(c["n_items"] for c in missing)
        for c in missing:
            c["value_inr_cr"] = round(remainder * c["n_items"] / total_items, 4)
            c["value_basis"] = "assumed_item_share"
    for c in comps:
        if overrides and c["capability"] in overrides:
            c["value_inr_cr"], c["value_basis"] = float(overrides[c["capability"]]), "user_override"
    for i, c in enumerate(comps, start=1):
        c["component_id"] = f"C{i}"
    return comps
