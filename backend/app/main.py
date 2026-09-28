"""TenderShield Nexus backend - FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000   (from backend/)
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(
        title="TenderShield Nexus API",
        version="0.1.0",
        description="Explainable tender assurance & evidence intelligence: rule extraction, compliance, "
                    "relationship graph, bid intelligence, evidence reasoning, counterfactual robustness, "
                    "human disposition and evidence integrity.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
