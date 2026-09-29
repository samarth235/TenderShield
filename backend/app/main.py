"""TenderShield Nexus backend - FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000   (from backend/)
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api.routes import router
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _autoload_demo() -> None:
    """Seed the demo tender when the database is empty (hosts with ephemeral disks start blank)."""
    from .db import fetch_one, session
    from .demo.generator import load_demo
    from .demo.scenario import DEMO_TENDER_ID
    from .pipeline import run_analysis

    with session() as conn:
        if fetch_one(conn, "SELECT tender_id FROM tenders WHERE tender_id = ?", (DEMO_TENDER_ID,)):
            return
    log.info("Database empty: loading demo tender %s", DEMO_TENDER_ID)
    load_demo()
    run_analysis(DEMO_TENDER_ID)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if os.environ.get("TS_AUTOLOAD_DEMO", "").lower() in {"1", "true", "yes"}:
        _autoload_demo()
    yield


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built dashboard from the API origin, falling back to index.html for client-side routes."""
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(
        title="TenderShield Nexus API",
        version="0.1.0",
        description="Explainable tender assurance & evidence intelligence: rule extraction, compliance, "
                    "relationship graph, bid intelligence, evidence reasoning, counterfactual robustness, "
                    "human disposition and evidence integrity.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    # TS_STATIC_DIR points at frontend/dist in the single-container deployment.
    static_dir = os.environ.get("TS_STATIC_DIR")
    if static_dir and (Path(static_dir) / "index.html").is_file():
        _mount_frontend(app, Path(static_dir))
    return app


app = create_app()
