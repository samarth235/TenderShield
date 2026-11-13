"""Authentication, role-based access control and audit attribution."""

from fastapi.testclient import TestClient

from app.auth import hash_password, login_limiter, verify_password
from app.main import create_app

from .conftest import auth_headers


def _client(**kw) -> TestClient:
    return TestClient(create_app(), **kw)


def test_password_hashing_round_trip():
    stored = hash_password("correct-horse-battery")
    assert stored.startswith("scrypt$") and "correct-horse" not in stored
    assert verify_password("correct-horse-battery", stored)
    assert not verify_password("wrong-password-123", stored)
    assert not verify_password("anything", "garbage")


def test_api_requires_a_session():
    with _client() as c:
        assert c.get("/api/health").status_code == 200  # public liveness probe
        r = c.get("/api/tenders")
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
        assert c.get("/api/tenders", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_login_and_me():
    auth_headers("officer")  # ensures officer@test.local exists
    login_limiter._hits.clear()
    with _client() as c:
        bad = c.post("/api/auth/login", json={"email": "officer@test.local", "password": "nope-nope-nope"})
        assert bad.status_code == 401
        unknown = c.post("/api/auth/login", json={"email": "nobody@test.local", "password": "nope-nope-nope"})
        assert unknown.json()["detail"] == bad.json()["detail"]  # no account enumeration
        ok = c.post("/api/auth/login", json={"email": "Officer@Test.local", "password": "correct-horse-battery"})
        assert ok.status_code == 200
        token = ok.json()["access_token"]
        me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
        assert me["email"] == "officer@test.local" and me["role"] == "officer"
        assert "password_hash" not in me


def test_login_is_rate_limited():
    login_limiter._hits.clear()
    with _client() as c:
        codes = [c.post("/api/auth/login", json={"email": "x@test.local", "password": "wrong-password"}).status_code
                 for _ in range(12)]
    login_limiter._hits.clear()
    assert codes[:10] == [401] * 10 and codes[-1] == 429


def test_viewer_is_read_only():
    with _client(headers=auth_headers("viewer")) as c:
        assert c.get("/api/tenders").status_code == 200
        r = c.post("/api/uploads/tender", files={"file": ("t.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 403


def test_only_admins_manage_users():
    with _client(headers=auth_headers("officer")) as c:
        assert c.get("/api/auth/users").status_code == 403
    with _client(headers=auth_headers("admin")) as c:
        r = c.post("/api/auth/users", json={"email": "new.viewer@test.local", "password": "long-enough-pw", "role": "viewer"})
        assert r.status_code == 200 and r.json()["role"] == "viewer"
        assert c.post("/api/auth/users", json={"email": "new.viewer@test.local", "password": "long-enough-pw"}).status_code == 400
        assert any(u["email"] == "new.viewer@test.local" for u in c.get("/api/auth/users").json())
        uid = r.json()["user_id"]
        assert c.patch(f"/api/auth/users/{uid}", json={"active": False}).json()["active"] == 0


def test_audit_actor_is_the_signed_in_user(analyzed):
    tid = analyzed["tender_id"]
    with _client(headers=auth_headers("officer")) as c:
        finding = c.get(f"/api/tenders/{tid}/findings").json()[0]["finding_id"]
        r = c.post(f"/api/findings/{finding}/disposition",
                   json={"decision": "FURTHER_REVIEW", "auditor": "someone-else", "notes": "check"})
        assert r.status_code == 200, r.text
        entries = c.get(f"/api/tenders/{tid}/audit-log").json()["entries"]
    assert entries[-1]["actor"] == "officer@test.local"


def test_security_headers():
    with _client() as c:
        r = c.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
