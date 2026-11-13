"""Procurement Restructuring & Supplier Intelligence Dossier (PDF).

Sections A-F follow the project definition: original procurement, proposed restructuring, SME
opportunity map, supplier relationships, scenario comparison, recommendation - plus data sources,
model cards and limitations, so every number in the report can be traced.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .taxonomy import LABELS

NAVY = colors.HexColor("#14213d")
FONT_CANDIDATES = [  # a Unicode font so supplier names in any script render; Helvetica is the fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def _font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "TSUnicode" in pdfmetrics.getRegisteredFontNames():
        return "TSUnicode"
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("TSUnicode", path))
                return "TSUnicode"
            except Exception:  # noqa: BLE001 - unusable font file, try the next
                continue
    return "Helvetica"
GREY = colors.HexColor("#e9ecef")


def _styles():
    ss = getSampleStyleSheet()
    f = _font()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], textColor=NAVY, fontSize=16, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=NAVY, fontSize=12.5, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontName=f, fontSize=9, leading=12),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontName=f, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#495057")),
        "cell": ParagraphStyle("cell", parent=ss["BodyText"], fontName=f, fontSize=7.8, leading=9.6),
    }


def _esc(text) -> str:
    s = (str(text) if text is not None else "-").replace("₹", "Rs ").replace("≥", ">=")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(rows, widths, st, header=True):
    data = [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#adb5bd")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), GREY)]
    t.setStyle(TableStyle(style))
    return t


def _cr(v) -> str:
    return "unknown" if v is None else f"Rs {v:,.2f} Cr"


def render_dossier(plan: dict, out_path: Path) -> dict:
    st = _styles()
    rec = plan["recommendation"]
    story = [Paragraph("Procurement Restructuring &amp; Supplier Intelligence Dossier", st["h1"]),
             Paragraph(f"Tender {_esc(plan['tender_id'])} - {_esc(plan['tender_title'])}<br/>Generated {plan['generated_at']} "
                       "by TenderShield Nexus (decision support - not an award decision)", st["small"]),
             Spacer(1, 4 * mm), Paragraph(_esc(rec["headline"]), st["h2"])]

    story += [Paragraph("A. Original procurement", st["h2"]),
              Paragraph(f"Estimated value: {_cr(plan['estimated_value_inr_cr'])}. Current structure: "
                        f"{_esc(rec['current_structure'])}.", st["body"])]
    rows = [["ID", "Component", "Items", "Value", "Value basis", "Source pages"]]
    for c in plan["components"]:
        rows.append([c["component_id"], c["label"], c["n_items"], _cr(c["value_inr_cr"]), c["value_basis"],
                     ", ".join(map(str, c["pages"])) or "BOQ"])
    story.append(_table(rows, [12 * mm, 52 * mm, 13 * mm, 26 * mm, 33 * mm, 40 * mm], st))

    story.append(Paragraph("B. Proposed restructuring", st["h2"]))
    story.append(Paragraph(_esc(rec["recommended_structure"]), st["body"]))
    for k in rec["keep_integrated"]:
        story.append(Paragraph(f"<b>Keep together:</b> {_esc(' + '.join(k['labels']))} - {_esc(' '.join(k['why']))}", st["body"]))
    if rec["cut_interfaces_to_manage"]:
        rows = [["Interface", "Weight", "Type"]] + [[f"{e['source']} - {e['target']}", e["weight"], ", ".join(e["types"])]
                                                     for e in rec["cut_interfaces_to_manage"]]
        story += [Spacer(1, 2 * mm), Paragraph("Interfaces the employer must manage if separated:", st["body"]),
                  _table(rows, [40 * mm, 20 * mm, 60 * mm], st)]

    story.append(Paragraph("C. SME opportunity map", st["h2"]))
    rows = [["Pkg", "Scope", "Value", "Turnover req.", "Capable firms", "Meet scale rule", "SME candidates", "Bidders (ind.)"]]
    for p in rec["packages"]:
        rows.append([p["package"], p["scope"], _cr(p["value_inr_cr"]), _cr(p["required_turnover_cr"]),
                     p["suppliers_with_full_capability_evidence"], p["of_which_meet_similar_work_scale"], p["sme_candidates"],
                     p["expected_bidders_indicator"]])
    story.append(_table(rows, [10 * mm, 50 * mm, 20 * mm, 20 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm], st))
    scen = plan["structures"]["scenarios"]["B_recommended"]
    for i, pk in enumerate(scen["packages"], start=1):
        rows = [["Supplier", "Country", "Status", "MSME status", "Score", "Evidence"]]
        for s in pk["match"]["shortlist"][:6]:
            ev = "; ".join(f"{e['awards_in_capability']} awards in {e['label']} (largest {e['largest_awards_inr_cr'][:1]})"
                           for e in s["evidence"])
            rows.append([s["name"], s["country"], s["status"], s["msme_status"], s["score"], ev])
        story += [Spacer(1, 2 * mm), Paragraph(f"P{i} potential supplier pool (top 6 of {sum(pk['match']['pool'].values())})",
                                               st["body"]), _table(rows, [40 * mm, 17 * mm, 30 * mm, 26 * mm, 15 * mm, 48 * mm], st)]

    rel = plan["relationships"]
    story.append(Paragraph("D. Supplier relationships (secondary objective)", st["h2"]))
    story.append(Paragraph(f"{rel['screened_suppliers']} shortlisted suppliers screened; {rel['requires_review']} "
                           f"relationship(s) require review. {_esc(rel['note'])}", st["body"]))
    if rel["edges"]:
        rows = [["Supplier A", "Supplier B", "Observed link", "Review score", "Ordinary explanations"]]
        for e in rel["edges"][:12]:
            rows.append([e["a_name"], e["b_name"], ", ".join(e["types"]), e["review_score"], "; ".join(e["alternative_explanations"])])
        story.append(_table(rows, [36 * mm, 36 * mm, 30 * mm, 16 * mm, 58 * mm], st))

    story.append(Paragraph("E. Scenario comparison", st["h2"]))
    rows = [["Scenario", "Packages", "Score", "Competition", "Coverage", "SME access", "Coordination", "Integration risk", "Scale loss"]]
    for key, s in plan["structures"]["scenarios"].items():
        if s:
            m = s["metrics"]
            rows.append([key.split("_", 1)[0], s["n_packages"], s["score"], m["competition"], m["coverage"], m["sme_access"],
                         m["coordination"], m["integration_risk"], m["scale_loss"]])
    story.append(_table(rows, [18 * mm, 16 * mm, 14 * mm, 20 * mm, 18 * mm, 18 * mm, 20 * mm, 22 * mm, 18 * mm], st))
    r = rec["robustness"]
    story.append(Paragraph(f"Weight sensitivity: the recommended structure stays best in {r['recommended_stays_best']:.0%} of "
                           f"{r['draws']} runs with every weight perturbed ({_esc(r['perturbation'])}). Weights: "
                           f"{_esc(json.dumps(plan['structures']['weights']))}", st["small"]))

    story.append(Paragraph("F. Recommendation", st["h2"]))
    story.append(Paragraph(_esc(rec["decision_note"]), st["body"]))
    for dq in plan["data_quality"]:
        story.append(Paragraph(f"[{dq['level']}] {_esc(dq['issue'])} - {_esc(dq['fix'])}", st["small"]))

    story += [PageBreak(), Paragraph("Data sources and models", st["h2"]),
              Paragraph(f"Market scope: {_esc(plan['market_scope']['countries'])}; {plan['market_scope']['awards_in_scope']} "
                        f"award records in scope from {_esc(', '.join(plan['market_scope']['sources']) or 'no datasets')}.",
                        st["body"])]
    for name, card in plan["models"].items():
        if card:
            data = "; ".join(f"{d['name']} ({d['rows']} rows)" for d in card["training_data"])
            story.append(Paragraph(f"<b>{_esc(name)}</b>: {_esc(card['algorithm'])}. Trained {card['trained_at']} on {_esc(data)}. "
                                   f"Metrics: {_esc(json.dumps(card['metrics']))}", st["small"]))
            for lim in card["limitations"]:
                story.append(Paragraph(f"- {_esc(lim)}", st["small"]))
    story.append(Paragraph("Capability taxonomy keys: " + _esc(", ".join(f"{k} = {v}" for k, v in LABELS.items())), st["small"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(15 * mm, 10 * mm, f"TenderShield Nexus - {plan['tender_id']} - restructuring dossier")
        canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                      bottomMargin=16 * mm, title="Procurement Restructuring Dossier").build(story, onFirstPage=footer,
                                                                                               onLaterPages=footer)
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()
    return {"path": str(out_path), "pdf_sha256": digest, "plan_sha256": plan_hash}
