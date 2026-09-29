"""HTTP API consumed by the React dashboard and the blockchain / dossier module.

Full contract: docs/backend-api.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from .. import pipeline
from ..compliance.engine import compliance_matrix, run_compliance
from ..config import get_settings
from ..db import dumps, fetch_all, fetch_one, get_artifact, session
from ..demo.generator import load_demo
from ..demo.scenario import DEMO_TENDER_ID
from ..demo.tamper import restore_documents, tamper_document
from ..evidence import audit
from ..evidence.bundle import finalize_snapshot, list_snapshots, load_bundle, snapshot_summary, verify_snapshot
from ..evidence.dossier import dossier_data
from ..graph.builder import build_graph, relationship_paths, tender_view, vendor_view
from ..ingestion.facts import ingest_vendor_facts
from ..ingestion.pdf_text import document_pages
from ..ingestion.upload import add_bidders, create_tender_from_pdf, parse_bidders_csv
from ..nlp.extract import extract_rulebook, load_rules
from ..nlp.llm_extractor import llm_available
from ..nlp.rulebook import METRICS
from ..reasoning.counterfactual import NotTestable, evaluate_removal, robustness_report
from ..reasoning.engine import load_finding
from ..reasoning.scoring import scoring_rule
from .schemas import (
    AnalyzeRequest,
    BiddersUpload,
    CounterfactualRequest,
    DispositionRequest,
    ExtractRequest,
    FinalizeRequest,
    TamperRequest,
)

router = APIRouter(prefix="/api")


def _require_tender(conn, tender_id: str) -> dict:
    tender = fetch_one(conn, "SELECT * FROM tenders WHERE tender_id = ?", (tender_id,))
    if tender is None:
        raise HTTPException(404, f"Unknown tender {tender_id}")
    return tender


def _require_artifact(conn, tender_id: str, stage: str):
    body = get_artifact(conn, tender_id, stage)
    if body is None:
        raise HTTPException(409, f"Stage '{stage}' has not run for {tender_id} - POST /api/tenders/{tender_id}/analyze")
    return body


def _require_finding(conn, finding_id: str) -> dict:
    finding = load_finding(conn, finding_id)
    if finding is None:
        raise HTTPException(404, f"Unknown finding {finding_id}")
    return finding


# --- System ----------------------------------------------------------------------

@router.get("/health", tags=["system"])
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "extractor": s.extractor, "llm_available": llm_available(), "llm_model": s.llm_model,
            "embedding_backend": s.embedding_backend, "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@router.get("/meta/metrics", tags=["system"])
def metrics() -> dict:
    return {"metrics": METRICS}


@router.get("/meta/scoring", tags=["system"])
def scoring() -> dict:
    return scoring_rule()


# --- Demo mode -------------------------------------------------------------------

@router.post("/demo/load", tags=["demo"])
def demo_load(analyze: bool = Query(False, description="Also run the full analysis pipeline")) -> dict:
    summary = load_demo()
    summary.pop("documents")
    if analyze:
        summary["analysis"] = pipeline.run_analysis(DEMO_TENDER_ID)
    return summary


@router.post("/demo/tamper", tags=["demo"])
def demo_tamper(body: TamperRequest) -> dict:
    with session() as conn:
        try:
            return tamper_document(conn, body.document_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


@router.post("/demo/restore", tags=["demo"])
def demo_restore() -> dict:
    with session() as conn:
        return restore_documents(conn, DEMO_TENDER_ID)


# --- Tenders & documents ---------------------------------------------------------

@router.get("/tenders", tags=["tenders"])
def list_tenders(include_history: bool = False) -> list[dict]:
    with session() as conn:
        sql = "SELECT * FROM tenders" + ("" if include_history else " WHERE is_current = 1") + " ORDER BY tender_id"
        return fetch_all(conn, sql)


@router.get("/tenders/{tender_id}", tags=["tenders"])
def get_tender(tender_id: str) -> dict:
    with session() as conn:
        tender = _require_tender(conn, tender_id)
        bidders = fetch_all(
            conn,
            "SELECT b.vendor_id, v.alias, v.name, b.amount_cr, b.submitted_at FROM bids b "
            "JOIN vendors v ON v.vendor_id = b.vendor_id WHERE b.tender_id = ? ORDER BY b.vendor_id",
            (tender_id,),
        )
        docs = fetch_all(conn, "SELECT document_id, vendor_id, kind, filename, pages, sha256 FROM documents "
                               "WHERE tender_id = ? ORDER BY document_id", (tender_id,))
        historical = conn.execute("SELECT COUNT(*) FROM tenders WHERE source = 'history'").fetchone()[0]
        stages = [r["stage"] for r in fetch_all(conn, "SELECT stage FROM artifacts WHERE tender_id = ?", (tender_id,))]
        return {**tender, "bidders": bidders, "documents": docs, "historical_tenders_available": historical,
                "completed_stages": stages}


@router.get("/tenders/{tender_id}/documents", tags=["tenders"])
def list_documents(tender_id: str) -> list[dict]:
    with session() as conn:
        _require_tender(conn, tender_id)
        return fetch_all(conn, "SELECT document_id, vendor_id, kind, filename, pages, sha256 FROM documents "
                               "WHERE tender_id = ? ORDER BY document_id", (tender_id,))


@router.get("/documents/{document_id}", tags=["tenders"])
def get_document(document_id: str) -> dict:
    with session() as conn:
        doc = fetch_one(conn, "SELECT document_id, tender_id, vendor_id, kind, filename, pages, sha256 FROM documents "
                              "WHERE document_id = ?", (document_id,))
        if doc is None:
            raise HTTPException(404, f"Unknown document {document_id}")
        doc["page_text"] = [{"page": p, "text": t} for p, t in document_pages(conn, document_id)]
        return doc


@router.get("/documents/{document_id}/file", tags=["tenders"])
def get_document_file(document_id: str) -> FileResponse:
    with session() as conn:
        doc = fetch_one(conn, "SELECT filename, path FROM documents WHERE document_id = ?", (document_id,))
    if doc is None or not Path(doc["path"]).exists():
        raise HTTPException(404, f"Unknown document {document_id}")
    return FileResponse(doc["path"], media_type="application/pdf", filename=doc["filename"])


# --- Analysis workflow -----------------------------------------------------------

@router.post("/tenders/{tender_id}/analyze", tags=["analysis"])
def analyze(tender_id: str, body: Optional[AnalyzeRequest] = None) -> dict:
    body = body or AnalyzeRequest()
    try:
        return pipeline.run_analysis(tender_id, body.method, body.actor)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/tenders/{tender_id}/rules/extract", tags=["analysis"])
def extract_rules(tender_id: str, body: Optional[ExtractRequest] = None) -> dict:
    with session() as conn:
        _require_tender(conn, tender_id)
        try:
            return extract_rulebook(conn, tender_id, (body or ExtractRequest()).method)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/tenders/{tender_id}/rules", tags=["analysis"])
def get_rules(tender_id: str) -> dict:
    with session() as conn:
        _require_tender(conn, tender_id)
        extraction = get_artifact(conn, tender_id, "rule_extraction") or {}
        return {"tender_id": tender_id, "method": extraction.get("method"), "model": extraction.get("model"),
                "warnings": extraction.get("warnings", []), "rules": load_rules(conn, tender_id)}


@router.get("/tenders/{tender_id}/clauses", tags=["analysis"])
def get_clauses(tender_id: str) -> dict:
    with session() as conn:
        extraction = _require_artifact(conn, tender_id, "rule_extraction")
        return {"tender_id": tender_id, "clauses": extraction["clauses"]}


@router.post("/tenders/{tender_id}/compliance/run", tags=["analysis"])
def run_compliance_endpoint(tender_id: str) -> dict:
    with session() as conn:
        _require_tender(conn, tender_id)
        ingest_vendor_facts(conn, tender_id)
        try:
            return run_compliance(conn, tender_id)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/tenders/{tender_id}/compliance", tags=["analysis"])
def get_compliance(tender_id: str) -> dict:
    with session() as conn:
        _require_tender(conn, tender_id)
        return compliance_matrix(conn, tender_id)


@router.get("/tenders/{tender_id}/compliance/{vendor_id}", tags=["analysis"])
def get_vendor_compliance(tender_id: str, vendor_id: str) -> dict:
    with session() as conn:
        matrix = compliance_matrix(conn, tender_id)
        if vendor_id not in matrix["cells"]:
            raise HTTPException(404, f"No compliance results for {vendor_id}")
        vendor = next(v for v in matrix["vendors"] if v["vendor_id"] == vendor_id)
        rules = {r["rule_id"]: r for r in matrix["rules"]}
        return {**vendor, "evaluations": [{**cell, "rule": rules[rid]} for rid, cell in sorted(matrix["cells"][vendor_id].items())]}


@router.get("/tenders/{tender_id}/entities", tags=["intelligence"])
def get_entities(tender_id: str) -> dict:
    with session() as conn:
        return _require_artifact(conn, tender_id, "entities")


@router.get("/tenders/{tender_id}/graph", tags=["intelligence"])
def get_graph(tender_id: str) -> dict:
    with session() as conn:
        _require_artifact(conn, tender_id, "entities")
        g = build_graph(conn, tender_id)
        view = tender_view(g, tender_id)
        view["analysis"] = get_artifact(conn, tender_id, "graph")
        return view


@router.get("/tenders/{tender_id}/graph/vendors/{vendor_id}", tags=["intelligence"])
def get_vendor_graph(tender_id: str, vendor_id: str, depth: int = Query(2, ge=1, le=3)) -> dict:
    with session() as conn:
        _require_artifact(conn, tender_id, "entities")
        try:
            return vendor_view(build_graph(conn, tender_id), vendor_id, depth)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


@router.get("/tenders/{tender_id}/graph/paths", tags=["intelligence"])
def get_paths(tender_id: str, a: str, b: str, include_tenders: bool = False) -> dict:
    with session() as conn:
        _require_artifact(conn, tender_id, "entities")
        g = build_graph(conn, tender_id)
        if f"vendor:{a}" not in g or f"vendor:{b}" not in g:
            raise HTTPException(404, "Unknown vendor")
        return {"a": a, "b": b, "paths": relationship_paths(g, a, b, include_tenders)}


@router.get("/tenders/{tender_id}/similarity", tags=["intelligence"])
def get_similarity(tender_id: str) -> dict:
    with session() as conn:
        result = _require_artifact(conn, tender_id, "similarity")
        return {**result, "pairs": [{k: v for k, v in p.items() if k not in ("sections", "passages")}
                                    for p in result["pairs"]]}


@router.get("/tenders/{tender_id}/similarity/{a}/{b}", tags=["intelligence"])
def get_similarity_pair(tender_id: str, a: str, b: str) -> dict:
    with session() as conn:
        result = _require_artifact(conn, tender_id, "similarity")
    pair = next((p for p in result["pairs"] if sorted(p["vendors"]) == sorted([a, b])), None)
    if pair is None:
        raise HTTPException(404, "No similarity result for that pair")
    return {**pair, "backend": result["backend"], "baseline": result["baseline"]}


@router.get("/tenders/{tender_id}/behaviour", tags=["intelligence"])
def get_behaviour(tender_id: str, include_history: bool = False) -> dict:
    with session() as conn:
        result = _require_artifact(conn, tender_id, "behaviour")
    if not include_history:
        result["pairs"] = [{k: v for k, v in p.items() if k != "history"} for p in result["pairs"]]
    return result


# --- Findings, reasoning & counterfactuals ----------------------------------------

@router.get("/tenders/{tender_id}/findings", tags=["findings"])
def list_findings(tender_id: str, category: Optional[str] = None) -> list[dict]:
    with session() as conn:
        _require_tender(conn, tender_id)
        sql, params = "SELECT finding_id FROM findings WHERE tender_id = ?", [tender_id]
        if category:
            sql += " AND category = ?"
            params.append(category.upper())
        out = []
        for row in fetch_all(conn, sql + " ORDER BY finding_id", params):
            f = load_finding(conn, row["finding_id"])
            out.append({k: f[k] for k in ("finding_id", "category", "title", "signal", "level", "status",
                                          "recommendation", "subject")}
                       | {"evidence_count": len(f["evidence"]), "data_quality": f["data_quality"]["level"]})
        return out


@router.get("/findings/{finding_id}", tags=["findings"])
def get_finding(finding_id: str) -> dict:
    """Full Evidence Card."""
    with session() as conn:
        finding = _require_finding(conn, finding_id)
        finding["audit"] = audit.history(conn, finding["tender_id"], finding_id)
        return finding


@router.get("/findings/{finding_id}/reasoning", tags=["findings"])
def get_reasoning(finding_id: str) -> dict:
    with session() as conn:
        finding = _require_finding(conn, finding_id)
    return {"finding_id": finding_id, "level": finding["level"], "assessment": finding["assessment"],
            **finding["reasoning"], "evidence": finding["evidence"]}


@router.get("/findings/{finding_id}/robustness", tags=["findings"])
def get_robustness(finding_id: str) -> dict:
    with session() as conn:
        finding = _require_finding(conn, finding_id)
    try:
        return robustness_report(finding)
    except NotTestable as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/findings/{finding_id}/counterfactual", tags=["findings"])
def run_counterfactual(finding_id: str, body: CounterfactualRequest) -> dict:
    with session() as conn:
        finding = _require_finding(conn, finding_id)
        try:
            result = evaluate_removal(finding, body.remove)
        except NotTestable as exc:
            raise HTTPException(422, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(400, str(exc.args[0])) from exc
        if body.record:
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cur = conn.execute(
                "INSERT INTO counterfactual_runs (finding_id, removed, run_result, created_at) VALUES (?, ?, ?, ?)",
                (finding_id, dumps(body.remove), dumps(result), created_at),
            )
            result["run_id"] = cur.lastrowid
            audit.append(conn, finding["tender_id"], "COUNTERFACTUAL_TEST", body.actor,
                         {"run_id": cur.lastrowid, "removed": body.remove, "status": result["status"],
                          "level_before": result["original"]["level"], "level_after": result["counterfactual"]["level"]},
                         finding_id=finding_id)
        return result


@router.get("/findings/{finding_id}/counterfactual", tags=["findings"])
def list_counterfactual_runs(finding_id: str) -> list[dict]:
    with session() as conn:
        _require_finding(conn, finding_id)
        return fetch_all(conn, "SELECT * FROM counterfactual_runs WHERE finding_id = ? ORDER BY run_id", (finding_id,))


@router.post("/findings/{finding_id}/disposition", tags=["findings"])
def post_disposition(finding_id: str, body: DispositionRequest) -> dict:
    with session() as conn:
        finding = _require_finding(conn, finding_id)
        try:
            entry = audit.record_disposition(conn, finding, body.decision, body.auditor, body.notes)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"finding_id": finding_id, "status": body.decision, "audit_entry": entry}


@router.get("/tenders/{tender_id}/audit-log", tags=["findings"])
def get_audit_log(tender_id: str) -> dict:
    with session() as conn:
        _require_tender(conn, tender_id)
        return {"entries": audit.history(conn, tender_id), "chain": audit.verify_chain(conn, tender_id)}


# --- Evidence, dossier & integrity (hand-off to blockchain module) -----------------

@router.get("/tenders/{tender_id}/dossier-data", tags=["evidence"])
def get_dossier_data(tender_id: str) -> dict:
    with session() as conn:
        try:
            return dossier_data(conn, tender_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


@router.post("/tenders/{tender_id}/evidence/finalize", tags=["evidence"])
def finalize(tender_id: str, body: FinalizeRequest) -> dict:
    with session() as conn:
        _require_tender(conn, tender_id)
        try:
            return finalize_snapshot(conn, tender_id, body.auditor, body.note)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/tenders/{tender_id}/evidence/snapshots", tags=["evidence"])
def get_snapshots(tender_id: str) -> list[dict]:
    with session() as conn:
        _require_tender(conn, tender_id)
        return list_snapshots(conn, tender_id)


@router.get("/evidence/snapshots/{snapshot_id}", tags=["evidence"])
def get_snapshot(snapshot_id: str, include_bundle: bool = False) -> dict:
    with session() as conn:
        try:
            data = load_bundle(conn, snapshot_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
    bundle = data["bundle"]
    summary = snapshot_summary(snapshot_id, bundle["tender"]["tender_id"], bundle["created_at"], data["bundle_hash"], bundle)
    if include_bundle:
        summary["bundle"] = bundle
        summary["canonical_json"] = data["canonical_json"]
    return summary


@router.get("/evidence/snapshots/{snapshot_id}/verify", tags=["evidence"])
def verify(snapshot_id: str) -> dict:
    with session() as conn:
        try:
            return verify_snapshot(conn, snapshot_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


# --- Exploration mode (uploads) ----------------------------------------------------

@router.post("/uploads/tender", tags=["exploration"])
async def upload_tender(
    file: UploadFile = File(..., description="Tender PDF"),
    tender_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    bid_deadline: Optional[str] = Form(None),
    method: Optional[str] = Form(None),
) -> dict:
    content = await file.read()
    with session() as conn:
        try:
            created = create_tender_from_pdf(conn, content, file.filename or "tender.pdf", tender_id, title,
                                             department, bid_deadline)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        rulebook = extract_rulebook(conn, created["tender_id"], method)
    return {**created, "rulebook": rulebook}


@router.post("/uploads/{tender_id}/bidders", tags=["exploration"])
def upload_bidders_json(tender_id: str, body: BiddersUpload) -> dict:
    with session() as conn:
        try:
            return add_bidders(conn, tender_id, [b.model_dump() for b in body.bidders])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


@router.post("/uploads/{tender_id}/bidders.csv", tags=["exploration"])
async def upload_bidders_csv(tender_id: str, file: UploadFile = File(...)) -> dict:
    text = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_bidders_csv(text)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"Could not parse CSV: {exc}") from exc
    with session() as conn:
        try:
            return add_bidders(conn, tender_id, rows)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc


@router.post("/uploads/{tender_id}/bidders.json", tags=["exploration"])
async def upload_bidders_file(tender_id: str, file: UploadFile = File(...)) -> dict:
    try:
        payload = json.loads(await file.read())
        body = BiddersUpload.model_validate(payload if isinstance(payload, dict) else {"bidders": payload})
    except ValueError as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    return upload_bidders_json(tender_id, body)
