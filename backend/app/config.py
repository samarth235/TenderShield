"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # python-dotenv is optional
    pass

BACKEND_DIR = Path(__file__).resolve().parents[1]
log = logging.getLogger(__name__)
# Used only when TS_AUTH_SECRET is unset outside production: sessions then end on restart.
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)


def _auth_secret() -> str:
    value = os.environ.get("TS_AUTH_SECRET", "")
    if value:
        if len(value) < 32:
            raise RuntimeError("TS_AUTH_SECRET must be at least 32 characters")
        return value
    if os.environ.get("TS_ENV", "development") == "production":
        raise RuntimeError("TS_AUTH_SECRET is required when TS_ENV=production")
    return _EPHEMERAL_SECRET


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("TS_DATA_DIR", str(BACKEND_DIR / "var"))))
    # Rule extraction: "pattern" (deterministic, offline), "llm" (Claude), or "auto" (LLM when a key is set).
    extractor: str = field(default_factory=lambda: _env("TS_EXTRACTOR", "pattern"))
    llm_model: str = field(default_factory=lambda: _env("TS_LLM_MODEL", "claude-opus-5"))
    # Bid similarity: "tfidf" (offline, deterministic) or "sbert" (requires requirements-ml.txt).
    embedding_backend: str = field(default_factory=lambda: _env("TS_EMBEDDING_BACKEND", "tfidf"))
    sbert_model: str = field(default_factory=lambda: _env("TS_SBERT_MODEL", "all-MiniLM-L6-v2"))
    # The fabricated demonstration dataset (TN-2026-014) is for tests and local rehearsal only.
    # It is never loaded automatically; /api/demo/* returns 404 unless this is enabled.
    enable_demo: bool = field(default_factory=lambda: _env("TS_ENABLE_DEMO", "0").lower() in {"1", "true", "yes"})
    random_seed: int = field(default_factory=lambda: int(_env("TS_RANDOM_SEED", "14")))
    env: str = field(default_factory=lambda: _env("TS_ENV", "development"))
    auth_secret: str = field(default_factory=_auth_secret)
    session_minutes: int = field(default_factory=lambda: int(_env("TS_SESSION_MINUTES", "480")))
    admin_email: str = field(default_factory=lambda: _env("TS_ADMIN_EMAIL", ""))
    admin_password: str = field(default_factory=lambda: _env("TS_ADMIN_PASSWORD", ""))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env("TS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000").split(",")
            if o.strip()
        )
    )

    # PostgreSQL in production, e.g. postgresql://user:pass@host:5432/tendershield.
    # Unset means a SQLite file in TS_DATA_DIR (local development and tests).
    database_url: str = field(default_factory=lambda: _env("TS_DATABASE_URL", ""))

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))

    @property
    def sqlalchemy_url(self) -> str:
        if self.is_postgres:
            return "postgresql+psycopg://" + self.database_url.split("://", 1)[1]
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tendershield.db"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"


def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    return settings
