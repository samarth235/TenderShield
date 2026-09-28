# TenderShield Nexus — Backend API contract

This is the contract between the **backend + AI/ML** service and the other two parts of the project:

- **Frontend** (React + TypeScript dashboard) — consumes every endpoint below.
- **Blockchain + dossier** (Solidity/Hardhat + PDF) — consumes the *Evidence & integrity* and *Dossier* endpoints.

Base URL in development: `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.
Machine-readable schema: [`docs/openapi.json`](openapi.json). Regenerate it with `make openapi`. To generate TypeScript types from it:

```bash
npx openapi-typescript ../docs/openapi.json -o src/api/schema.d.ts
```

All responses are JSON unless noted. Errors use FastAPI's shape `{"detail": "..."}` with these codes:
`404` unknown id · `409` stage not run yet (call `analyze` first) · `400` bad input · `422` validation / not applicable.

---

## 1. Demo-mode flow (what the UI buttons call)

| UI step (spec §28) | Call |
|---|---|
| LOAD DEMONSTRATION TENDER | `POST /api/demo/load?analyze=true` |
| Open rulebook (clause → rule → page) | `GET /api/tenders/{tid}/rules` |
| Compliance matrix (108 checks) | `GET /api/tenders/{tid}/compliance` |
| Vendor graph | `GET /api/tenders/{tid}/graph` |
| Click Vendor A | `GET /api/tenders/{tid}/graph/vendors/V001?depth=2` |
| A ↔ B relationship | `GET /api/tenders/{tid}/graph/paths?a=V001&b=V002` |
| Findings list | `GET /api/tenders/{tid}/findings` |
| Open finding (evidence card) | `GET /api/findings/{fid}` |
| WHY WAS THIS FLAGGED? | `GET /api/findings/{fid}/reasoning` |
| TEST ROBUSTNESS (overview) | `GET /api/findings/{fid}/robustness` |
| Remove evidence | `POST /api/findings/{fid}/counterfactual` `{"remove": ["E1"]}` |
| Auditor disposition | `POST /api/findings/{fid}/disposition` `{"decision": "FURTHER_REVIEW", "auditor": "...", "notes": "..."}` |
| Generate dossier (data) | `GET /api/tenders/{tid}/dossier-data` |
| Commit evidence | `POST /api/tenders/{tid}/evidence/finalize` `{"auditor": "..."}` → `bundle_hash` goes on-chain |
| Modify a document | `POST /api/demo/tamper` `{}` (default: Vendor A's compliance PDF) |
| VERIFY | `GET /api/evidence/snapshots/{sid}/verify` |
| Reset the tamper | `POST /api/demo/restore` |

The demo tender id is `TN-2026-014`. Finding ids are `{tender_id}-Fnn`; the demo's headline finding (Vendor A ↔ Vendor B) is always `TN-2026-014-F01`.

---

## 2. Endpoints

### System
| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | extractor mode, whether Claude credentials are available, embedding backend |
| GET | `/api/meta/metrics` | controlled metric vocabulary used by rules and uploaded bidder facts |
| GET | `/api/meta/scoring` | evidence weights and the level rule (show this in a "How scoring works" panel) |

### Demo
| Method | Path | Notes |
|---|---|---|
| POST | `/api/demo/load?analyze=true` | resets the DB, generates 50 vendors / 120 historical tenders / 14 PDFs; with `analyze=true` also runs the pipeline |
| POST | `/api/demo/tamper` | body `{"document_id": "DOC-V001-COMP"}` (optional). Edits the stored file on disk |
| POST | `/api/demo/restore` | restores tampered files |

### Tenders & documents
| Method | Path | Notes |
|---|---|---|
| GET | `/api/tenders` | current tenders (`?include_history=true` for all 121) |
| GET | `/api/tenders/{tid}` | tender, bidders (amount, submission time), documents, `completed_stages` |
| GET | `/api/tenders/{tid}/documents` | document list with SHA-256 |
| GET | `/api/documents/{doc_id}` | metadata + extracted text per page (for the evidence viewer) |
| GET | `/api/documents/{doc_id}/file` | the PDF itself (`application/pdf`) |

Document ids in the demo: `DOC-TENDER`, `DOC-SUBMISSION-LOG`, `DOC-V00n-TECH` (technical proposal), `DOC-V00n-COMP` (compliance documents).

### Analysis pipeline
| Method | Path | Notes |
|---|---|---|
| POST | `/api/tenders/{tid}/analyze` | body `{"method": "pattern" \| "llm" \| "auto"}` optional. Runs all stages; returns per-stage timings + summaries |
| POST | `/api/tenders/{tid}/rules/extract` | re-run only the rule extraction |
| GET | `/api/tenders/{tid}/rules` | the Tender Rulebook |
| GET | `/api/tenders/{tid}/clauses` | segmented clauses with page numbers |
| POST | `/api/tenders/{tid}/compliance/run` | re-extract bidder facts + re-run compliance |
| GET | `/api/tenders/{tid}/compliance` | compliance matrix |
| GET | `/api/tenders/{tid}/compliance/{vendor_id}` | one bidder's evaluations with rule details |

### Intelligence
| Method | Path | Notes |
|---|---|---|
| GET | `/api/tenders/{tid}/entities` | entity-resolution result: name variants, shared directors/addresses/contacts, data-quality gaps |
| GET | `/api/tenders/{tid}/graph` | tender graph view (bidders, their corporate entities, co-bid tenders, documents, derived `CO_BID` edges) |
| GET | `/api/tenders/{tid}/graph/vendors/{vendor_id}?depth=1..3` | ego network |
| GET | `/api/tenders/{tid}/graph/paths?a=&b=&include_tenders=false` | shared intermediate nodes that link two vendors |
| GET | `/api/tenders/{tid}/similarity` | document-similarity pairs (summary) |
| GET | `/api/tenders/{tid}/similarity/{a}/{b}` | section scores + matching passages with pages |
| GET | `/api/tenders/{tid}/behaviour?include_history=false` | pair features, deterministic flags, Isolation Forest scores |

### Findings, reasoning, counterfactuals, audit
| Method | Path | Notes |
|---|---|---|
| GET | `/api/tenders/{tid}/findings?category=` | list; `category` = `INVESTIGATION_SIGNAL` \| `COMPLIANCE` \| `DATA_QUALITY` |
| GET | `/api/findings/{fid}` | full evidence card + its audit entries |
| GET | `/api/findings/{fid}/reasoning` | steps + conclusion + reasoning graph (`nodes`/`edges`) |
| GET | `/api/findings/{fid}/robustness` | leave-one-out, family ablation, minimal breaking set (signals only; 422 otherwise) |
| POST | `/api/findings/{fid}/counterfactual` | body `{"remove": ["E1","E3"], "actor": "auditor", "record": true}` |
| GET | `/api/findings/{fid}/counterfactual` | recorded runs |
| POST | `/api/findings/{fid}/disposition` | body `{"decision": "VERIFIED" \| "DISMISSED" \| "FURTHER_REVIEW", "auditor": "...", "notes": ""}` |
| GET | `/api/tenders/{tid}/audit-log` | hash-chained audit trail + chain validity |

### Evidence & integrity (blockchain hand-off)
| Method | Path | Notes |
|---|---|---|
| POST | `/api/tenders/{tid}/evidence/finalize` | freezes evidence → `snapshot_id`, `bundle_hash`, `chain_payload` |
| GET | `/api/tenders/{tid}/evidence/snapshots` | snapshots for a tender |
| GET | `/api/evidence/snapshots/{sid}?include_bundle=true` | snapshot summary; optionally the full bundle and its exact canonical JSON |
| GET | `/api/evidence/snapshots/{sid}/verify` | recomputes the hash from current evidence |
| GET | `/api/tenders/{tid}/dossier-data` | everything the Assurance Dossier PDF needs |

### Exploration mode (uploads)
| Method | Path | Notes |
|---|---|---|
| POST | `/api/uploads/tender` | multipart: `file` (PDF), optional `tender_id`, `title`, `department`, `bid_deadline`, `method`. Returns the extracted rulebook |
| POST | `/api/uploads/{tid}/bidders` | JSON `{"bidders": [...]}` (see `backend/samples/bidders_sample.json`) |
| POST | `/api/uploads/{tid}/bidders.csv` | multipart CSV (see `backend/samples/bidders_sample.csv`) |
| POST | `/api/uploads/{tid}/bidders.json` | multipart JSON file |

Then `POST /api/tenders/{tid}/analyze`.

---

## 3. Key response shapes

### Rule (`GET /rules` → `rules[]`)
```json
{
  "rule_id": "R06", "category": "Experience",
  "requirement": "Aggregate value of similar projects >= Rs. 10 crore",
  "metric": "similar_projects_value_cr", "operator": "gte", "threshold": 10.0, "unit": "crore",
  "mandatory": true, "applies_if": null,
  "condition": "similar_projects_value_cr >= 10.0",
  "clause_text": "The Bidder shall have completed at least three similar projects ...",
  "source": {"document_id": "DOC-TENDER", "filename": "Tender_TN-2026-014.pdf", "page": 4, "clause": "4.2"},
  "extraction": {"method": "pattern", "confidence": 0.9, "model": null},
  "notes": []
}
```
`operator` ∈ `gte, gt, lte, eq, is_true, is_false, valid_on_submission, submitted_before`.

### Compliance matrix (`GET /compliance`)
```json
{
  "rules": [{"rule_id": "R01", "category": "Financial", "requirement": "...", "condition": "...", "mandatory": true, "source": {...}}],
  "vendors": [{"vendor_id": "V005", "alias": "Vendor E", "name": "...", "status": "NOT_QUALIFIED",
               "counts": {"PASS": 15, "FAIL": 2, "UNKNOWN": 0, "NOT_APPLICABLE": 1}}],
  "cells": {"V005": {"R08": {"result": "FAIL", "expected": "...", "actual": "2026-01-31", "mandatory": true,
                               "reason": "Certificate valid until 2026-01-31; bid submission date 2026-03-12 - certificate had expired before that date.",
                               "evidence": [{"role": "primary", "document_id": "DOC-V005-COMP", "filename": "ComplianceDocs_E.pdf", "page": 3, "excerpt": "..."}]}}},
  "evaluations": 108
}
```
`result` ∈ `PASS, FAIL, UNKNOWN, NOT_APPLICABLE`. Vendor `status` ∈ `QUALIFIED, NOT_QUALIFIED, INCOMPLETE_EVIDENCE`.

### Graph (`GET /graph`, `/graph/vendors/{id}`)
```json
{
  "nodes": [{"id": "vendor:V001", "type": "vendor", "label": "Vendor A", "name": "...", "is_bidder": true}],
  "edges": [{"id": "director:DIR-001|DIRECTED_BY|vendor:V001", "source": "...", "target": "...", "type": "DIRECTED_BY"},
            {"id": "vendor:V001|CO_BID|vendor:V002", "type": "CO_BID", "derived": true, "weight": 5}],
  "stats": {"nodes": {"vendor": 6, "...": 0}, "edges": {"...": 0}}
}
```
Node `type` ∈ `vendor, director, address, contact, tender, document`. Edge `type` ∈ `DIRECTED_BY, REGISTERED_AT, USES_CONTACT, PARTICIPATED_IN, WON, SUBMITTED, SIMILAR_TO, CO_BID`. The shape maps directly onto Cytoscape / React Flow elements.

### Finding / evidence card (`GET /findings/{fid}`)
```json
{
  "finding_id": "TN-2026-014-F01", "category": "INVESTIGATION_SIGNAL",
  "title": "Vendor A <-> Vendor B: potential coordinated-bidding indicator",
  "signal": "Potential coordinated-bidding indicator", "recommendation": "REVIEW",
  "level": "HIGH", "status": "OPEN",
  "subject": {"type": "vendor_pair", "vendors": [{"vendor_id": "V001", "alias": "Vendor A", "name": "..."}, {...}]},
  "evidence": [{
    "evidence_id": "E1", "type": "SHARED_DIRECTOR", "label": "Shared director", "family": "corporate",
    "weight": 0.2, "strength": "strong", "statement": "Both vendors list the same director (...)",
    "metrics": {"din": "07345128", "match_method": "identifier (DIN)"},
    "sources": [{"kind": "vendor_registry", "vendor_id": "V001", "field": "directors", "value": "Rajesh Kumar Sharma"}],
    "alternative_explanation": "...", "recommended_verification": ["..."]
  }],
  "assessment": {"support": 1.35, "families": ["behavioural", "corporate", "document"], "level": "HIGH", "evidence_count": 8, "rule": {...}},
  "reasoning": {"steps": [{"step": 1, "key": "corporate", "label": "Corporate overlap", "evidence_ids": ["E1", "E2"], "statement": "..."}],
                "conclusion": "...", "graph": {"nodes": [...], "edges": [...]}},
  "data_quality": {"level": "HIGH", "notes": ["..."]},
  "alternative_explanations": ["..."], "recommended_verification": ["..."], "disclaimer": "...",
  "audit": [...]
}
```
- `level`: signals `HIGH | MEDIUM | LOW`; compliance `FAIL`; data quality `INSUFFICIENT_DATA`.
- `status`: `OPEN | VERIFIED | DISMISSED | FURTHER_REVIEW`.
- `recommendation`: `REVIEW | NO_ACTION | VERIFY | REQUEST_INFORMATION`.
- Evidence `family`: `corporate | behavioural | document | model` (signals), `compliance`, `data_quality`.
- Source `kind`: `vendor_registry | award_record | document | passage | model | tender_clause`. `document`/`passage` sources carry `document_id` + `page` → link to `/api/documents/{id}/file#page=N`.

### Counterfactual (`POST /findings/{fid}/counterfactual`)
```json
{
  "finding_id": "...", "removed": [{"evidence_id": "E1", "label": "Shared director", "family": "corporate"}],
  "remaining": [...], "original": {"level": "HIGH", "support": 1.35, "families": [...]},
  "counterfactual": {"level": "HIGH", "support": 1.15, "families": [...]},
  "status": "STILL_SUPPORTED", "explanation": "Finding still supported at HIGH: ...", "run_id": 1
}
```
`status` ∈ `STILL_SUPPORTED, DOWNGRADED, DISSOLVED`.

### Snapshot (`POST /evidence/finalize`)
```json
{
  "snapshot_id": "SNAP-6BC41234DAAC", "tender_id": "TN-2026-014", "created_at": "2026-09-28T14:15:08+00:00",
  "bundle_hash": "0adee5ef8360...", "hash_algorithm": "SHA-256",
  "component_hashes": {"rulebook": "...", "compliance": "...", "findings": "...", "documents": "...", "audit_trail": "..."},
  "documents": 14, "findings": 5,
  "dispositions": [{"finding_id": "TN-2026-014-F01", "decision": "FURTHER_REVIEW", "auditor": "..."}],
  "chain_payload": {"case_id": "SNAP-...", "tender_id": "TN-2026-014", "evidence_hash": "0adee5...",
                    "audit_head_hash": "...", "timestamp": "...", "auditor_actions": ["FURTHER_REVIEW"]}
}
```

### Verify (`GET /evidence/snapshots/{sid}/verify`)
```json
{
  "snapshot_id": "...", "committed_hash": "0adee5...", "current_hash": "f81aa9...",
  "match": false, "status": "INTEGRITY_MISMATCH",
  "changed_components": ["documents"],
  "changed_documents": [{"document_id": "DOC-V001-COMP", "filename": "ComplianceDocs_A.pdf", "committed_sha256": "...", "current_sha256": "..."}],
  "audit_chain": {"valid": true, "head_hash": "..."},
  "note": "Integrity verification proves the evidence is unchanged since commitment; it does not prove ..."
}
```

---

## 4. Blockchain hand-off

1. After the auditor's disposition, call `POST /api/tenders/{tid}/evidence/finalize`.
2. Commit `chain_payload` on-chain: `case_id`, `evidence_hash` (= `bundle_hash`), `audit_head_hash`, `timestamp`, auditor action(s). Add the dossier PDF's own SHA-256 as the report hash. Nothing else goes on-chain.
3. To verify, call `GET /api/evidence/snapshots/{sid}/verify` and compare **`current_hash`** with the hash read from the contract. Equal → `INTEGRITY VERIFIED`; different → `INTEGRITY MISMATCH` (use `changed_documents` to show what changed).
4. The bundle hash is `SHA-256(canonical JSON)`. Canonical JSON = `json.dumps(bundle, sort_keys=True, ensure_ascii=False)` with no extra whitespace options (Python defaults: `", "` and `": "` separators). `GET /api/evidence/snapshots/{sid}?include_bundle=true` returns the exact `canonical_json` string, so it can be re-hashed independently.
5. Actions taken after finalisation (new dispositions, counterfactual runs) do not change an existing snapshot. Re-running `analyze` or modifying a document does.
