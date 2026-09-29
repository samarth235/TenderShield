# TenderShield Nexus — Backend + AI/ML

This service is a FastAPI app. It handles tender ingestion, AI rule extraction, deterministic compliance checks, entity resolution, the relationship graph, bid-document similarity, behavioural anomaly detection, evidence reasoning, counterfactual robustness, human disposition, and the evidence bundles that the blockchain module commits.

- API contract for the frontend and blockchain teammates: [`../docs/backend-api.md`](../docs/backend-api.md)
- Stage-by-stage workflow and design decisions: [`../docs/pipeline.md`](../docs/pipeline.md)

## Setup

Requires Python 3.11+. Development and CI use 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # runtime + pytest/ruff/httpx
cp .env.example .env                              # optional
```

You can also run `make setup` from the repository root.

Optional extras:

| Feature | How to enable |
|---|---|
| Claude rule extraction | set `ANTHROPIC_API_KEY` (or run `ant auth login`), then `TS_EXTRACTOR=llm` or pass `{"method": "llm"}` to `analyze` |
| Neural sentence embeddings | `pip install -r requirements-ml.txt`, then set `TS_EMBEDDING_BACKEND=sbert` (the model downloads on first use) |

## Run

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Interactive docs are at http://localhost:8000/docs. Load the demo with `POST /api/demo/load?analyze=true`.

```bash
.venv/bin/python -m scripts.seed_demo        # load the demo + run the pipeline, print stage summaries
.venv/bin/python -m scripts.hero_demo        # rehearse the full hero demo (in-process, no server)
.venv/bin/python -m scripts.hero_demo --url http://localhost:8000   # ...against a running server
.venv/bin/python -m scripts.export_openapi   # refresh ../docs/openapi.json for the frontend
```

## Test

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check app tests scripts
```

The tests cover rule extraction (including mocked LLM output and the fallback path), the compliance semantics, entity-resolution precision against the dataset's ground truth, similarity and behaviour detection of the planted pair, the scoring and counterfactual rules, and the full API hero flow with tamper detection and exploration-mode uploads.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TS_DATA_DIR` | `backend/var` | SQLite DB + generated / uploaded PDFs |
| `TS_EXTRACTOR` | `pattern` | `pattern` \| `llm` \| `auto` |
| `TS_LLM_MODEL` | `claude-opus-5` | Claude model for rule extraction |
| `TS_EMBEDDING_BACKEND` | `tfidf` | `tfidf` \| `sbert` |
| `TS_SBERT_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `TS_RANDOM_SEED` | `14` | demo dataset + Isolation Forest seed |
| `TS_CORS_ORIGINS` | Vite / CRA dev ports | allowed browser origins |

## Layout

```text
app/
  main.py              FastAPI app (CORS, router)
  config.py, db.py     settings, SQLite schema + helpers
  pipeline.py          end-to-end analysis workflow with per-stage timings
  api/                 routes + request schemas
  demo/                deterministic simulated market (registry + 5-year award history), PDFs, tamper demo
  ingestion/           PDF text extraction, bidder fact extraction, exploration uploads
  nlp/                 clause segmentation, pattern + Claude extractors, rulebook model
  compliance/          deterministic rule engine
  entities/            entity resolution (names, directors, addresses, contacts)
  graph/               NetworkX relationship graph + views
  intelligence/        document similarity (TF-IDF / SBERT), behaviour + Isolation Forest
  reasoning/           scoring rule, findings + reasoning chains, counterfactuals
  evidence/            audit chain, evidence bundles / verification, dossier data
scripts/               seed_demo, hero_demo, export_openapi
samples/               example bidder uploads (CSV / JSON)
tests/                 pytest suite
```
