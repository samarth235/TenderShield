"""Document versioning: immutable versions, historical verification and auditor review.

A changed SHA-256 is an objective fact, not a verdict. This module keeps the three
questions apart:

* Historical integrity - does a stored version still match the fingerprint recorded for it?
  A version's file and hash are never rewritten; an in-place edit of a committed file
  therefore shows up as ``INTEGRITY_MISMATCH``.
* Versioning - a legitimate change is uploaded as a *new* version (V2, V3...) with its own
  hash. Old versions stay available and verifiable forever.
* Review - a new version stays ``PENDING_REVIEW`` until an auditor accepts it, requests
  verification or flags it. Only an auditor action (recorded in the hash-chained audit trail)
  makes a version official; nothing is accepted automatically.

Each finalised version gets an ``anchor`` (the snapshot that sealed it and the audit head at
that moment) and a ``chain_payload`` the blockchain module commits as its own MST record.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..db import dumps, fetch_all, fetch_one
from ..ingestion.pdf_text import extract_pages, sha256_file
from ..ingestion.upload import SAFE_NAME
from . import audit

ACTIVE, SUPERSEDED = "ACTIVE", "SUPERSEDED"
PENDING_REVIEW, VERIFICATION_REQUESTED, FLAGGED = "PENDING_REVIEW", "VERIFICATION_REQUESTED", "FLAGGED"
OPEN_STATUSES = (PENDING_REVIEW, VERIFICATION_REQUESTED, FLAGGED)
REVIEW_DECISIONS = {"ACCEPT": ACTIVE, "REQUEST_VERIFICATION": VERIFICATION_REQUESTED,
                    "FLAG_FOR_INVESTIGATION": FLAGGED}

INTEGRITY_VERIFIED = "INTEGRITY_VERIFIED"
HISTORICALLY_VERIFIED = "HISTORICALLY_VERIFIED"
NEW_VERSION_DETECTED = "NEW_VERSION_DETECTED"
INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def version_id(document_id: str, version: int) -> str:
    return f"{document_id}@v{version}"


def label(version: int) -> str:
    return f"V{version}"


# --- Storage ------------------------------------------------------------------------

def ensure_initial_versions(conn: sqlite3.Connection, tender_id: str | None = None) -> int:
    """Register every document that has no version history as its V1 (the file as first registered)."""
    sql = ("SELECT d.* FROM documents d WHERE NOT EXISTS "
           "(SELECT 1 FROM document_versions v WHERE v.document_id = d.document_id)")
    params: list = []
    if tender_id:
        sql += " AND d.tender_id = ?"
        params.append(tender_id)
    docs = fetch_all(conn, sql, params)
    created_at = _now()
    for d in docs:
        vid = version_id(d["document_id"], 1)
        conn.execute(
            "INSERT INTO document_versions (version_id, document_id, tender_id, version, parent_version_id, created_at,"
            " created_by, filename, path, sha256, pages, status, meta) VALUES (?, ?, ?, 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, d["document_id"], d["tender_id"], created_at, "initial registration", d["filename"], d["path"],
             d["sha256"], d["pages"], ACTIVE,
             dumps({"origin": "initial_registration", "kind": d["kind"], "vendor_id": d["vendor_id"]})),
        )
        conn.execute("INSERT INTO document_version_pages (version_id, page, text) "
                     "SELECT ?, page, text FROM document_pages WHERE document_id = ?", (vid, d["document_id"]))
    return len(docs)


def _require_document(conn: sqlite3.Connection, document_id: str) -> dict:
    doc = fetch_one(conn, "SELECT * FROM documents WHERE document_id = ?", (document_id,))
    if doc is None:
        raise LookupError(f"Unknown document {document_id}")
    ensure_initial_versions(conn, doc["tender_id"])
    return doc


def _rows(conn: sqlite3.Connection, document_id: str) -> list[dict]:
    return fetch_all(conn, "SELECT * FROM document_versions WHERE document_id = ? ORDER BY version", (document_id,))


def get_version_row(conn: sqlite3.Connection, document_id: str, version: int) -> dict:
    _require_document(conn, document_id)
    row = fetch_one(conn, "SELECT * FROM document_versions WHERE document_id = ? AND version = ?", (document_id, version))
    if row is None:
        raise LookupError(f"{document_id} has no version {label(version)}")
    return row


def version_by_id(conn: sqlite3.Connection, vid: str) -> dict | None:
    return fetch_one(conn, "SELECT * FROM document_versions WHERE version_id = ?", (vid,))


def official_version(conn: sqlite3.Connection, document_id: str) -> dict | None:
    """The version currently accepted as the official evidence state."""
    return fetch_one(conn, "SELECT * FROM document_versions WHERE document_id = ? AND status = ? "
                           "ORDER BY version DESC LIMIT 1", (document_id, ACTIVE))


def latest_version(conn: sqlite3.Connection, document_id: str) -> dict | None:
    return fetch_one(conn, "SELECT * FROM document_versions WHERE document_id = ? ORDER BY version DESC LIMIT 1",
                     (document_id,))


def version_pages(conn: sqlite3.Connection, vid: str) -> list[tuple[int, str]]:
    rows = conn.execute("SELECT page, text FROM document_version_pages WHERE version_id = ? ORDER BY page",
                        (vid,)).fetchall()
    return [(r["page"], r["text"]) for r in rows]


def snapshots_pinning(conn: sqlite3.Connection, tender_id: str) -> dict[str, list[str]]:
    """version_id -> snapshot ids whose evidence bundle committed that exact version.

    Snapshots finalised before versioning existed carry no version ids; they committed V1.
    """
    out: dict[str, list[str]] = {}
    for snap in fetch_all(conn, "SELECT snapshot_id, bundle FROM snapshots WHERE tender_id = ? ORDER BY created_at",
                          (tender_id,)):
        for d in snap["bundle"].get("documents", []):
            vid = d.get("version_id") or version_id(d["document_id"], 1)
            out.setdefault(vid, []).append(snap["snapshot_id"])
    return out


def chain_payload(row: dict) -> dict | None:
    """Minimal on-chain record for one finalised version: identifiers + hashes only, never content."""
    anchor = row.get("anchor")
    if not anchor:
        return None
    return {
        "case_id": anchor["anchor_id"],
        "tender_id": row["tender_id"],
        "evidence_hash": row["sha256"],
        "audit_head_hash": anchor["audit_head_hash"],
        "timestamp": anchor["finalized_at"],
        "auditor_actions": [f"{label(row['version'])}_{anchor['action']}"],
        "document_id": row["document_id"],
        "version_id": row["version_id"],
        "version": row["version"],
    }


def serialize(row: dict, pinned_by: dict[str, list[str]] | None = None) -> dict:
    out = {k: v for k, v in row.items() if k != "path"}
    out["label"] = label(row["version"])
    out["chain_payload"] = chain_payload(row)
    if pinned_by is not None:
        out["committed_in_snapshots"] = pinned_by.get(row["version_id"], [])
    return out


def list_versions(conn: sqlite3.Connection, document_id: str) -> dict:
    doc = _require_document(conn, document_id)
    pinned = snapshots_pinning(conn, doc["tender_id"])
    rows = _rows(conn, document_id)
    official = next((r for r in reversed(rows) if r["status"] == ACTIVE), None)
    return {
        "document_id": document_id, "tender_id": doc["tender_id"], "vendor_id": doc["vendor_id"],
        "kind": doc["kind"], "filename": doc["filename"],
        "official_version": official["version"] if official else None,
        "latest_version": rows[-1]["version"] if rows else None,
        "pending_review": [r["version"] for r in rows if r["status"] in OPEN_STATUSES],
        "versions": [serialize(r, pinned) for r in rows],
    }


def version_file(conn: sqlite3.Connection, document_id: str, version: int) -> tuple[Path, str]:
    row = get_version_row(conn, document_id, version)
    return Path(row["path"]), row["filename"]


# --- Version creation -------------------------------------------------------------------

def create_version(conn: sqlite3.Connection, document_id: str, content: bytes, filename: str, created_by: str,
                   note: str = "", origin: str = "upload") -> dict:
    """Store a new, immutable version. Earlier versions (files, hashes, anchors) are never touched."""
    doc = _require_document(conn, document_id)
    if not created_by.strip():
        raise ValueError("created_by is required")
    if not content.startswith(b"%PDF"):
        raise ValueError("Uploaded file is not a PDF")
    rows = _rows(conn, document_id)
    digest = hashlib.sha256(content).hexdigest()
    duplicate = next((r for r in rows if r["sha256"] == digest), None)
    if duplicate:
        raise FileExistsError(f"Identical to {label(duplicate['version'])} (same SHA-256); no new version created.")
    number = rows[-1]["version"] + 1
    parent = official_version(conn, document_id) or rows[-1]
    vid = version_id(document_id, number)
    safe = SAFE_NAME.sub("_", Path(filename or doc["filename"]).name) or doc["filename"]
    folder = get_settings().documents_dir / doc["tender_id"] / "versions" / document_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"v{number}_{safe}"
    path.write_bytes(content)
    try:
        pages = extract_pages(path)
    except Exception as exc:  # unreadable PDF: do not leave a half-created version behind
        path.unlink(missing_ok=True)
        raise ValueError(f"Could not read the PDF: {exc}") from exc
    created_at = _now()
    conn.execute(
        "INSERT INTO document_versions (version_id, document_id, tender_id, version, parent_version_id, created_at,"
        " created_by, filename, path, sha256, pages, status, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (vid, document_id, doc["tender_id"], number, parent["version_id"], created_at, created_by.strip(), safe,
         str(path), digest, len(pages), PENDING_REVIEW,
         dumps({"origin": origin, "note": note, "size_bytes": len(content), "kind": doc["kind"],
                "vendor_id": doc["vendor_id"]})),
    )
    conn.executemany("INSERT INTO document_version_pages (version_id, page, text) VALUES (?, ?, ?)",
                     [(vid, i, text) for i, text in enumerate(pages, start=1)])
    audit.append(conn, doc["tender_id"], "DOCUMENT_VERSION_CREATED", created_by.strip(),
                 {"document_id": document_id, "version_id": vid, "version": number,
                  "parent_version_id": parent["version_id"], "sha256": digest, "parent_sha256": parent["sha256"],
                  "filename": safe, "note": note})
    return serialize(version_by_id(conn, vid), snapshots_pinning(conn, doc["tender_id"]))  # type: ignore[arg-type]


# --- Anchoring (called when a snapshot is finalised) --------------------------------------

def anchor_pinned_versions(conn: sqlite3.Connection, manifest: list[dict], snapshot_id: str, finalized_at: str,
                           audit_head_hash: str) -> int:
    """Give every version sealed by this snapshot its own anchor, once. Existing anchors are never replaced."""
    count = 0
    for d in manifest:
        vid = d.get("version_id")
        row = version_by_id(conn, vid) if vid else None
        if row is None or row.get("anchor"):
            continue
        anchor = {"anchor_id": f"{snapshot_id}:{vid}", "snapshot_id": snapshot_id, "finalized_at": finalized_at,
                  "audit_head_hash": audit_head_hash, "action": "FINALIZED" if row["version"] == 1 else "ACCEPTED"}
        conn.execute("UPDATE document_versions SET anchor = ? WHERE version_id = ? AND anchor IS NULL",
                     (dumps(anchor), vid))
        count += 1
    return count


# --- Verification -----------------------------------------------------------------------

def verify_version(conn: sqlite3.Connection, document_id: str, version: int) -> dict:
    """Recompute one version's SHA-256 and explain the result without judging the document."""
    row = get_version_row(conn, document_id, version)
    path = Path(row["path"])
    current = sha256_file(path) if path.exists() else None
    match = current == row["sha256"]
    pinned = snapshots_pinning(conn, row["tender_id"]).get(row["version_id"], [])
    latest = latest_version(conn, document_id)
    official = official_version(conn, document_id)
    parent = version_by_id(conn, row["parent_version_id"]) if row["parent_version_id"] else None
    name = label(version)
    committed_at = f"snapshot {pinned[0]}" if pinned else None

    if not match:
        status, headline = INTEGRITY_MISMATCH, "Integrity mismatch"
        explanation = ("The historically committed evidence no longer matches its original fingerprint."
                       if committed_at else
                       f"The stored file no longer matches the fingerprint recorded when {name} was created.")
        explanation += (" The file was changed in place instead of being uploaded as a new version, so this "
                        "cannot be treated as a routine update.")
    elif row["status"] in OPEN_STATUSES:
        status, headline = NEW_VERSION_DETECTED, "New version detected"
        base = label(parent["version"]) if parent else "the earlier version"
        explanation = (f"The current document ({name}) differs from the historically committed version ({base}). "
                       f"{base} remains unchanged and verifiable. {name} is "
                       f"{row['status'].replace('_', ' ').lower()} - an auditor decides whether it becomes official.")
    elif latest and latest["version"] > version:
        status, headline = HISTORICALLY_VERIFIED, "Historical version verified"
        explanation = (f"{name} still matches the fingerprint " + (f"committed at {committed_at}" if committed_at
                                                                   else "recorded when it was created")
                       + f". A newer version ({label(latest['version'])}, "
                       f"{latest['status'].replace('_', ' ').lower()}) exists; the history is preserved.")
    else:
        status, headline = INTEGRITY_VERIFIED, "Integrity verified"
        explanation = (f"Document matches the version committed at {committed_at}." if committed_at else
                       f"Document matches the fingerprint recorded for {name}. It has not been sealed in an "
                       "evidence snapshot yet.")
    return {
        "document_id": document_id, "tender_id": row["tender_id"], "version_id": row["version_id"],
        "version": version, "label": name, "version_status": row["status"],
        "status": status, "match": match, "headline": headline, "explanation": explanation,
        "recorded_sha256": row["sha256"], "current_sha256": current,
        "committed_in_snapshots": pinned,
        "official_version": official["version"] if official else None,
        "latest_version": latest["version"] if latest else None,
        "chain_payload": chain_payload(row),
        "verified_at": _now(),
        "note": "A different hash between versions is an objective fact, not a finding. Only an in-place change "
                "to a stored version is an integrity mismatch.",
    }


# --- Auditor review ------------------------------------------------------------------------

def review_version(conn: sqlite3.Connection, document_id: str, version: int, decision: str, auditor: str,
                   notes: str = "") -> dict:
    """Record the auditor's decision in the audit chain. ACCEPT makes the version official and
    supersedes the previous official version; the earlier version's file, hash and anchor stay intact."""
    decision = decision.upper()
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"decision must be one of {', '.join(REVIEW_DECISIONS)}")
    if not auditor.strip():
        raise ValueError("auditor is required")
    row = get_version_row(conn, document_id, version)
    if row["status"] not in OPEN_STATUSES:
        raise PermissionError(f"{label(version)} is {row['status']}; only versions awaiting review can be decided.")
    previous = official_version(conn, document_id)
    entry = audit.append(conn, row["tender_id"], "VERSION_REVIEW", auditor.strip(),
                         {"document_id": document_id, "version_id": row["version_id"], "version": version,
                          "decision": decision, "notes": notes, "sha256": row["sha256"],
                          "previous_official_version_id": previous["version_id"] if previous else None})
    if decision == "ACCEPT" and previous:
        conn.execute("UPDATE document_versions SET status = ? WHERE version_id = ?", (SUPERSEDED, previous["version_id"]))
    conn.execute("UPDATE document_versions SET status = ? WHERE version_id = ?",
                 (REVIEW_DECISIONS[decision], row["version_id"]))
    return {"version": serialize(version_by_id(conn, row["version_id"]),  # type: ignore[arg-type]
                                 snapshots_pinning(conn, row["tender_id"])),
            "audit_entry": entry}
