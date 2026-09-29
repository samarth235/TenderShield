"""Single-container deployment: the API serves the built dashboard and seeds the demo on an empty database."""

from fastapi.testclient import TestClient

from app.db import fetch_one, reset_db, session
from app.main import create_app

from .conftest import TENDER


def test_serves_dashboard_with_spa_fallback(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setenv("TS_STATIC_DIR", str(tmp_path))
    monkeypatch.delenv("TS_AUTOLOAD_DEMO", raising=False)

    with TestClient(create_app()) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/assets/app.js").text == "console.log(1)"
        # Client-side routes fall back to index.html.
        for path in ("/", "/graph", "/findings/TN-2026-014-F01"):
            r = c.get(path)
            assert r.status_code == 200 and "id=root" in r.text
        # Unknown API paths stay JSON 404s instead of returning the dashboard.
        r = c.get("/api/does-not-exist")
        assert r.status_code == 404 and r.headers["content-type"] == "application/json"
        # Files outside the static directory are never served.
        assert "nope" not in c.get("/%2e%2e/secret.txt").text


def test_no_static_dir_means_api_only(monkeypatch):
    monkeypatch.delenv("TS_STATIC_DIR", raising=False)
    with TestClient(create_app()) as c:
        assert c.get("/graph").status_code == 404


def test_autoload_seeds_empty_database(monkeypatch):
    reset_db()
    monkeypatch.setenv("TS_AUTOLOAD_DEMO", "1")
    with TestClient(create_app()) as c:
        assert c.get(f"/api/tenders/{TENDER}").status_code == 200
        assert c.get(f"/api/tenders/{TENDER}/findings").json()
    with session() as conn:
        assert fetch_one(conn, "SELECT tender_id FROM tenders WHERE tender_id = ?", (TENDER,))
