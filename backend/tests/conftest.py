import os
import tempfile

# Isolate test data before any app module reads the settings.
os.environ["TS_DATA_DIR"] = tempfile.mkdtemp(prefix="tendershield-test-")
os.environ["TS_EXTRACTOR"] = "pattern"
os.environ["TS_EMBEDDING_BACKEND"] = "tfidf"

import pytest  # noqa: E402

from app.demo.generator import load_demo  # noqa: E402
from app.demo.scenario import DEMO_TENDER_ID  # noqa: E402
from app.pipeline import run_analysis  # noqa: E402

TENDER = DEMO_TENDER_ID


@pytest.fixture(scope="module")
def analyzed():
    """Fresh demo dataset with the full analysis pipeline applied."""
    load_demo()
    return run_analysis(TENDER)
