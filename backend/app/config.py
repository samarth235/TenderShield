"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # python-dotenv is optional
    pass

BACKEND_DIR = Path(__file__).resolve().parents[1]


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
    random_seed: int = field(default_factory=lambda: int(_env("TS_RANDOM_SEED", "14")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env("TS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000").split(",")
            if o.strip()
        )
    )

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
