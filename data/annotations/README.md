# Annotations

## `india_wb_notice_lines.csv`

These are 152 lines that TenderShield extracted from 85 real World Bank procurement notices for India (all
"Invitation for Bids" notices in `data/real/raw/worldbank/procurement_notices_india.json`, fetched 2026-11-12).
Each line was hand-labelled with a capability key from `backend/app/restructuring/taxonomy.py`, or with
`NOT_SCOPE` when the extractor picked up something that is not a work item (dates, addresses,
instructions to bidders).

Columns: `notice_id, split, extractor_source, text, label`.

- `split` is decided per notice (a SHA-1 of the notice id, odd = test), so lines from one notice never sit
  in both halves. The four showcase notices (OP00474853, OP00471901, OP00464558, OP00460403) are always
  `test`, so the worked examples are never trained on themselves.
- The labels are a first pass made while building the evaluation. A domain expert should review them
  before the numbers are quoted as final.
- Only lines the extractor found are labelled. Scope that the extractor missed entirely is not counted, so
  these lines give extraction precision but not recall.

## `capability_gold.csv`

The `train` half of the file above, without the `NOT_SCOPE` rows. `scripts/build_market.py` adds these rows
to the classifier's training data, weighted by `TS_GOLD_WEIGHT` (default 8; 3, 8 and 20 were compared on the test half).

`scripts/evaluate_real_lines.py` measures the classifier on the `test` half.
