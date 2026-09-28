# TenderShield Nexus

**Explainable Tender Assurance & Evidence Intelligence Platform**

TenderShield Nexus is a procurement assurance layer that turns tender records into explainable, evidence-backed investigation cases. Its guiding principle: AI finds and explains signals, rules verify objective conditions, blockchain protects evidence integrity, and the human auditor makes the final decision.

## Repository layout

| Path | Owner | Status |
|---|---|---|
| `backend/` | Backend + AI/ML | implemented: FastAPI, rule extraction (pattern + Claude), compliance engine, entity resolution, NetworkX graph, document similarity, Isolation Forest, reasoning, counterfactuals, audit chain, evidence bundles |
| `frontend/` | Frontend | implemented: React + TypeScript investigation dashboard (Vite, TanStack Query, Cytoscape). See [`frontend/README.md`](frontend/README.md) |
| `blockchain/` | Blockchain + dossier | to be added (Solidity + Hardhat, PDF dossier). Hand-off described in [`docs/backend-api.md` §4](docs/backend-api.md#4-blockchain-hand-off) |
| `docs/` | shared | API contract, pipeline and design notes, OpenAPI schema |
| `.github/workflows/` | shared | `backend-ci.yml`: lint, tests, offline hero-demo rehearsal, OpenAPI freshness check. `frontend-ci.yml`: type-check + build |

## Quick start (backend)

```bash
make setup     # Python 3.12 venv + dependencies
make test      # test suite
make demo      # rehearse the full hero demo in the terminal
make run       # API on http://localhost:8000  (docs: /docs)
```

## Quick start (dashboard)

```bash
make web-setup # npm install
make run       # terminal 1: API on :8000
make web       # terminal 2: dashboard on http://localhost:5173
```

Click **Load demonstration tender**, then follow the sidebar from 00 to 06.

The demo runs completely offline. Claude-based rule extraction and neural embeddings are optional (see `backend/README.md`).
