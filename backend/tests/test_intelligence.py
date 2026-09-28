from app.db import get_artifact, session
from app.intelligence.similarity import split_sections

from .conftest import TENDER


def test_split_sections():
    pages = [(1, "Header\n1. Company Profile\nWe are a firm.\nPage 1 of 2"),
             (2, "Header\n2. Risk Management\nRisks are tracked in a weekly register. Every risk has a named owner.\nPage 2 of 2")]
    sections = split_sections(pages)
    assert [s.title for s in sections] == ["Company Profile", "Risk Management"]
    assert sections[1].page == 2 and len(sections[1].sentences) == 2


def test_vendor_a_b_documents_are_most_similar(analyzed):
    with session() as conn:
        sim = get_artifact(conn, TENDER, "similarity")
    top = sim["pairs"][0]
    assert top["vendors"] == ["V001", "V002"]
    assert top["document_similarity"] > sim["baseline"]["median"] + 0.25
    assert "Implementation Methodology" in top["high_overlap_sections"]
    assert top["passages"] and top["passages"][0]["a"]["page"] >= 1
    c_d = next(p for p in sim["pairs"] if p["vendors"] == ["V003", "V004"])
    assert c_d["document_similarity"] < 0.65


def test_behaviour_flags_planted_pair(analyzed):
    with session() as conn:
        beh = get_artifact(conn, TENDER, "behaviour")
    pairs = {tuple(p["vendors"]): p for p in beh["pairs"]}
    ab = pairs[("V001", "V002")]
    assert ab["co_bids"] == 5 and ab["rotation_count"] == 5
    assert all(ab["flags"].values())
    assert ab["anomaly"]["is_outlier"]
    cd = pairs[("V003", "V004")]
    assert cd["co_bids"] == 1 and not any(cd["flags"].values())
