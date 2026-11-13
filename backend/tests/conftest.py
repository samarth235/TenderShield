import os
import tempfile

# Isolate test data before any app module reads the settings.
os.environ["TS_DATA_DIR"] = tempfile.mkdtemp(prefix="tendershield-test-")
os.environ["TS_EXTRACTOR"] = "pattern"
os.environ["TS_ENABLE_DEMO"] = "1"
# Run the suite against PostgreSQL with TS_TEST_DATABASE_URL=postgresql://... (the database is wiped).
if os.environ.get("TS_TEST_DATABASE_URL"):
    os.environ["TS_DATABASE_URL"] = os.environ["TS_TEST_DATABASE_URL"]
    import psycopg

    with psycopg.connect(os.environ["TS_DATABASE_URL"], autocommit=True) as _c:
        _c.execute("DROP SCHEMA public CASCADE")
        _c.execute("CREATE SCHEMA public")
else:
    os.environ.pop("TS_DATABASE_URL", None)  # tests exercise the assurance pipeline on the fabricated dataset
os.environ["TS_EMBEDDING_BACKEND"] = "tfidf"

import pytest  # noqa: E402

from app.auth import create_user, issue_token  # noqa: E402
from app.db import fetch_one, init_db, session  # noqa: E402
from app.demo.generator import load_demo  # noqa: E402
from app.demo.scenario import DEMO_TENDER_ID  # noqa: E402
from app.pipeline import run_analysis  # noqa: E402

TENDER = DEMO_TENDER_ID


@pytest.fixture(scope="module")
def analyzed():
    """Fresh demo dataset with the full analysis pipeline applied."""
    load_demo()
    return run_analysis(TENDER)


def auth_headers(role: str = "officer") -> dict[str, str]:
    """Bearer header for a test user with the given role (created on first use)."""
    init_db()
    email = f"{role}@test.local"
    with session() as conn:
        user = fetch_one(conn, "SELECT * FROM users WHERE email = ?", (email,))
        if user is None:
            user = create_user(conn, email, "correct-horse-battery", role)  # type: ignore[arg-type]
    token, _ = issue_token(user)
    return {"Authorization": f"Bearer {token}"}
