"""Run the backend test suite against an embedded PostgreSQL server (no Docker needed).

Usage (from backend/):  python -m scripts.test_pg [pytest args...]
Needs `pip install -r requirements-dev.txt` (pgserver). The test database is wiped on each run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pgserver


def main() -> int:
    data = Path(__file__).resolve().parents[1] / "var" / "pg-test"
    server = pgserver.get_server(data, cleanup_mode=None)
    env = {**os.environ, "TS_TEST_DATABASE_URL": server.get_uri()}
    return subprocess.call([sys.executable, "-m", "pytest", *sys.argv[1:]], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
