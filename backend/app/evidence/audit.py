"""Human-in-the-loop investigation (Stage 12) and the hash-chained audit trail.

Every auditor action (disposition, counterfactual test, evidence finalisation) is appended
to an audit log in which each entry commits to the previous entry's hash, so any later
edit of the history is detectable even before the blockchain commitment.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

from ..db import dumps, fetch_all

DISPOSITIONS = ("VERIFIED", "DISMISSED", "FURTHER_REVIEW")
GENESIS = "0" * 64


def entry_hash(prev_hash: str, tender_id: str, finding_id: str | None, action: str, actor: str, payload: dict,
               created_at: str) -> str:
    material = dumps({"prev": prev_hash, "tender_id": tender_id, "finding_id": finding_id, "action": action,
                      "actor": actor, "payload": payload, "created_at": created_at})
    return hashlib.sha256(material.encode()).hexdigest()


def append(conn: sqlite3.Connection, tender_id: str, action: str, actor: str, payload: dict,
           finding_id: str | None = None) -> dict:
    last = conn.execute("SELECT entry_hash FROM audit_log WHERE tender_id = ? ORDER BY entry_id DESC LIMIT 1",
                        (tender_id,)).fetchone()
    prev = last["entry_hash"] if last else GENESIS
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = entry_hash(prev, tender_id, finding_id, action, actor, payload, created_at)
    cur = conn.execute(
        "INSERT INTO audit_log (tender_id, finding_id, action, actor, payload, created_at, prev_hash, entry_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tender_id, finding_id, action, actor, dumps(payload), created_at, prev, digest),
    )
    return {"entry_id": cur.lastrowid, "tender_id": tender_id, "finding_id": finding_id, "action": action,
            "actor": actor, "payload": payload, "created_at": created_at, "prev_hash": prev, "entry_hash": digest}


def record_disposition(conn: sqlite3.Connection, finding: dict, decision: str, auditor: str, notes: str = "") -> dict:
    decision = decision.upper()
    if decision not in DISPOSITIONS:
        raise ValueError(f"decision must be one of {', '.join(DISPOSITIONS)}")
    if not auditor.strip():
        raise ValueError("auditor is required")
    entry = append(conn, finding["tender_id"], "DISPOSITION", auditor.strip(),
                   {"decision": decision, "notes": notes, "finding_level": finding["level"],
                    "finding_category": finding["category"]},
                   finding_id=finding["finding_id"])
    conn.execute("UPDATE findings SET status = ? WHERE finding_id = ?", (decision, finding["finding_id"]))
    return entry


def history(conn: sqlite3.Connection, tender_id: str, finding_id: str | None = None,
            up_to_entry: int | None = None) -> list[dict]:
    sql = "SELECT * FROM audit_log WHERE tender_id = ?"
    params: list = [tender_id]
    if finding_id:
        sql += " AND finding_id = ?"
        params.append(finding_id)
    if up_to_entry is not None:
        sql += " AND entry_id <= ?"
        params.append(up_to_entry)
    return fetch_all(conn, sql + " ORDER BY entry_id", params)


def verify_chain(conn: sqlite3.Connection, tender_id: str) -> dict:
    prev = GENESIS
    for e in history(conn, tender_id):
        expected = entry_hash(prev, e["tender_id"], e["finding_id"], e["action"], e["actor"], e["payload"], e["created_at"])
        if e["prev_hash"] != prev or e["entry_hash"] != expected:
            return {"valid": False, "broken_at_entry": e["entry_id"]}
        prev = e["entry_hash"]
    return {"valid": True, "head_hash": prev}
