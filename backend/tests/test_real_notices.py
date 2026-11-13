"""Extraction and classification on real World Bank India procurement notices (tests/fixtures/real_notices)."""

from pathlib import Path

import pytest

from app.restructuring.classifier import classify
from app.restructuring.components import items_from_documents

FIX = Path(__file__).parent / "fixtures" / "real_notices"


def _items(notice_id: str, title: str | None = None) -> list[dict]:
    pages = [(f"DOC-{notice_id}", 1, (FIX / f"{notice_id}.txt").read_text())]
    items, _ = items_from_documents(pages, title=title)
    return items


def _texts(items: list[dict]) -> str:
    return "\n".join(i["text"] for i in items).lower()


def test_millet_plant_line_items_are_extracted():
    items = _items("OP00474853")
    texts = _texts(items)
    for expected in ("primary processing line for millets", "continuous milling line", "cold extrusion line",
                     "cookies making line", "flaking line", "vacuum packing machine", "band sealing machine",
                     "platform weighing scale"):
        assert expected in texts, expected
    assert any(i["source"] == "line_item" for i in items)


@pytest.mark.parametrize("notice_id,junk", [
    ("OP00474853", ["received financing", "project implementation unit"]),
    ("OP00471901", ["construction period", "mobile no", "e-mail", "ifsc"]),
])
def test_boilerplate_is_not_a_work_item(notice_id, junk):
    texts = _texts(_items(notice_id))
    for phrase in junk:
        assert phrase not in texts, phrase


def test_metro_contract_title_is_the_scope():
    texts = _texts(_items("OP00471901"))
    assert "construction of viaduct and elevated stations" in texts


def test_substation_name_of_work_is_found_and_electrical():
    items = _items("OP00464558")
    work = [i for i in items if "132 kv gis" in i["text"].lower()]
    assert work, "the quoted 'Detail of Work' must become a scope item"
    assert work[0]["capability"] == "electrical"


def test_tender_title_counts_as_scope_when_document_has_none():
    items, _ = items_from_documents([("D", 1, "Bids must be submitted online.")],
                                    title="Supply and installation of 33 kV switchgear panels")
    assert [i["source"] for i in items] == ["title"]


def test_food_processing_machinery_has_its_own_capability():
    preds = classify(["Primary Processing Line for Millets (Vibro-Grader cum Aspirator, Destoner, dehuller)",
                      "Vacuum Packing Machine", "Cookies Making Line (rotary rack oven)", "Continuous Milling Line (Chakki mill and Roller mill)"])
    assert [p[0] for p in preds] == ["industrial_machinery"] * 4


def test_ukai_dam_lists_seven_works_with_their_estimated_costs():
    items = _items("OP00460403")
    listed = [i for i in items if i["source"] == "listed_work"]
    assert len(listed) == 7
    by_text = {i["text"][:40].lower(): i for i in listed}
    roads = next(i for t, i in by_text.items() if t.startswith("construction of new 3.75 m"))
    assert roads["amount_inr_cr"] == pytest.approx(11.5166, abs=1e-3)  # "Estimated Cost: 11,51,66,390.81" rupees
    assert any(t.startswith("turfing work") for t in by_text)
    assert any(t.startswith("renovation works of vip rest house") for t in by_text)
    assert all(i["amount_inr_cr"] for i in listed)


def test_ukai_dam_trades_are_separated():
    caps = {i["capability"] for i in _items("OP00460403") if i["source"] == "listed_work"}
    # Roads, dam-top lighting and CCTV/fire safety are distinct trades. (The SCADA gate-control line also
    # contains "Operation & Maintenance" and is currently labelled O&M - a known error, see
    # docs/results/real-data-check/README.md.)
    assert {"civil_works", "electrical", "telecom_networks"} <= caps


def test_ukai_dam_works_survive_pdf_line_wrapping():
    import textwrap

    text = (FIX / "OP00460403.txt").read_text()
    wrapped = "\n".join(w for para in text.splitlines() for w in (textwrap.wrap(para, 105) or [""]))
    items, _ = items_from_documents([("D", 1, wrapped)])
    listed = [i for i in items if i["source"] == "listed_work"]
    assert len(listed) == 7 and all(i["amount_inr_cr"] for i in listed)
    assert not any("department" in i["text"].lower() for i in items)


def test_tender_estimate_is_sum_of_stated_work_costs():
    from app.db import init_db, session
    from app.restructuring.plan import run_restructuring

    init_db()
    text = (FIX / "OP00460403.txt").read_text()
    with session() as conn:
        conn.execute("INSERT OR REPLACE INTO tenders (tender_id, title, status, is_current, source) VALUES (?, ?, ?, 0, ?)",
                     ("T-UKAI", "Seven works at Ukai Dam", "OPEN", "test"))
        conn.execute("INSERT OR REPLACE INTO documents (document_id, tender_id, kind, filename, path, sha256, pages) "
                     "VALUES (?, ?, 'tender', 'n.txt', 'n.txt', 'x', 1)", ("DOC-UKAI", "T-UKAI"))
        conn.execute("INSERT OR REPLACE INTO document_pages (document_id, page, text) VALUES (?, 1, ?)", ("DOC-UKAI", text))
        plan = run_restructuring(conn, "T-UKAI", countries=("India",))
    assert plan["estimated_value_inr_cr"] == pytest.approx(46.8376, abs=1e-3)
    assert plan["estimate_source"]["basis"].startswith("sum of item costs")
    # The split itself depends on the real market store (see docs/results/real-data-check); here we check that
    # the trades reach the packaging stage as separate components.
    assert len(plan["components"]) >= 3
