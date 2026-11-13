"""HTTP API for the primary objective: procurement restructuring and market (supplier) intelligence."""

from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import fetch_one, put_artifact, session
from ..evidence import audit
from ..ingestion.pdf_text import register_document
from ..market import profiles, sources
from ..market.fx import rates
from ..market.store import market_available, market_session, rows, status
from ..restructuring import classifier, competition
from ..restructuring.components import parse_boq
from ..restructuring.dossier import render_dossier
from ..restructuring.packaging import DEFAULT_PARAMS, DEFAULT_WEIGHTS
from ..restructuring.plan import load_plan, run_restructuring
from ..restructuring.taxonomy import CAPABILITY_KEYS, describe

router = APIRouter(prefix="/api")
SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class RestructureRequest(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict, description=f"Override any of {sorted(DEFAULT_WEIGHTS)}")
    params: dict[str, float] = Field(default_factory=dict, description=f"Override any of {sorted(DEFAULT_PARAMS)}")
    countries: Optional[list[str]] = Field(None, description="Market scope, e.g. ['India']; default TS_MARKET_COUNTRIES or all")
    actor: str = "system"


class ComponentValues(BaseModel):
    values: dict[str, float] = Field(..., description="capability -> value in ₹ crore (e.g. from the BOQ abstract)")
    actor: str = "procurement-officer"


def _tender(conn, tender_id: str) -> dict:
    t = fetch_one(conn, "SELECT * FROM tenders WHERE tender_id = ?", (tender_id,))
    if t is None:
        raise HTTPException(404, f"Unknown tender {tender_id}")
    return t


# --- Reference -------------------------------------------------------------------------

@router.get("/meta/capabilities", tags=["restructuring"])
def capabilities() -> dict:
    return {"capabilities": describe(), "weights": DEFAULT_WEIGHTS, "params": DEFAULT_PARAMS, "fx_inr_per_unit": rates()}


@router.get("/models", tags=["market"])
def models() -> dict:
    return {"capability_classifier": classifier.model_card(), "competition_model": competition.model_card()}


# --- Market (real award / bid data) -------------------------------------------------

@router.get("/market/status", tags=["market"])
def market_status() -> dict:
    if not market_available():
        return {"real_data_loaded": False, "sources": [], "counts": {}, "hint": "run scripts/fetch_real_data.py then build_market.py"}
    with market_session() as conn:
        return status(conn)


@router.get("/market/suppliers", tags=["market"])
def market_suppliers(q: Optional[str] = None, capability: Optional[str] = None, country: Optional[str] = None,
                     sme_only: bool = False, limit: int = Query(25, le=200)) -> list[dict]:
    if not market_available():
        return []
    sql, params = "SELECT * FROM market_suppliers WHERE 1=1", []
    if q:
        sql += " AND name LIKE ?"
        params.append(f"%{q}%")
    if country:
        sql += " AND lower(country) = ?"
        params.append(country.lower())
    if capability:
        if capability not in CAPABILITY_KEYS:
            raise HTTPException(400, f"Unknown capability {capability}")
        sql += " AND capabilities LIKE ?"
        params.append(f'%"{capability}"%')
    if sme_only:
        sql += " AND (msme_status LIKE 'VERIFIED_%' OR msme_status = 'SIZE_PROXY_SMALL')"
    sql += " ORDER BY n_awards DESC LIMIT ?"
    params.append(limit)
    with market_session() as conn:
        return rows(conn.execute(sql, params))


@router.get("/market/suppliers/{supplier_key:path}", tags=["market"])
def market_supplier(supplier_key: str, awards: int = Query(50, le=500)) -> dict:
    with market_session() as conn:
        prof = rows(conn.execute("SELECT * FROM market_suppliers WHERE supplier_key = ?", (supplier_key,)))
        if not prof:
            raise HTTPException(404, f"Unknown supplier {supplier_key}")
        recs = rows(conn.execute("SELECT * FROM market_awards WHERE supplier_key = ? ORDER BY signed_on DESC LIMIT ?",
                                 (supplier_key, awards)))
        n_bids = conn.execute("SELECT COUNT(*) FROM market_bids WHERE supplier_key = ?", (supplier_key,)).fetchone()[0]
    return {"profile": prof[0], "awards": recs, "bids_recorded": n_bids}


@router.post("/market/import", tags=["market"])
async def market_import(adapter: Literal["worldbank_awards", "ocds", "awards_csv"] = Form(...),
                        file: UploadFile = File(...), country: Optional[str] = Form(None),
                        source_id: Optional[str] = Form(None)) -> dict:
    """Load a published dataset file (World Bank awards CSV, OCDS JSON/JSONL, or an award-notice CSV)."""
    suffix = Path(file.filename or "data.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        path = Path(tmp.name)
    try:
        with market_session() as conn:
            result = sources.ingest(conn, adapter, path, source_id=source_id or f"{adapter}:{SAFE.sub('_', file.filename or 'upload')}",
                                    country=country, classify=classifier.classify_simple)
            result["profiles"] = profiles.rebuild_profiles(conn)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"Could not import: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)
    return result


UDYAM_CSV_HELP = "CSV: supplier_name|supplier_key, category, udyam_number, verified_on, source_url"


@router.post("/market/udyam", tags=["market"])
async def market_udyam(file: UploadFile = File(..., description=UDYAM_CSV_HELP)) -> dict:
    with market_session() as conn:
        return profiles.import_udyam_evidence(conn, (await file.read()).decode("utf-8-sig"))


# --- Tender inputs ----------------------------------------------------------------------

@router.post("/tenders/{tender_id}/documents", tags=["restructuring"])
async def add_tender_document(tender_id: str, file: UploadFile = File(...),
                              kind: Literal["tender_annex", "scope", "specification"] = Form("tender_annex")) -> dict:
    """Attach another part of the real tender bundle (Scope of Work, Technical Specifications...)."""
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Expected a PDF")
    with session() as conn:
        _tender(conn, tender_id)
        folder = get_settings().documents_dir / tender_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (SAFE.sub("_", file.filename or "annex.pdf"))
        path.write_bytes(content)
        n = conn.execute("SELECT COUNT(*) FROM documents WHERE tender_id = ?", (tender_id,)).fetchone()[0]
        return register_document(conn, document_id=f"DOC-{tender_id}-{kind.upper()}-{n + 1}", tender_id=tender_id,
                                 vendor_id=None, kind=kind, path=path)


@router.post("/tenders/{tender_id}/boq", tags=["restructuring"])
async def upload_boq(tender_id: str, file: UploadFile = File(..., description="Bill of Quantities: .xlsx, .xls or .csv")) -> dict:
    content = await file.read()
    try:
        boq_rows = parse_boq(content, file.filename or "boq.csv")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with session() as conn:
        _tender(conn, tender_id)
        folder = get_settings().documents_dir / tender_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / SAFE.sub("_", file.filename or "boq.csv")).write_bytes(content)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        put_artifact(conn, tender_id, "boq", {"document_id": f"BOQ-{tender_id}", "filename": file.filename, "rows": boq_rows}, now)
        total = sum(r["amount_inr"] or 0 for r in boq_rows)
    return {"tender_id": tender_id, "rows": len(boq_rows), "total_amount_inr_cr": round(total / 1e7, 4) if total else None}


@router.put("/tenders/{tender_id}/components/values", tags=["restructuring"])
def set_component_values(tender_id: str, body: ComponentValues) -> dict:
    bad = sorted(set(body.values) - set(CAPABILITY_KEYS))
    if bad:
        raise HTTPException(400, f"Unknown capabilities {bad}")
    with session() as conn:
        _tender(conn, tender_id)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        put_artifact(conn, tender_id, "component_values", body.values, now)
        audit.append(conn, tender_id, "COMPONENT_VALUES_SET", body.actor, body.values)
    return {"tender_id": tender_id, "values": body.values}


# --- Restructuring ----------------------------------------------------------------------

@router.post("/tenders/{tender_id}/restructure", tags=["restructuring"])
def restructure(tender_id: str, body: Optional[RestructureRequest] = None) -> dict:
    body = body or RestructureRequest()
    unknown = sorted((set(body.weights) - set(DEFAULT_WEIGHTS)) | (set(body.params) - set(DEFAULT_PARAMS)))
    if unknown:
        raise HTTPException(400, f"Unknown weight/param keys {unknown}")
    with session() as conn:
        _tender(conn, tender_id)
        try:
            plan = run_restructuring(conn, tender_id, weights=body.weights, params=body.params,
                                     countries=tuple(body.countries) if body.countries is not None else None)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit.append(conn, tender_id, "RESTRUCTURING_RUN", body.actor,
                     {"recommended": plan["recommendation"]["recommended_structure"], "weights": plan["structures"]["weights"]})
    return plan


@router.get("/tenders/{tender_id}/restructuring", tags=["restructuring"])
def get_restructuring(tender_id: str) -> dict:
    with session() as conn:
        plan = load_plan(conn, tender_id)
    if plan is None:
        raise HTTPException(409, f"Run POST /api/tenders/{tender_id}/restructure first")
    return plan


@router.post("/tenders/{tender_id}/restructuring/dossier", tags=["restructuring"])
def restructuring_dossier(tender_id: str) -> dict:
    with session() as conn:
        plan = load_plan(conn, tender_id)
    if plan is None:
        raise HTTPException(409, f"Run POST /api/tenders/{tender_id}/restructure first")
    out = get_settings().data_dir / "reports" / f"restructuring_{tender_id}.pdf"
    result = render_dossier(plan, out)
    return {**result, "url": f"/api/tenders/{tender_id}/restructuring/dossier.pdf"}


@router.get("/tenders/{tender_id}/restructuring/dossier.pdf", tags=["restructuring"])
def restructuring_dossier_file(tender_id: str) -> FileResponse:
    out = get_settings().data_dir / "reports" / f"restructuring_{tender_id}.pdf"
    if not out.exists():
        raise HTTPException(404, "Generate it first with POST .../restructuring/dossier")
    return FileResponse(out, media_type="application/pdf", filename=out.name)
