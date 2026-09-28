# TenderShield Nexus - common tasks. Run from the repository root.
PY ?= python3.12
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup setup-ml run seed demo test lint openapi clean web-setup web web-build

setup:            ## Create the backend virtualenv and install dependencies
	cd backend && $(PY) -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements-dev.txt

setup-ml:         ## Optional: neural sentence embeddings (TS_EMBEDDING_BACKEND=sbert)
	cd backend && .venv/bin/pip install -r requirements-ml.txt

run:              ## Start the API on http://localhost:8000 (docs at /docs)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

seed:             ## Load the demonstration tender and run the full analysis
	cd backend && .venv/bin/python -m scripts.seed_demo

demo:             ## Rehearse the hero demo end-to-end (in-process)
	cd backend && .venv/bin/python -m scripts.hero_demo

test:             ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest

lint:
	cd backend && .venv/bin/ruff check app tests scripts

openapi:          ## Regenerate docs/openapi.json for the frontend
	cd backend && .venv/bin/python -m scripts.export_openapi

clean:            ## Delete generated data (database + PDFs)
	rm -rf backend/var

web-setup:        ## Install frontend dependencies
	cd frontend && npm install

web:              ## Start the dashboard on http://localhost:5173 (needs `make run` in another terminal)
	cd frontend && npm run dev

web-build:        ## Type-check and build the dashboard into frontend/dist
	cd frontend && npm run build
