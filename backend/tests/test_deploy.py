"""Single-container deployment: the API serves the built dashboard and never seeds fabricated data."""

from fastapi.testclient import TestClient

from app.db import fetch_one, reset_db, session
from app.main import create_app

from .conftest import TENDER, auth_headers


def test_serves_dashboard_with_spa_fallback(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setenv("TS_STATIC_DIR", str(tmp_path))

    with TestClient(create_app()) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/assets/app.js").text == "console.log(1)"
        # Client-side routes fall back to index.html.
        for path in ("/", "/graph", "/findings/TN-2026-014-F01"):
            r = c.get(path)
            assert r.status_code == 200 and "id=root" in r.text
        # Unknown API paths stay JSON 404s instead of returning the dashboard.
        r = c.get("/api/does-not-exist", headers=auth_headers())
        assert r.status_code == 404 and r.headers["content-type"] == "application/json"
        # Files outside the static directory are never served.
        assert "nope" not in c.get("/%2e%2e/secret.txt").text


def test_no_static_dir_means_api_only(monkeypatch):
    monkeypatch.delenv("TS_STATIC_DIR", raising=False)
    with TestClient(create_app()) as c:
        assert c.get("/graph").status_code == 404


def test_empty_database_stays_empty(monkeypatch):
    """No fabricated records are loaded on start-up, whatever the environment says."""
    reset_db()
    monkeypatch.setenv("TS_AUTOLOAD_DEMO", "1")
    with TestClient(create_app(), headers=auth_headers()) as c:
        assert c.get(f"/api/tenders/{TENDER}").status_code == 404
        assert c.get("/api/tenders").json() == []
    with session() as conn:
        assert fetch_one(conn, "SELECT tender_id FROM tenders WHERE tender_id = ?", (TENDER,)) is None


def test_demo_routes_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TS_ENABLE_DEMO", "0")
    with TestClient(create_app(), headers=auth_headers()) as c:
        assert c.get("/api/health").status_code == 200
        assert c.post("/api/demo/load").status_code == 404
