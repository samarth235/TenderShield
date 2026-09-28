from app.db import session
from app.ingestion.pdf_text import document_pages
from app.nlp import extract as extract_module
from app.nlp.extract import extract_rulebook, load_rules
from app.nlp.pattern_extractor import amount_in, extract_candidates
from app.nlp.segmentation import Clause, segment_clauses

from .conftest import TENDER


def test_amount_conversion():
    assert amount_in("not less than Rs. 10 crore", "crore") == 10
    assert amount_in("EMD of Rs. 20 lakh", "crore") == 0.2
    assert amount_in("INR 1.5 crore", "lakh") == 150


def test_one_clause_can_yield_two_rules():
    clause = Clause("4.2", "Technical", 4, "The Bidder shall have completed at least three similar projects during "
                    "the preceding five years with an aggregate value not less than Rs. 10 crore.")
    got = {(c["metric"], c["threshold"]) for c in extract_candidates([clause])}
    assert got == {("similar_projects_5y", 3.0), ("similar_projects_value_cr", 10.0)}


def test_descriptive_clauses_are_ignored():
    clause = Clause("2.1", "Scope", 2, "Supply and installation of adaptive signal controllers at 120 junctions.")
    assert extract_candidates([clause]) == []


def test_demo_tender_rulebook(analyzed):
    with session() as conn:
        rules = load_rules(conn, TENDER)
        clauses = segment_clauses(document_pages(conn, "DOC-TENDER"))
    assert len(rules) == 18
    assert sum(r["mandatory"] for r in rules) == 17  # ISO 27001 is "desirable"
    by_metric = {r["metric"]: r for r in rules}
    assert by_metric["avg_annual_turnover_cr"]["threshold"] == 10
    assert by_metric["emd_amount_lakh"]["threshold"] == 20
    assert by_metric["submitted_at"]["threshold"] == "2026-03-15T15:00:00+05:30"
    assert by_metric["udyam_registered"]["applies_if"]["metric"] == "claims_msme_exemption"
    assert not by_metric["iso27001_valid_until"]["mandatory"]
    # Every rule is traceable to its clause and page.
    clause_pages = {c.clause_id: c.page for c in clauses}
    for rule in rules:
        assert rule["source"]["page"] == clause_pages[rule["source"]["clause"]]
        assert rule["clause_text"]


def test_llm_failure_falls_back_to_pattern_extractor(analyzed, monkeypatch):
    def failing(clauses):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(extract_module, "extract_candidates_llm", failing)
    with session() as conn:
        result = extract_rulebook(conn, TENDER, "llm")
    assert result["method"] == "pattern"
    assert "network unavailable" in result["warnings"][0]
    assert result["rules_extracted"] == 18


def test_llm_candidates_are_normalised_into_rules(analyzed, monkeypatch):
    def fake(clauses):
        return [
            {"clause_id": "3.1", "metric": "avg_annual_turnover_cr", "operator": "gte", "threshold": 1000.0,
             "mandatory": True, "applies_if": None, "confidence": 0.95},
            {"clause_id": "8.3", "metric": "unmapped", "operator": "is_true", "threshold": True,
             "mandatory": True, "applies_if": None, "confidence": 0.4},
            {"clause_id": "99.9", "metric": "pan_available", "operator": "is_true", "threshold": True,
             "mandatory": True, "applies_if": None, "confidence": 0.9},  # hallucinated clause id: dropped
        ], "claude-opus-5"

    monkeypatch.setattr(extract_module, "extract_candidates_llm", fake)
    with session() as conn:
        result = extract_rulebook(conn, TENDER, "llm")
        extract_rulebook(conn, TENDER, "pattern")  # restore the demo rulebook for later tests
    assert result["method"] == "llm" and result["model"] == "claude-opus-5"
    assert [r["source"]["clause"] for r in result["rules"]] == ["3.1", "8.3"]
    assert result["rules"][0]["source"]["page"] == 3
    assert result["rules"][1]["category"] == "Unmapped" and result["unmapped_rules"] == 1
