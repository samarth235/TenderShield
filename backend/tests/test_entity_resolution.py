from app.db import get_artifact, session
from app.entities.resolution import company_core, normalise_address, normalise_company, person_name_compatible

from .conftest import TENDER


def test_company_name_normalisation():
    variants = ["ABC Constructions Pvt. Ltd.", "ABC Construction Private Limited", "ABC Constructions Pvt Ltd"]
    assert len({normalise_company(v) for v in variants}) == 1
    assert company_core("ABC Constructions Pvt. Ltd.") == "abc construction"


def test_person_names_with_initials():
    assert person_name_compatible("Rajesh K. Sharma", "Rajesh Kumar Sharma") >= 95
    assert person_name_compatible("Rajesh K. Sharma", "Rajesh Mohan Sharma") < 95


def test_address_normalisation():
    a, pin_a = normalise_address("Plot No. 14, Sector 5, Vashi, Navi Mumbai, Maharashtra 400703")
    b, pin_b = normalise_address("Plot 14, Sec-5, Vashi, Navi Mumbai - 400703")
    assert pin_a == pin_b == "400703"
    assert set(b.split()) <= set(a.split())


def test_historical_records_resolve_without_false_matches(analyzed):
    with session() as conn:
        truth = get_artifact(conn, TENDER, "demo_ground_truth")["bid_vendor"]
        linked = {str(r["bid_id"]): r["vendor_id"] for r in conn.execute("SELECT bid_id, vendor_id FROM bids")}
    wrong = [k for k, v in truth.items() if linked[k] is not None and linked[k] != v]
    missed = [k for k, v in truth.items() if v is not None and linked[k] is None]
    assert not wrong
    assert len(missed) / len(truth) < 0.02


def test_shared_entities(analyzed):
    with session() as conn:
        entities = get_artifact(conn, TENDER, "entities")
    links = {tuple(l["vendors"]): {x["type"] for x in l["links"]} for l in entities["shared_links"]}
    assert links[("V001", "V002")] == {"director", "address"}
    assert links[("V003", "V004")] == {"director"}
    assert {d["vendor_id"] for d in entities["data_quality"]} == {"V006"}
