"""Evidence Store: canonical evidence bundles, SHA-256 fingerprints and integrity verification.

Hand-off contract with the blockchain module (Stages 14-15):
  1. ``finalize_snapshot`` freezes the evidence state and returns ``bundle_hash``.
     The blockchain service commits {case/snapshot id, bundle_hash, report hash, auditor action}.
  2. ``verify_snapshot`` recomputes the hash from the *current* stored evidence.
     The blockchain service compares ``current_hash`` with the on-chain hash.
Only hashes go on-chain; documents and analysis stay off-chain.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..db import dumps, fetch_all, fetch_one
from ..ingestion.pdf_text import sha256_file
from ..nlp.extract import load_rules
from . import audit, versions

SCHEMA = "tendershield.evidence-bundle/v1"


def sha256_json(value) -> str:
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def document_manifest(conn: sqlite3.Connection, tender_id: str, pinned: dict[str, str] | None = None,
                      legacy: bool = False) -> list[dict]:
    """Fingerprint every document of the tender.

    By default each entry is the document's *official* version. ``pinned`` (document_id -> version_id)
    re-fingerprints the exact versions a snapshot committed, so a later V2 never changes what V1's
    snapshot proves. ``legacy`` reproduces the pre-versioning manifest format of older snapshots.
    """
    versions.ensure_initial_versions(conn, tender_id)
    manifest = []
    for d in fetch_all(conn, "SELECT * FROM documents WHERE tender_id = ? ORDER BY document_id", (tender_id,)):
        if legacy:
            path = Path(d["path"])
            manifest.append({
                "document_id": d["document_id"], "filename": d["filename"], "kind": d["kind"], "vendor_id": d["vendor_id"],
                "sha256": sha256_file(path) if path.exists() else None,
                "registered_sha256": d["sha256"],
            })
            continue
        row = versions.version_by_id(conn, pinned[d["document_id"]]) if pinned and d["document_id"] in pinned else None
        row = row or versions.official_version(conn, d["document_id"]) or versions.latest_version(conn, d["document_id"])
        path = Path(row["path"])  # type: ignore[index]
        manifest.append({
            "document_id": d["document_id"], "filename": d["filename"], "kind": d["kind"], "vendor_id": d["vendor_id"],
            "version": row["version"], "version_id": row["version_id"],  # type: ignore[index]
            "sha256": sha256_file(path) if path.exists() else None,
            "registered_sha256": row["sha256"],  # type: ignore[index]
        })
    return manifest


def build_bundle(conn: sqlite3.Connection, tender_id: str, snapshot_id: str, created_at: str, audit_head: int,
                 pinned: dict[str, str] | None = None, legacy: bool = False) -> dict:
    tender = fetch_one(conn, "SELECT tender_id, title, department, estimated_value_cr, bid_deadline FROM tenders "
                             "WHERE tender_id = ?", (tender_id,))
    findings = []
    for row in fetch_all(conn, "SELECT body FROM findings WHERE tender_id = ? ORDER BY finding_id", (tender_id,)):
        body = dict(row["body"])
        body.pop("status", None)  # dispositions are captured by the audit entries below
        findings.append(body)
    compliance = [
        {"vendor_id": r["vendor_id"], "rule_id": r["rule_id"], "result": r["result"], "actual": r["body"]["actual"]}
        for r in fetch_all(conn, "SELECT vendor_id, rule_id, result, body FROM compliance WHERE tender_id = ? "
                                 "ORDER BY vendor_id, rule_id", (tender_id,))
    ]
    manifest = [{k: v for k, v in d.items() if k != "registered_sha256"}
                for d in document_manifest(conn, tender_id, pinned, legacy)]
    entries = audit.history(conn, tender_id, up_to_entry=audit_head)
    components = {
        "rulebook": load_rules(conn, tender_id),
        "compliance": compliance,
        "findings": findings,
        "documents": manifest,
        "audit_trail": entries,
    }
    return {
        "schema": SCHEMA,
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "tender": tender,
        "component_hashes": {name: sha256_json(value) for name, value in components.items()},
        "audit_head_hash": entries[-1]["entry_hash"] if entries else audit.GENESIS,
        **components,
    }


def finalize_snapshot(conn: sqlite3.Connection, tender_id: str, auditor: str, note: str = "") -> dict:
    if not conn.execute("SELECT 1 FROM findings WHERE tender_id = ? LIMIT 1", (tender_id,)).fetchone():
        raise LookupError("No findings to finalise - run the analysis first.")
    head_row = conn.execute("SELECT MAX(entry_id) AS head FROM audit_log WHERE tender_id = ?", (tender_id,)).fetchone()
    audit_head = head_row["head"] or 0
    snapshot_id = f"SNAP-{uuid.uuid4().hex[:12].upper()}"
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bundle = build_bundle(conn, tender_id, snapshot_id, created_at, audit_head)
    bundle_hash = sha256_json(bundle)
    conn.execute(
        "INSERT INTO snapshots (snapshot_id, tender_id, created_at, bundle, bundle_hash, audit_head) VALUES (?, ?, ?, ?, ?, ?)",
        (snapshot_id, tender_id, created_at, dumps(bundle), bundle_hash, audit_head),
    )
    audit.append(conn, tender_id, "EVIDENCE_FINALIZED", auditor,
                 {"snapshot_id": snapshot_id, "bundle_hash": bundle_hash, "note": note})
    # Every document version sealed here gets its own anchor (and MST chain payload), once.
    versions.anchor_pinned_versions(conn, bundle["documents"], snapshot_id, created_at, bundle["audit_head_hash"])
    return snapshot_summary(snapshot_id, tender_id, created_at, bundle_hash, bundle)


def snapshot_summary(snapshot_id: str, tender_id: str, created_at: str, bundle_hash: str, bundle: dict) -> dict:
    dispositions = [e for e in bundle["audit_trail"] if e["action"] == "DISPOSITION"]
    return {
        "snapshot_id": snapshot_id,
        "tender_id": tender_id,
        "created_at": created_at,
        "bundle_hash": bundle_hash,
        "hash_algorithm": "SHA-256",
        "component_hashes": bundle["component_hashes"],
        "documents": len(bundle["documents"]),
        "findings": len(bundle["findings"]),
        "dispositions": [{"finding_id": e["finding_id"], "decision": e["payload"]["decision"], "auditor": e["actor"]}
                         for e in dispositions],
        # Minimal record the blockchain service commits on-chain.
        "chain_payload": {
            "case_id": snapshot_id,
            "tender_id": tender_id,
            "evidence_hash": bundle_hash,
            "audit_head_hash": bundle["audit_head_hash"],
            "timestamp": created_at,
            "auditor_actions": [e["payload"]["decision"] for e in dispositions],
        },
    }


def get_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> dict | None:
    return fetch_one(conn, "SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,))


def verify_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> dict:
    snap = get_snapshot(conn, snapshot_id)
    if snap is None:
        raise LookupError(f"Unknown snapshot {snapshot_id}")
    committed = snap["bundle"]
    committed_docs = {d["document_id"]: d for d in committed["documents"]}
    # Re-fingerprint the exact versions this snapshot committed, not whatever is newest today.
    legacy = any("version_id" not in d for d in committed["documents"])
    pinned = {d["document_id"]: d["version_id"] for d in committed["documents"] if d.get("version_id")}
    current = build_bundle(conn, snap["tender_id"], snapshot_id, snap["created_at"], snap["audit_head"], pinned, legacy)
    current_hash = sha256_json(current)
    changed_components = [
        name for name, digest in committed["component_hashes"].items() if current["component_hashes"].get(name) != digest
    ]
    changed_documents = [
        {"document_id": d["document_id"], "filename": d["filename"], "version_id": d.get("version_id"),
         "committed_sha256": committed_docs.get(d["document_id"], {}).get("sha256"), "current_sha256": d["sha256"]}
        for d in current["documents"]
        if committed_docs.get(d["document_id"], {}).get("sha256") != d["sha256"]
    ]
    newer_versions = []
    for doc_id, d in committed_docs.items():
        committed_version = d.get("version", 1)
        latest = versions.latest_version(conn, doc_id)
        if latest and latest["version"] > committed_version:
            newer_versions.append({
                "document_id": doc_id, "filename": d["filename"],
                "committed_version": committed_version, "committed_version_id": versions.version_id(doc_id, committed_version),
                "latest_version": latest["version"], "latest_version_id": latest["version_id"],
                "latest_status": latest["status"],
            })
    match = current_hash == snap["bundle_hash"]
    if not match:
        status, headline = "INTEGRITY_MISMATCH", "Integrity mismatch"
        explanation = ("The historically committed evidence no longer matches its original fingerprint."
                       if changed_documents else
                       "Committed evidence components changed since the snapshot: " + ", ".join(changed_components) + ".")
    elif newer_versions:
        status, headline = "NEW_VERSION_DETECTED", "Historically verified · new version detected"
        names = ", ".join(f"{v['filename']} V{v['latest_version']}" for v in newer_versions)
        explanation = (f"Snapshot {snapshot_id} still matches its committed hash. A newer document version exists "
                       f"({names}); the current document differs from the historically committed version. "
                       "That alone is not a finding - review the change on the version history.")
    else:
        status, headline = "INTEGRITY_VERIFIED", "Integrity verified"
        explanation = f"Evidence matches the state committed at snapshot {snapshot_id}."
    return {
        "snapshot_id": snapshot_id,
        "tender_id": snap["tender_id"],
        "committed_hash": snap["bundle_hash"],
        "current_hash": current_hash,
        "match": match,
        "status": status,
        "headline": headline,
        "explanation": explanation,
        "changed_components": changed_components,
        "changed_documents": changed_documents,
        "newer_versions": newer_versions,
        "audit_chain": audit.verify_chain(conn, snap["tender_id"]),
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Integrity verification proves the evidence is unchanged since commitment; it does not prove the "
                "original documents were truthful or that a detected pattern was illegal.",
    }


def load_bundle(conn: sqlite3.Connection, snapshot_id: str) -> dict:
    snap = get_snapshot(conn, snapshot_id)
    if snap is None:
        raise LookupError(f"Unknown snapshot {snapshot_id}")
    return {"bundle_hash": snap["bundle_hash"], "canonical_json": dumps(snap["bundle"]), "bundle": snap["bundle"]}


def list_snapshots(conn: sqlite3.Connection, tender_id: str) -> list[dict]:
    rows = fetch_all(conn, "SELECT snapshot_id, tender_id, created_at, bundle_hash, audit_head FROM snapshots "
                           "WHERE tender_id = ? ORDER BY created_at", (tender_id,))
    return rows

