# TenderShield Nexus - common tasks. Run from the repository root.
PY ?= python3.12
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup setup-ml run seed demo test test-pg migrate user up lint openapi clean web-setup web web-build data market

setup:            ## Create the backend virtualenv and install dependencies
	cd backend && $(PY) -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements-dev.txt

setup-ml:         ## Optional: neural sentence embeddings (TS_EMBEDDING_BACKEND=sbert)
	cd backend && .venv/bin/pip install -r requirements-ml.txt

run:              ## Start the API on http://localhost:8000 (docs at /docs)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

seed:             ## Local rehearsal only: load the fabricated demo tender (serve it with TS_ENABLE_DEMO=1)
	cd backend && .venv/bin/python -m scripts.seed_demo

demo:             ## Rehearse the hero demo end-to-end (in-process)
	cd backend && .venv/bin/python -m scripts.hero_demo

test:             ## Run the backend test suite (SQLite)
	cd backend && .venv/bin/python -m pytest

test-pg:          ## Run the backend test suite against an embedded PostgreSQL (wiped each run)
	cd backend && .venv/bin/python -m scripts.test_pg

migrate:          ## Apply database migrations (TS_DATABASE_URL, or the local SQLite file)
	cd backend && .venv/bin/alembic upgrade head

user:             ## Create a user: make user EMAIL=a@b.gov.in ROLE=officer
	cd backend && .venv/bin/python -m scripts.create_user --email $(EMAIL) --role $(or $(ROLE),viewer)

up:               ## Start PostgreSQL + the app with Docker Compose on http://localhost:8000
	docker compose up --build

lint:
	cd backend && .venv/bin/ruff check app tests scripts migrations

openapi:          ## Regenerate docs/openapi.json for the frontend
	cd backend && .venv/bin/python -m scripts.export_openapi

data:             ## Download the real public datasets into data/real/raw/
	cd backend && .venv/bin/python -m scripts.fetch_real_data

market:           ## Train models on real data and build the market (supplier) store
	cd backend && .venv/bin/python -m scripts.build_market

clean:            ## Delete generated data (database + PDFs)
	rm -rf backend/var

web-setup:        ## Install frontend dependencies
	cd frontend && npm install

web:              ## Start the dashboard on http://localhost:5173 (needs `make run` in another terminal)
	cd frontend && npm run dev

web-build:        ## Type-check and build the dashboard into frontend/dist
	cd frontend && npm run build
