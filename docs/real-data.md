# Real data: what TenderShield trains on, matches against, and demos with

Every model and every supplier match in the restructuring module is built from published, real
procurement records. Synthetic data is used only in CI test fixtures (`backend/tests/fixtures/`,
labelled as such) and in the original Demo Mode tender of the secondary (assurance) pipeline.

## 1. Datasets

| Dataset | Real? | Used for | Licence | How it gets here |
|---|---|---|---|---|
| **CPV 2008 vocabulary** - 9,454 official codes + descriptions (EU Regulation 213/2008) | Yes | Training the capability classifier | EU legal text, reusable | Committed: `data/real/cpv_2008_codes.csv` |
| **Prozorro lots / tenders / bids / contracts** - 92,802 lots, 238,228 bids, 95,272 contracts (Ukraine, 2019-2023) | Yes | Training the competition model; real co-bidding networks; supplier-matching evaluation | CC BY 4.0 (Thesis Institute derived tables of the public Prozorro API) | `fetch_real_data.py --only prozorro` |
| **World Bank Major Contract Awards** (filter: Borrower Country = India) | Yes | Indian supplier capability evidence and pools | CC BY 4.0 | `fetch_real_data.py --only worldbank` (needs a normal internet connection) |
| **World Bank procurement notices, India** | Yes | Real tender texts for quick tests | World Bank terms | `fetch_real_data.py --only wb_notices` |
| **CPPP / eProcure Award-of-Contract notices** | Yes | Indian award evidence for the demo department | As published | Compile into the `awards_csv` format (below) |
| **OCDS publications** (any publisher) | Yes | Awards + bids where a publisher offers OCDS | Publisher licence | `build_market.py --ocds file.jsonl --ocds-country India` |
| **Udyam (MSME) registration evidence** | Yes, checked by hand | Turning MSME *proxies* into *verified* status | - | `POST /api/market/udyam` |

Every downloaded file is recorded in `data/real/raw/MANIFEST.json` (URL, bytes, SHA-256, time) and
every imported dataset in the `market_sources` table (origin URL, licence, file SHA-256, row counts),
so a supplier's evidence card links back to a published record.

## 2. Build it (from `backend/`)

```bash
python -m scripts.fetch_real_data        # downloads into data/real/raw/ (~70 MB)
python -m scripts.build_market           # trains both models + builds var/market.db
export TS_MARKET_COUNTRIES=India         # match Indian tenders against Indian award records only
```

Trained models are committed (`backend/models/*.joblib` + `*.card.json`), so the API works offline
without the raw files; the raw files are only needed to retrain or rebuild the market store.

## 3. Current model results (see the `.card.json` files for full detail)

| Model | Data | Evaluation | Result |
|---|---|---|---|
| Capability classifier (TF-IDF + logistic regression) | 9,454 CPV descriptions | 5-fold stratified CV | macro-F1 0.75, accuracy 0.79 |
| Competition model (Poisson gradient boosting) | 92,438 Prozorro lots | time split: train 2019-21, test 2022+ (14,170 lots) | Poisson deviance 0.691 vs 0.701 per-capability baseline |

Honest reading:

- The classifier learns catalogue wording. Indian BOQ wording is a domain shift, so it is blended
  with a curated Indian-phrasing lexicon, and **transfer accuracy on real Indian lines is not yet
  measured** - see section 4.
- In the real lot data, value explains little about how many firms bid (larger lots draw slightly
  *more* bids). The competition model is therefore a weak, relative input (weight 0.20); the
  stronger competition signal is the number of real suppliers with capability evidence, and the
  bundling penalty measured from real supplier co-capability data.

## 4. To-do that makes the evaluation real for India (owner: data)

1. Annotate ~200 lines - half from World Bank India contract descriptions, half from the BOQ of
   the demo tender - into `data/annotations/capability_gold.csv` (`text,capability`). Re-run
   `build_market.py`; the classifier card then reports accuracy on real Indian text.
2. Compile the demo department's last 2-3 years of CPPP Award-of-Contract notices into
   `data/real/india/cppp_awards.csv` and load with `--awards-csv`.
3. Verify MSME status on udyamregistration.gov.in for the shortlisted firms and import it.

`awards_csv` columns: `award_id, tender_ref, title, description, buyer, supplier_name, supplier_gstin,
supplier_country, amount, currency, signed_on, cpv, country, source_url` (unknown cells left blank).

## 5. Live demo with a real tender

1. On eprocure.gov.in pick a live multi-component works/SITC tender (e.g. a water-supply, smart-city
   or station-redevelopment tender) and download the NIT / tender document PDF(s) and the BOQ
   (CPPP BOQs are `.xls`: open and *Save As* `.xlsx`, or install `xlrd`).
2. `POST /api/uploads/tender` (PDF) -> `POST /api/tenders/{id}/documents` (scope / specs PDFs) ->
   `POST /api/tenders/{id}/boq` (xlsx/csv).
3. `POST /api/tenders/{id}/restructure` with `{"countries": ["India"]}`.
4. `POST /api/tenders/{id}/restructuring/dossier` -> open the PDF.
5. Secondary objective on the same tender: once bids exist, upload bidders and run
   `POST /api/tenders/{id}/analyze` (the original assurance pipeline).

Rehearse with two tenders: one that splits, and one that should stay integrated - showing the
system can say "don't split" is part of the credibility.
