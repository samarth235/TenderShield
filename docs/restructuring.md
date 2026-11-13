# Procurement restructuring engine (primary objective, SDG 9.3)

Code: `backend/app/restructuring/` and `backend/app/market/`. API: `backend/app/api/restructuring_routes.py`.

```text
tender PDFs + BOQ ──► components.py ──► dependencies.py ──► packaging.py ──► plan.py ──► dossier.py
   (provenance)      items→capabilities   coupling graph     all feasible     narrative   PDF A–F
                           ▲                                  structures,
                    classifier.py (CPV-trained)               scored + sensitivity
                                                                  ▲
real awards/bids ──► market/sources.py ──► market/profiles.py ──► matching.py (pools, CPWD scale rule)
                                                              └─► relationships.py (secondary objective)
                     competition.py (Prozorro-trained) ───────► packaging.py
```

## Stages

1. **Work items** - scope blocks are found in the tender text (work verbs or Scope-of-Work sections;
   eligibility/legal boilerplate excluded) or read from the BOQ. Each keeps document, page/row and text.
2. **Capabilities** - 12 capabilities defined by CPV prefixes (`taxonomy.py`), predicted by the classifier.
3. **Component values** - BOQ amounts > amounts in the text > share of the stated estimate
   (flagged as an assumption) > unknown. Users can override (`PUT .../components/values`).
4. **Dependency graph** - documented engineering priors per capability pair + text evidence
   (safety / interface / schedule / installation cues, with quotes) − relief when an open standard
   (DLMS, Modbus, OPC UA, MQTT...) defines the interface. Strong (≥0.75) links are hard constraints.
   Design/supervision is treated as *independence-preferred* (separate from works).
5. **Structures** - every set partition of components (strong groups merged first) is enumerated
   and scored:

   `value = 0.20·competition + 0.25·coverage + 0.25·SME access − 0.10·coordination − 0.15·integration risk − 0.05·scale loss`

   * competition: expected bidders (competition model × bundling factor), saturating at 5
   * coverage: real suppliers with evidence for *every* capability in the package, saturating at 3
   * SME access: share of value in packages whose turnover requirement (30 % of value) is within the
     MSME *small* ceiling (₹100 Cr, from 1 Apr 2025) **and** that have ≥1 SME candidate with evidence
   * coordination / integration risk: weight of the dependencies cut, risk weighted by type
     (safety 1.5, interface 1.0, installation 0.8, schedule 0.5)
   * scale loss: value in packages below ₹2 Cr when split

   Weights and parameters are request inputs. A sensitivity test perturbs every weight ×U(0.5,1.5)
   300 times and reports how often the recommendation stays best.
6. **Supplier pools** - per package, suppliers with published awards in each capability, scale
   checked with the CPWD similar-work rule (1×80 % / 2×50 % / 3×40 % of package value).
   Status: `POTENTIALLY_SUITABLE`, `LIMITED_SCALE_EVIDENCE`, `PARTIAL_CAPABILITY`.
   MSME status is a labelled size proxy until Udyam evidence is imported.
7. **Relationship screening** (secondary objective) on the shortlist: co-bidding, win rotation,
   JV/consortium awards, same project, near-identical names - each with ordinary explanations.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta/capabilities` | taxonomy, default weights/params, FX reference rates |
| GET | `/api/models` | model cards (training data, metrics, limitations) |
| GET | `/api/market/status` | loaded datasets with provenance and counts |
| GET | `/api/market/suppliers?q=&capability=&country=&sme_only=` | search supplier profiles |
| GET | `/api/market/suppliers/{key}` | profile + award records |
| POST | `/api/market/import` | load a World Bank / OCDS / award-notice file |
| POST | `/api/market/udyam` | attach verified MSME evidence |
| POST | `/api/tenders/{id}/documents` | add scope / specification PDFs |
| POST | `/api/tenders/{id}/boq` | upload BOQ (.xlsx/.xls/.csv) |
| PUT | `/api/tenders/{id}/components/values` | set component values (₹ Cr) |
| POST | `/api/tenders/{id}/restructure` | run; body `{weights, params, countries}` |
| GET | `/api/tenders/{id}/restructuring` | last plan |
| POST | `/api/tenders/{id}/restructuring/dossier` | render the PDF dossier (returns SHA-256 of PDF and plan) |

## What it will not do

Award contracts, declare a firm qualified, claim savings, or call a relationship collusion. The
integrated contract is always Scenario A and wins whenever splitting does not pay for itself.
