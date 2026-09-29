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

Ordinary market structure also produces LOW "relationship noted" items. Vendor E works the same Mumbai-region traffic market as A and B, so each pair meets in 5 tenders, well above the independence baseline. That is behavioural evidence from one family only, so it is not escalated.

### Simulated market (`app/demo/market.py`, `app/demo/history.py`)

The background is modelled on urban-local-body works procurement rather than random draws:

- **Registry:** 260 contractors. That is the six bidders, 20 hand-authored background actors (V007-V026) and 234 generated firms. Each firm has a constitution (public / private limited, LLP, partnership, proprietorship), CIN or LLPIN, PAN with the correct entity character, a GSTIN with a valid check digit, DINs for company directors and LLP partners (partners of firms have none), a registered address with a real PIN code, and work categories, home market and reach.
- **History:** 480 awarded tenders from January 2021 to January 2026, spread across 8 regional markets (MMR, Pune, Nashik, Nagpur, Gujarat, Chennai, Hyderabad, Bengaluru), 21 buyers and 6 work segments (traffic/ITS, roads, drains, street lighting, water supply, buildings). Each segment has its own value distribution and pricing. Volume peaks at fiscal-year end and is thin in 2021. Bidders are firms working that segment and market that meet the 20%-of-estimate turnover criterion, are more than a year old and are not debarred. Tenders average about 3.7 bids, and some are single-bid. The lowest technically qualified bid wins, and about 5% of bids are rejected at technical evaluation. Most bids are filed on the last day.
- **Messy records:** Award records spell names the way clerks do ("M/s.", upper case, Pvt/Private, Engg., Shri/Shree, typos). They carry a GSTIN only about half the time, often the firm's registration in the tender's state. About 5% of bids come from firms missing from the registry. Entity resolution matches GSTIN, then PAN inside GSTIN, then normalised name, then fuzzy name. It links 98% of records with no false matches.

Planted background structure (none of it touches the current tender's findings, but all of it is visible in the graph and the behaviour model):

| Structure | Vendors | What the data shows |
|---|---|---|
| Hidden network around the A/B ring | V007 Shreeji Traffic Solutions, V008 Sharma Realty | V007 shares Vendor B's landline and files cover bids in 5 of the 9 ring tenders (disqualified: too small). Its partner Sunita Sharma co-directs V008 with Vendor A's director. |
| Pune road-works ring | V009, V010, V011 | 12 tenders with a three-way winner rotation. V009 and V011 share a director, and V010 and V011 share an office. |
| Nagpur street-lighting pair | V012, V013 (+ V014) | 8 alternating wins. All three use one bid consultant's e-mail domain; V014 is an innocent client of that consultant. |
| Legitimate group companies | V015, V016 | Same directors, head office and e-mail domain, and they never bid against each other. Corporate links alone stay LOW. |
| Dominant national players | V017, V018 | Meet in most large ITS tenders and genuinely compete. The Isolation Forest still flags them, which is why the model never counts as an evidence family on its own. |
| Independent directors | Meera Iyer (C, D, V019, V020), Dr. Venkatesh Subramanian (V015, V018) | Board interlocks with no bidding coordination. |
| Virtual-office address | V021-V024 | Four unrelated firms registered at one Thane address. |
| Debarred firm reborn | V025, V026 | V025 is debarred by PMC in Feb 2024. V026, with the same directors, is incorporated two months later and starts bidding. |

The Pune, Nagpur and A/B rings are the top population outliers of the Isolation Forest. The tender graph shows bidders plus the registry vendors one corporate hop away, so the Shreeji / Sharma Realty network around Vendors A and B and the Meera Iyer boards around Vendors C and D both appear.

The dataset is deterministic: `TS_RANDOM_SEED=14` and PDFs are rendered with `invariant=1`, so the same seed produces the same data.
