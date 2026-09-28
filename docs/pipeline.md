# Backend + AI/ML analysis workflow

`POST /api/tenders/{tid}/analyze` (or `make seed`) runs the stages below in order inside one database transaction. Each stage writes its result to the `artifacts` table, and the next stage reads it from there.

```text
Tender PDF ──► segmentation ──► rule extraction (pattern | Claude) ──► Tender Rulebook
Bidder PDFs ─► fact extraction (value + document + page + excerpt)
                                   │
                                   ▼
                     Deterministic compliance engine (PASS / FAIL / UNKNOWN / N/A)
Vendor registry + award records ─► Entity resolution ─► Relationship graph (NetworkX)
Technical proposals ─► section chunking ─► embeddings ─► document / section / passage similarity
Resolved award history ─► pair features ─► deterministic flags + Isolation Forest
                                   │
                                   ▼
             Evidence reasoning engine ─► findings (signal / compliance / data quality)
                                   │
                  counterfactual robustness · human disposition · audit chain
                                   │
                                   ▼
                  evidence bundle (SHA-256) ─► blockchain module / dossier PDF
```

| # | Spec stage | Module | Output |
|---|---|---|---|
| 1 | Tender ingestion | `app/ingestion/pdf_text.py`, `app/demo/generator.py` | documents + page text + SHA-256 |
| 2 | AI tender understanding | `app/nlp/segmentation.py`, `pattern_extractor.py`, `llm_extractor.py` | candidate rules per clause |
| 3 | Tender Rulebook | `app/nlp/extract.py`, `rulebook.py` | normalised rules with clause + page |
| — | Bidder evidence | `app/ingestion/facts.py` | declared values with document + page + excerpt |
| 4 | Compliance engine | `app/compliance/engine.py` | 6 × 18 = 108 evaluations |
| 5 | Entity resolution | `app/entities/resolution.py` | vendor links, director/address/contact entities |
| 6 | Relationship graph | `app/graph/builder.py` | NetworkX multigraph and views |
| 7 | Bid document intelligence | `app/intelligence/similarity.py` | document/section/passage similarity |
| 8 | Bid behaviour intelligence | `app/intelligence/behaviour.py` | pair features, flags, Isolation Forest |
| 9–10 | Evidence reasoning + cards | `app/reasoning/engine.py`, `scoring.py` | findings with reasoning chains |
| 11 | Counterfactual analysis | `app/reasoning/counterfactual.py` | robustness report, what-if runs |
| 12 | Human-in-the-loop | `app/evidence/audit.py` | dispositions in a hash-chained audit log |
| 13 | Dossier data | `app/evidence/dossier.py` | JSON for the PDF generator |
| 14–15 | Evidence commitment/verification | `app/evidence/bundle.py` | snapshot, `bundle_hash`, verify |

## Design decisions

**AI proposes and rules decide.** The LLM (Claude, `claude-opus-5` by default) only maps clauses onto a fixed metric vocabulary using structured outputs (`messages.parse` with a Pydantic schema). The deterministic engine does the evaluation. Candidates that point at clause ids not in the document are dropped. Requirements that cannot be mapped are kept as `Unmapped` rules and evaluate to `UNKNOWN`. If the LLM call fails for any reason (no credentials, network, refusal, truncation), extraction falls back to the pattern extractor and records a warning. Demo Mode uses the pattern extractor so the presentation is deterministic and works offline.

**Missing data is not wrongdoing.** Absent evidence yields `UNKNOWN`, never `FAIL`. Unknown results on mandatory rules and registry gaps become `DATA_QUALITY` findings, not adverse ones.

**Relationships are not fraud.** A signal is escalated only when independent evidence families corroborate each other:

| Level | Rule |
|---|---|
| HIGH | support ≥ 0.90, behavioural evidence present, ≥ 2 independent families |
| MEDIUM | support ≥ 0.45, ≥ 2 independent families |
| LOW | evidence present without independent corroboration (relationship noted, not escalated) |

The families are corporate (director / address / contact), behavioural (co-bidding, rotation, price proximity, timing) and document (proposal similarity). The Isolation Forest adds support but never counts as a family of its own. Weights are listed in `app/reasoning/scoring.py` and served at `/api/meta/scoring`.

**Behaviour thresholds are relative to chance.** "Repeated co-bidding" requires at least 3 common tenders *and* at least 1.75× the count expected if both vendors participated independently. Document similarity is compared against the tender's median pair similarity (strong: ≥ 0.75 and ≥ median + 0.25).

**Counterfactuals reuse the same rule.** Removing evidence re-runs `assess()` on what is left, so a what-if result can always be re-derived by hand. The robustness report adds leave-one-out results, family ablation and the minimal breaking set: the smallest removal that drops the finding below escalation.

**Integrity is layered.** Audit entries are hash-chained (`prev_hash` → `entry_hash`). The evidence bundle hashes the rulebook, compliance results, findings, the audit trail up to the snapshot, and the SHA-256 of every stored document file. The blockchain module commits only the resulting hash.

## Demo dataset (planted scenarios, spec §27)

| Scenario | Vendors | Expected result | Actual |
|---|---|---|---|
| Multi-signal case | A (V001) + B (V002) | investigation signal | HIGH, 8 evidence items, robustness 1.0 |
| Single weak relationship | C (V003) + D (V004) | much weaker result | LOW, shared director only |
| Compliance failure | E (V005) | deterministic FAIL | ISO 9001 expired before bid date |
| Missing information | F (V006) | UNKNOWN / insufficient data | ownership disclosure missing, directors unavailable |

Random background noise can also produce LOW "relationship noted" items, for example C ↔ F with 3 co-bids. This shows that single weak signals are not escalated.

The dataset is deterministic: `TS_RANDOM_SEED=14` and PDFs are rendered with `invariant=1`, so the same seed produces the same data.
