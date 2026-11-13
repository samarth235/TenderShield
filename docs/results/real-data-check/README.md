# TenderShield on real-life data: datasets, documents, models and results

Last run: 2026-11-13, branch `feature/sdg93-upgrade`. Every number here comes from a run, and the files
listed sit in this folder.

## 1. Datasets used

| Dataset (publisher, licence) | Raw size | What TenderShield uses it for | Sample in `dataset_samples/` |
|---|---|---|---|
| **World Bank Major Contract Awards** (World Bank, CC BY 4.0) | about 244,000 rows, all countries; **7,434 Indian awards** stored after cleaning | **The evidence base for proposing SMEs.** Every Indian supplier, its awards, values, capabilities and size proxy come from here | `worldbank_major_contract_awards_india.sample.csv` (raw), `market_awards_india_cleaned.sample.csv` (cleaned) |
| **World Bank procurement notices, India** (World Bank) | 500 notices, of which 134 are Invitations for Bids | The real tenders that were tested | `worldbank_india_invitations_for_bids.index.csv` (all 134) |
| **CPV 2008 vocabulary** (EU Regulation 213/2008) | 9,454 codes | Training data for the capability classifier | `cpv_2008_codes.sample.csv` |
| **Prozorro lots / tenders / bids / contracts** (Ukraine, CC BY 4.0, Thesis Institute) | 92,802 lots, 238,228 bids, 95,272 contracts | Training data for the competition model (expected number of bidders) | `prozorro_*.sample.csv` |
| **Hand-labelled Indian tender lines** (made in this project) | 152 lines from 85 notices | Teaching the classifier Indian phrasing (train half) and measuring it (test half) | `data/annotations/india_wb_notice_lines.csv` |

**Which data actually proposes SMEs.** With `TS_MARKET_COUNTRIES=India`, supplier matching only uses Indian
awards: 7,434 World Bank-financed contract awards signed between 1992-11-28 and 2020-01-01, from
**3,496 Indian suppliers**. Of those suppliers, 2,858 are "small" and 638 are "large" by the size proxy
(largest award at or below ₹30 crore). The Ukrainian Prozorro data never proposes an Indian supplier. It only
trains the bidder-count model. `dataset_samples/sme_candidate_profiles.sample.csv` shows 20 Indian SME
candidate profiles, and `dataset_samples/market_store_stats.json` has the full counts.

Cleaning applied when building the market store (`scripts/build_market.py`):

- Indian rows are filtered from the global file.
- Supplier names are normalised into a supplier key.
- Amounts are converted to ₹ crore at the reference rates in `app/market/fx.py`.
- Each award is classified into a capability (the classifier and the CPV code where present). The basis and
  confidence are stored in `capability_basis`.
- Awards and bids are de-duplicated.
- Supplier profiles are aggregated: number of awards, largest award, capabilities, first and last award date.
- Every row keeps its source dataset and the file's SHA-256.

## 2. Documents considered

All 134 "Invitation for Bids" notices for India were run through the system (`batch_134_ifb_summary.json`):

| Outcome | Notices |
|---|---|
| Restructuring plan produced | 88 |
| No scope found (the notice only says "see the bidding document") | 32 |
| No usable text | 14 |

The full list is in `dataset_samples/worldbank_india_invitations_for_bids.index.csv`.

**The four test documents** are in `test_documents/`, each as a PDF (the text the system read) and a TXT
(the same text):

| File | Tender | Why it matters |
|---|---|---|
| `OP00460403.pdf` | **Ukai Dam, Gujarat**: seven civil and electro-mechanical works, each with its own estimated cost (₹46.84 cr in total) | **The split example** (section 4) |
| `OP00474853.pdf` | SMART Maharashtra: millet processing and value addition plant, supply and installation, 9 line items | A goods tender with a line-item table |
| `OP00471901.pdf` | Gurugram Metro: viaduct and elevated stations, 13.3 km | A large civil works tender |
| `OP00464558.pdf` | PTCUL Uttarakhand: restoration of a 132 kV GIS substation and line | An electrical EPC tender |

These PDFs render the official notice text published by the World Bank. Full bidding documents (BOQ and
specifications) sit on the state e-procurement portals, which need bidder registration, so they were not
downloaded.

## 3. Models and methods, stage by stage

| Stage | Method or model | Trained on / based on | Measured quality |
|---|---|---|---|
| PDF text | `pypdf` text extraction (no OCR) | - | Scanned PDFs are not supported |
| Requirement extraction | Rule-based: line-item tables, "Details of Works" lists with their cost lines, labelled fields ("Name of work:"), a boilerplate filter, and the tender title as a fallback (`restructuring/components.py`) | Built and checked on real notices | **Precision 0.91** on 89 held-out extracted lines (47 notices). Recall not measured |
| Capability classification | TF-IDF (word 1–2-grams + character 3–5-grams) + logistic regression, blended with a keyword lexicon. Procedural lead-ins ("Providing and installation of") are stripped before the model sees the text (`restructuring/classifier.py`) | 9,454 CPV descriptions + 53 hand-labelled Indian lines (weight 8) | **Held-out Indian lines: accuracy 0.84, macro-F1 0.79** (before this work: 0.63 / 0.50). CPV 5-fold CV: macro-F1 0.74, accuracy 0.79 |
| Technical dependency graph | Expert prior table per capability pair, plus text cues (safety, interface, schedule, installation, open standards), built with NetworkX (`restructuring/dependencies.py`) | Engineering rules, written down with their reasons | Not measured |
| Package generation | Every feasible set partition, keeping strongly dependent components together, scored on competition, coverage, SME access, coordination, integration risk and scale loss. Robustness is checked with 300 random weight perturbations (`restructuring/packaging.py`) | - | Not compared with experts yet |
| Expected bidders | HistGradientBoosting regression (Poisson loss) on contract value and capability (`restructuring/competition.py`) | 92,438 Prozorro lots | Poisson deviance 0.691 vs 0.701 baseline on 14,170 later lots. Ukrainian data, applied to India as an indicator only |
| SME capability matching | CPWD-style similar-work rule: the supplier's past awards in the same capability, compared with the package value. The MSME size proxy comes from the largest award; Udyam-verified status can be imported (`restructuring/matching.py`, `market/profiles.py`) | Indian World Bank awards | Not measured |
| Supplier relationship screening | Co-bidding and win rotation (bids), joint-venture names, same project, and fuzzy name overlap (rapidfuzz). Clusters via NetworkX (`restructuring/relationships.py`) | Bid and award records | No Indian bid data, so 0 relationships found in every Indian run. Not measured |
| Dossier | ReportLab PDF, sections A–F (`restructuring/dossier.py`) | - | - |

The secondary assurance pipeline (fraud signals on bids received) uses:

- Rule extraction: a pattern extractor, or Claude when `TS_EXTRACTOR=llm`.
- Entity resolution: rapidfuzz.
- Bid-behaviour anomalies: IsolationForest (300 trees).
- Document similarity: TF-IDF, or a sentence-transformer when `TS_EMBEDDING_BACKEND=sbert`.

## 4. Split example: Ukai Dam (OP00460403)

The notice lists seven works, each with its own estimated cost. TenderShield read all seven and their costs
(`OP00460403/plan.json`, `OP00460403/dossier.pdf`):

| Work (as written in the notice) | Estimated cost | Capability assigned |
|---|---|---|
| Concrete Trimix roads, asphalt strengthening, culverts and minor bridges | ₹11.52 cr | Civil |
| Turfing of the downstream slope of the earthen dam | ₹7.34 cr | Civil |
| Renovation of the VIP rest house | ₹3.72 cr | Civil |
| Protection work near the right training wall | ₹2.50 cr | Civil |
| Dam-top lighting and electrification | ₹6.51 cr | Electrical |
| CCTV, fire safety, boom barrier, including O&M | ₹2.38 cr | Telecom |
| SCADA gate operation, ARMC and monitoring, including O&M | ₹12.89 cr | O&M (**wrong**: this should be ICT or control systems) |

**Original structure:** one integrated contract worth ₹46.84 cr (the notice gives no overall estimate; this is the sum of the seven stated costs), score 0.093.

**Recommended:** 3 packages, score 0.489, out of 15 feasible structures. All three are within SME size (turnover required is 30% of package value):

| Package | Scope | Value | Turnover required | Suppliers with capability evidence | Of which meet similar-work scale | SME candidates | Expected bidders |
|---|---|---|---|---|---|---|---|
| P1 | Civil works (4 works) | ₹25.06 cr | ₹7.52 cr | 1,119 | 373 | 795 | 2.8 |
| P2 | Dam-top lighting and electrification | ₹6.51 cr | ₹1.95 cr | 230 | 141 | 162 | 2.4 |
| P3 | CCTV/fire safety + SCADA/monitoring | ₹15.27 cr | ₹4.58 cr | 259 | 5 | 169 | 0.2 |

- **Why P3 stays together:** CCTV and SCADA share an interface/safety dependency ("moderate"). Every other
  pair was weak, so the civil and electrical work can stand alone.
- **Robustness:** the 3-package structure stays best in 89% of 300 weight perturbations. The most common
  alternative is 4 packages (CCTV separated).
- **Proposed suppliers (examples, with evidence from Indian World Bank awards):**
  - P1: A. K. Patel and Company (small by proxy, 6 civil awards, largest ₹18.4 cr).
  - P2: L&T and ABB (large).
  - P3: thin evidence; only 5 suppliers meet the scale.
- **Real-world check:** the authority itself listed these as seven separately estimated works. TenderShield
  proposes grouping them into three packages by trade.

## 5. The other three tenders

| Tender | Result |
|---|---|
| Millet plant | All 9 line items extracted, all classified *Industrial & process machinery*. One trade, so it stays integrated. 34 suppliers have capability evidence, but the evidence is thin and old (2002–2012) |
| Gurugram Metro | The "Name of work" field extracted as *Civil*. One trade, so it stays integrated. 1,119 civil suppliers |
| 132 kV substation | The quoted "Detail of Work" extracted as *Electrical*. One trade, so it stays integrated. Top suppliers: L&T, ABB, Alstom, BHEL |

`plan_before*.json` in each folder is the output before the extraction fixes (which proposed splits based on
boilerplate text).

## 6. Evaluation (held-out test half)

Run `python -m scripts.evaluate_real_lines` from `backend/`. Before and after results are in
`eval_heldout_before.json` and `eval_heldout_after.json`.

| Metric | Before | After |
|---|---|---|
| Extraction precision (89 lines, 47 notices) | 0.91 | 0.91 |
| Classification accuracy (81 scope lines) | 0.630 | 0.840 |
| Classification macro-F1 | 0.495 | 0.792 |

Caveats:

- The labels are a first pass by the developer and need review by a domain expert.
- The extraction rules were developed while looking at all 134 notices, including the test half, so the
  extraction precision is optimistic.
- The classifier settings were chosen on the train half only. The lexicon weight 0.8 scored best there
  (0.774 vs 0.717 at the old 0.25). On the test half it raised macro-F1 (0.58 → 0.79) and lowered plain
  accuracy (0.88 → 0.84) compared with leaving the weight unchanged.

## 7. Known limits

- **Old Indian award data.** It ends in January 2020 (the World Bank mirror). The primary World Bank URL
  returns 404.
- **No Indian bid data.** Relationship screening finds nothing for Indian suppliers. CPPP or state award and
  bid data is needed.
- **Supplier names are not merged.** Example: "ALSTOM LTD." / "M/S ALSTOM LTD., JAIPUR" / "ALSTOM T&D INDIA
  LIMITED". The Jaipur entry is wrongly marked small.
- **Items in one trade are never split** (for example, the millet plant's processing lines and its packing
  machines).
- **Unmeasured:** extraction recall, supplier matching precision, package agreement with experts, and the
  relationship false-positive rate.

## Reproduce

From `backend/`:

```bash
python -m scripts.fetch_real_data
python -m scripts.build_market
python -m scripts.evaluate_real_lines
python -I ../docs/results/real-data-check/run_batch.py <scratch-dir> <repo-dir>
python -I ../docs/results/real-data-check/run_real.py <scratch-dir> <repo-dir> OP00460403 OP00474853 OP00471901 OP00464558
```

The runner scripts expect the market store at `<scratch-dir>/real/market.db`. Set `TS_DATA_DIR` and
`TS_MARKET_DB` to match when building it.
