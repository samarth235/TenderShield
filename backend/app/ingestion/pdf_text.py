"""PDF text extraction and document registration (Stage 1 - Tender Ingestion)."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from pypdf import PdfReader

from ..db import dumps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pages(path: Path) -> list[str]:
    """Return the text of each page (1 string per page, whitespace-normalised per line)."""
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        pages.append("\n".join(line for line in lines if line))
    return pages


def register_document(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    tender_id: str,
    vendor_id: str | None,
    kind: str,
    path: Path,
    meta: dict | None = None,
) -> dict:
    pages = extract_pages(path)
    sha = sha256_file(path)
    conn.execute("DELETE FROM document_pages WHERE document_id = ?", (document_id,))
    conn.execute(
        "INSERT OR REPLACE INTO documents (document_id, tender_id, vendor_id, kind, filename, path, sha256, pages, meta)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (document_id, tender_id, vendor_id, kind, path.name, str(path), sha, len(pages), dumps(meta or {})),
    )
    conn.executemany(
        "INSERT INTO document_pages (document_id, page, text) VALUES (?, ?, ?)",
        [(document_id, i, text) for i, text in enumerate(pages, start=1)],
    )
    return {"document_id": document_id, "filename": path.name, "sha256": sha, "pages": len(pages)}


def document_pages(conn: sqlite3.Connection, document_id: str) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT page, text FROM document_pages WHERE document_id = ? ORDER BY page", (document_id,)
    ).fetchall()
    return [(r["page"], r["text"]) for r in rows]
