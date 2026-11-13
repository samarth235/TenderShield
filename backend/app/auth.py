"""Authentication, sessions and role-based access control.

* Passwords are hashed with scrypt (stdlib) and a per-user salt.
* Sessions are short-lived signed JWTs (HS256) sent as ``Authorization: Bearer``. Because the
  browser never sends them automatically (no cookies), cross-site request forgery does not apply.
* Roles, lowest to highest: ``viewer`` (read only), ``officer`` (upload, run analysis, record
  decisions), ``admin`` (manage users). Every non-GET request needs at least ``officer``.
* The authenticated user is the actor recorded in the audit trail, whatever the request body says.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .config import get_settings
from .db import fetch_all, fetch_one, session

log = logging.getLogger(__name__)

Role = Literal["viewer", "officer", "admin"]
RANK = {"viewer": 0, "officer": 1, "admin": 2}
ALGORITHM = "HS256"
PUBLIC_PATHS = {"/api/health", "/api/ready", "/api/auth/login"}

_current_user: ContextVar[dict | None] = ContextVar("current_user", default=None)


def current_actor() -> str | None:
    """Email of the authenticated user handling this request, if any."""
    user = _current_user.get()
    return user["email"] if user else None


# --- Passwords ---------------------------------------------------------------------

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


# --- Users -------------------------------------------------------------------------

def _public(user: dict) -> dict:
    return {k: user[k] for k in ("user_id", "email", "name", "role", "active", "created_at")}


def create_user(conn: sqlite3.Connection, email: str, password: str, role: Role, name: str = "") -> dict:
    email = email.strip().lower()
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    if role not in RANK:
        raise ValueError(f"Unknown role {role}")
    if fetch_one(conn, "SELECT user_id FROM users WHERE email = ?", (email,)):
        raise ValueError(f"User {email} already exists")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO users (email, name, role, password_hash, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (email, name, role, hash_password(password), now),
    )
    return _public(fetch_one(conn, "SELECT * FROM users WHERE user_id = ?", (cur.lastrowid,)))


def bootstrap_admin() -> None:
    """Create the first admin from TS_ADMIN_EMAIL / TS_ADMIN_PASSWORD when no users exist."""
    s = get_settings()
    with session() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        if not (s.admin_email and s.admin_password):
            log.warning("No users exist. Set TS_ADMIN_EMAIL and TS_ADMIN_PASSWORD, or run "
                        "`python -m scripts.create_user`, to create the first administrator.")
            return
        create_user(conn, s.admin_email, s.admin_password, "admin", "Administrator")
        log.info("Created bootstrap administrator %s", s.admin_email)


# --- Tokens ------------------------------------------------------------------------

def issue_token(user: dict) -> tuple[str, int]:
    s = get_settings()
    ttl = s.session_minutes * 60
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user["user_id"]), "email": user["email"], "role": user["role"],
              "iat": now, "exp": now + timedelta(seconds=ttl)}
    return jwt.encode(claims, s.auth_secret, algorithm=ALGORITHM), ttl


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().auth_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(401, "Session expired, sign in again", headers={"WWW-Authenticate": "Bearer"}) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "Invalid session token", headers={"WWW-Authenticate": "Bearer"}) from exc


# --- Rate limiting (login) --------------------------------------------------------------

class RateLimiter:
    """Sliding-window limiter, in process memory (one instance per worker)."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise HTTPException(429, "Too many sign-in attempts, try again later", headers={"Retry-After": str(retry)})
            hits.append(now)


login_limiter = RateLimiter(limit=10, window_s=300)


# --- Dependencies ------------------------------------------------------------------

async def authenticate(request: Request) -> dict | None:
    """Global dependency: every /api route except PUBLIC_PATHS needs a valid session.

    Async on purpose: the context variable it sets is then visible to sync endpoints, which
    FastAPI runs in a thread pool with a copy of this context.
    """
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS or not request.url.path.startswith("/api"):
        return None
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    claims = _decode(token)
    with session() as conn:
        user = fetch_one(conn, "SELECT * FROM users WHERE user_id = ?", (int(claims["sub"]),))
    if user is None or not user["active"]:
        raise HTTPException(401, "Account disabled", headers={"WWW-Authenticate": "Bearer"})
    if request.method not in {"GET", "HEAD"} and RANK[user["role"]] < RANK["officer"]:
        raise HTTPException(403, "Your role is read-only")
    user = _public(user)
    _current_user.set(user)
    request.state.user = user
    return user


def require_role(role: Role):
    async def check(request: Request) -> dict:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
        if RANK[user["role"]] < RANK[role]:
            raise HTTPException(403, f"Requires the {role} role")
        return user
    return check


# --- Routes ------------------------------------------------------------------------

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class NewUser(BaseModel):
    email: str
    password: str = Field(..., min_length=10)
    role: Role = "viewer"
    name: str = ""


class UserUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = None


@router.post("/login")
def login(body: LoginRequest, request: Request) -> dict:
    login_limiter.check(request.client.host if request.client else "unknown")
    with session() as conn:
        user = fetch_one(conn, "SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),))
    # Same message for unknown user and wrong password, so accounts cannot be enumerated.
    if user is None or not user["active"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    token, ttl = issue_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl, "user": _public(user)}


@router.get("/me")
def me(request: Request) -> dict:
    return request.state.user


@router.get("/users", dependencies=[Depends(require_role("admin"))])
def list_users() -> list[dict]:
    with session() as conn:
        return [_public(u) for u in fetch_all(conn, "SELECT * FROM users ORDER BY user_id")]


@router.post("/users", dependencies=[Depends(require_role("admin"))])
def add_user(body: NewUser) -> dict:
    with session() as conn:
        try:
            return create_user(conn, body.email, body.password, body.role, body.name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.patch("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
def update_user(user_id: int, body: UserUpdate, request: Request) -> dict:
    if user_id == request.state.user["user_id"] and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "You cannot demote or disable your own account")
    with session() as conn:
        if fetch_one(conn, "SELECT user_id FROM users WHERE user_id = ?", (user_id,)) is None:
            raise HTTPException(404, f"Unknown user {user_id}")
        if body.role is not None:
            conn.execute("UPDATE users SET role = ? WHERE user_id = ?", (body.role, user_id))
        if body.active is not None:
            conn.execute("UPDATE users SET active = ? WHERE user_id = ?", (int(body.active), user_id))
        return _public(fetch_one(conn, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
