"""Primary objective: restructuring engine, market adapters, models and API."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.market import profiles, sources
from app.market.store import market_db_path, market_session
from app.restructuring import classifier, competition
from app.restructuring.components import build_components, items_from_documents, parse_boq, parse_money_cr
from app.restructuring.dependencies import build_dependency_graph
from app.restructuring.matching import MarketIndex, match_package, similar_work_met
from app.restructuring.packaging import compare_structures, set_partitions
from app.restructuring.relationships import screen_relationships
from app.restructuring.taxonomy import capability_for_cpv, lexicon_hits

FIX = Path(__file__).parent / "fixtures"

TENDER_TEXT = """Scope of Work
1.1 Supply, installation, testing and commissioning of 25,000 ultrasonic smart water meters with AMR modules.
1.2 Development and deployment of SCADA software and central dashboard; the software shall integrate with the meters over an open protocol (DLMS).
1.3 Laying of DI K7 pipes 300 mm dia including excavation, jointing and hydraulic testing.
1.4 Construction of RCC meter chambers and restoration of road cuts.
1.5 Comprehensive operation and maintenance of the complete system for five years.
2. Eligibility
2.1 The bidder shall have an average annual turnover of Rs 30 crore."""


@pytest.fixture(scope="module")
def market(tmp_path_factory):
    with market_session() as conn:
        sources.ingest(conn, "awards_csv", FIX / "awards_sample.csv", source_id="fixture:awards", country="India",
                       classify=classifier.classify_simple)
        sources.ingest(conn, "ocds", FIX / "ocds_sample.json", source_id="fixture:ocds", country="India")
        profiles.rebuild_profiles(conn)
    yield market_db_path()


# --- taxonomy & models (trained on real data; files are committed) --------------------

def test_cpv_mapping_longest_prefix_wins():
    assert capability_for_cpv("34632200-8") == "signalling_control"  # railway signalling, not vehicles
    assert capability_for_cpv("34100000-8") == "vehicles_equipment"
    assert capability_for_cpv("38421100-3") == "instrumentation_sensors"
    assert capability_for_cpv("45232151-5") == "mechanical_hvac_plumbing"
    assert capability_for_cpv("45210000-2") == "civil_works"


def test_lexicon_matches_plurals():
    assert "water meter" in lexicon_hits("Supply of water meters")["instrumentation_sensors"]


def test_classifier_card_reports_real_training_data():
    card = classifier.model_card()
    assert card and card["training_data"][0]["rows"] > 9000
    assert card["metrics"]["cv_macro_f1"] > 0.6
    cap, conf, _, _ = classifier.classify(["Supply and installation of 11 kV switchgear panels"])[0]
    assert cap == "electrical" and conf > 0.4


def test_competition_model_trained_on_real_lots():
    card = competition.model_card()
    assert card and card["training_data"][0]["rows"] > 50000
    assert card["metrics"]["poisson_deviance"] <= card["metrics"]["poisson_deviance_baseline"]
    assert 0.5 < competition.expected_bidders("civil_works", 10.0) < 10


# --- components & dependencies ---------------------------------------------------------

def _pages():
    return [("DOC-T", 3, TENDER_TEXT)]


def test_money_parsing_indian_units():
    assert parse_money_cr("Rs. 2,50,00,000") == pytest.approx(2.5)
    assert parse_money_cr("estimated at 45 lakh") == pytest.approx(0.45)
    assert parse_money_cr("₹12.5 crore") == pytest.approx(12.5)


def test_scope_items_extracted_with_provenance_and_boilerplate_excluded():
    items, _ = items_from_documents(_pages())
    caps = {i["capability"] for i in items}
    assert {"instrumentation_sensors", "ict_software", "operation_maintenance"} <= caps
    assert all(i["page"] == 3 and i["document_id"] == "DOC-T" for i in items)
    assert not any("turnover" in i["text"].lower() for i in items)


def test_component_values_never_invented():
    items, _ = items_from_documents(_pages())
    comps = build_components(items, None)
    assert all(c["value_inr_cr"] is None and c["value_basis"] == "unknown" for c in comps)
    comps = build_components(items, 50.0)
    assert sum(c["value_inr_cr"] for c in comps) == pytest.approx(50.0)
    assert {c["value_basis"] for c in comps} == {"assumed_item_share"}


def test_boq_csv_parsing_and_amount_from_rate():
    csv_text = "Sl,Description of Item,Qty,Unit,Rate,Amount\n1,Supply of ultrasonic water meters DN15,1000,Nos,5000,\n" \
               "2,Laying DI pipes 300 mm,2000,m,4000,8000000\n"
    rows = parse_boq(csv_text.encode(), "boq.csv")
    assert rows[0]["amount_inr"] == 5_000_000 and rows[1]["amount_inr"] == 8_000_000


def test_dependency_graph_open_standard_relief_and_text_evidence():
    items, _ = items_from_documents(_pages())
    comps = build_components(items, 50.0)
    dep = build_dependency_graph(comps, _pages())
    cid = {c["capability"]: c["component_id"] for c in comps}
    edge = next(e for e in dep["edges"] if {e["source"], e["target"]} == {cid["instrumentation_sensors"], cid["ict_software"]})
    assert edge["text_evidence"] and edge["text_evidence"][0]["page"] == 3
    assert edge["open_standard_evidence"]  # DLMS named -> interface is defined -> lower coupling
    assert edge["weight"] < edge["prior"] + 0.3


# --- optimiser ---------------------------------------------------------------------------

def test_set_partitions_bell_numbers():
    assert [len(set_partitions(list(range(n)))) for n in range(1, 6)] == [1, 2, 5, 15, 52]


def _comps(spec):
    return [{"component_id": f"C{i}", "capability": cap, "label": cap, "value_inr_cr": v, "n_items": 1}
            for i, (cap, v) in enumerate(spec, start=1)]


def test_strong_dependencies_are_never_split(market):
    comps = _comps([("signalling_control", 20), ("ict_software", 10), ("civil_works", 15)])
    dep = build_dependency_graph(comps, [])
    with market_session() as conn:
        idx = MarketIndex.load(conn, ("India",))
    out = compare_structures(comps, dep, idx, sensitivity_draws=20)
    for s in out["scenarios"].values():
        for pk in s["packages"]:
            assert ("C1" in pk["components"]) == ("C2" in pk["components"])
    assert out["scenarios"]["A_integrated"]["n_packages"] == 1


def test_integrated_contract_can_win():
    # Two strongly coupled components only: splitting is infeasible, so A is the recommendation.
    comps = _comps([("signalling_control", 20), ("ict_software", 10)])
    out = compare_structures(comps, build_dependency_graph(comps, []), MarketIndex(), sensitivity_draws=10)
    assert out["scenarios"]["B_recommended"]["n_packages"] == 1
    assert not out["recommendation_differs_from_current"]


# --- market data, matching, relationships --------------------------------------------

def test_similar_work_rule():
    assert similar_work_met([9.0], 10.0)[0] is True              # one of 80 %
    assert similar_work_met([6.0, 5.5], 10.0)[0] is True         # two of 50 %
    assert similar_work_met([4.5, 4.2, 4.0], 10.0)[0] is True    # three of 40 %
    assert similar_work_met([7.0, 3.0], 10.0)[0] is False


def test_market_ingest_and_matching(market):
    with market_session() as conn:
        idx = MarketIndex.load(conn, ("India",))
        rec = conn.execute("SELECT capability, capability_basis FROM market_awards WHERE award_id='T3'").fetchone()
    assert rec["capability"] == "instrumentation_sensors" and rec["capability_basis"] == "cpv"
    m = match_package(idx, {"instrumentation_sensors": 3.0})
    top = m["shortlist"][0]
    assert top["name"] == "Beta Instruments" and top["status"] == "POTENTIALLY_SUITABLE"
    assert top["evidence"][0]["example_awards"]
    m2 = match_package(idx, {"instrumentation_sensors": 50.0})
    assert m2["shortlist"][0]["status"] == "LIMITED_SCALE_EVIDENCE"


def test_msme_status_is_proxy_until_udyam_evidence(market):
    with market_session() as conn:
        status = conn.execute("SELECT msme_status FROM market_suppliers WHERE name='Gamma Soft Solutions'").fetchone()[0]
        assert status == "SIZE_PROXY_SMALL"
        r = profiles.import_udyam_evidence(conn, "supplier_name,category,udyam_number\nGamma Soft Solutions,small,UDYAM-XX-00-0000000\n")
        assert r["updated"] == 1
        assert conn.execute("SELECT msme_status FROM market_suppliers WHERE name='Gamma Soft Solutions'").fetchone()[0] == "VERIFIED_SMALL"


def test_jv_and_cobidding_relationships(market):
    assert sources.jv_partners("Alpha Pipes Pvt Ltd - Delta Infra Ltd JV") == ["Alpha Pipes Pvt Ltd", "Delta Infra Ltd"]
    with market_session() as conn:
        keys = {r["name"]: r["supplier_key"] for r in conn.execute("SELECT name, supplier_key FROM market_suppliers")}
        names = {v: k for k, v in keys.items()}
        rel = screen_relationships(conn, [keys["Alpha Pipes Pvt Ltd"], keys["Delta Infra Ltd"],
                                          keys["Beta Instruments"], keys["Epsilon Meters"]], names, min_cobids=1)
    types = {t for e in rel["edges"] for t in e["types"]}
    assert {"joint_venture", "co_bidding"} <= types
    assert all(e["alternative_explanations"] for e in rel["edges"])


# --- API ----------------------------------------------------------------------------------

def test_restructuring_api_end_to_end(analyzed, market):
    from app.main import app

    from .conftest import auth_headers

    c = TestClient(app, headers=auth_headers("officer"))
    tid = analyzed["tender_id"]
    boq = "Description,Qty,Unit,Rate,Amount\nSITC of adaptive traffic signal controllers,120,Nos,1500000,\n" \
          "Command centre software and video wall integration,1,LS,90000000,\nRoad marking and junction geometry works,1,LS,,40000000\n" \
          "Operation and maintenance for five years,1,LS,,60000000\n"
    r = c.post(f"/api/tenders/{tid}/boq", files={"file": ("boq.csv", io.BytesIO(boq.encode()), "text/csv")})
    assert r.status_code == 200 and r.json()["rows"] == 4
    r = c.post(f"/api/tenders/{tid}/restructure", json={"countries": ["India"]})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert any(comp["value_basis"] == "boq" for comp in plan["components"])
    assert plan["structures"]["scenarios"]["A_integrated"]["n_packages"] == 1
    assert plan["recommendation"]["decision_note"]
    assert c.get(f"/api/tenders/{tid}/restructuring").status_code == 200
    d = c.post(f"/api/tenders/{tid}/restructuring/dossier").json()
    assert len(d["pdf_sha256"]) == 64
    assert c.get(d["url"]).headers["content-type"] == "application/pdf"
    assert c.get("/api/market/status").json()["real_data_loaded"] is True
    bad = c.post(f"/api/tenders/{tid}/restructure", json={"weights": {"nonsense": 1}})
    assert bad.status_code == 400
