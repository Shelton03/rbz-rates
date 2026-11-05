"""API keys, daily limits and usage counting for /v1/*, plus admin endpoints
the website uses to manage accounts and keys.

Two tiers:
  * anonymous: no key, ANON_DAILY requests per UTC day, counted per caller as
    a hash of (daily salt, day, IP) so raw IP addresses are never stored;
  * key holders: an API key from the website, KEY_DAILY requests per key per day.

Storage is a small async DB interface (all / run) with two backends: Cloudflare
D1 in the Worker, SQLite for local runs and tests. Both speak SQLite SQL, and
the schema lives in worker/migrations/.

Configuration (Worker vars/secrets, or environment variables locally):
  ADMIN_SECRET  shared secret the website sends as X-Admin-Secret to /admin/*
  ANON_SALT     secret mixed into the anonymous caller hash
  SITE_URL      the website, linked from 429 responses (where to get a key)
Locally, set RBZ_DB=<sqlite path> to switch the gate on; without it the API is open.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ANON_DAILY = 100
KEY_DAILY = 5000
MAX_KEYS = 3
KEY_PREFIX = "rbz_"
KEY_CACHE_SECONDS = 60      # a revoked key can keep working for up to this long per isolate
DEFAULT_SITE_URL = "https://rbz-rates.vercel.app"


# ---------------------------------------------------------------- storage backends

class SqliteDB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    async def all(self, sql: str, *args) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    async def run(self, sql: str, *args) -> None:
        self.conn.execute(sql, args)
        self.conn.commit()


class D1DB:
    """Cloudflare D1 through the Python Workers FFI."""

    def __init__(self, binding):
        self.db = binding

    def _stmt(self, sql: str, args: tuple):
        stmt = self.db.prepare(sql)
        return stmt.bind(*args) if args else stmt

    async def all(self, sql: str, *args) -> list[dict]:
        res = await self._stmt(sql, args).all()
        rows = res.results
        return rows.to_py() if hasattr(rows, "to_py") else list(rows)

    async def run(self, sql: str, *args) -> None:
        await self._stmt(sql, args).run()


class Config:
    def __init__(self, db, admin_secret: str | None, anon_salt: str, site_url: str | None = None):
        self.db, self.admin_secret, self.anon_salt = db, admin_secret, anon_salt
        self.site_url = (site_url or DEFAULT_SITE_URL).rstrip("/")


_local: Config | None = None
_worker: Config | None = None


def config(request: Request) -> Config | None:
    """The gate's configuration, or None when access control is off (plain local run)."""
    global _local, _worker
    env = request.scope.get("env")
    if env is not None:  # Cloudflare Workers
        if _worker is None:
            _worker = Config(D1DB(env.DB), _env_str(env, "ADMIN_SECRET") or None,
                             _env_str(env, "ANON_SALT"), _env_str(env, "SITE_URL") or None)
        return _worker
    path = os.environ.get("RBZ_DB")
    if not path:
        return None
    if _local is None or getattr(_local, "path", None) != path:
        _local = Config(SqliteDB(path), os.environ.get("ADMIN_SECRET"), os.environ.get("ANON_SALT", ""),
                        os.environ.get("SITE_URL"))
        _local.path = path
    return _local


def _env_str(env, name: str) -> str:
    value = getattr(env, name, None)
    return "" if value is None else str(value)


# ---------------------------------------------------------------- keys

def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


_key_cache: dict[str, tuple[str | None, float]] = {}


async def _key_id(db, key: str) -> str | None:
    h = hash_key(key)
    hit = _key_cache.get(h)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    rows = await db.all("SELECT id FROM api_keys WHERE hash = ? AND revoked_at IS NULL", h)
    key_id = rows[0]["id"] if rows else None
    _key_cache[h] = (key_id, time.monotonic() + KEY_CACHE_SECONDS)
    return key_id


def _presented_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.headers.get("x-api-key") or request.query_params.get("api_key") or None


def _client_ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.client.host if request.client else "")
            or "unknown")


def _endpoint(path: str) -> str:
    """'/v1/rates/2026-11-05' -> '/v1/rates' (so usage groups by endpoint, not by argument)."""
    return "/".join(path.split("/")[:3])


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _error(status: int, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status, headers=headers or {})


async def gate(request: Request, call_next):
    """Middleware: authenticate, enforce the daily limit, count the request."""
    if not request.url.path.startswith("/v1/") or request.method == "OPTIONS":
        return await call_next(request)
    cfg = config(request)
    if cfg is None:
        return await call_next(request)

    day = _today()
    key = _presented_key(request)
    if key:
        key_id = await _key_id(cfg.db, key)
        if key_id is None:
            return _error(401, "Invalid or revoked API key")
        subject, limit = f"key:{key_id}", KEY_DAILY
    else:
        digest = hashlib.sha256(f"{cfg.anon_salt}|{day}|{_client_ip(request)}".encode()).hexdigest()
        subject, limit = f"anon:{digest[:24]}", ANON_DAILY

    rows = await cfg.db.all("SELECT COALESCE(SUM(count), 0) AS n FROM usage WHERE day = ? AND subject = ?",
                            day, subject)
    used = int(rows[0]["n"]) if rows else 0
    reset = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
    headers = {"X-RateLimit-Limit": str(limit), "X-RateLimit-Reset": reset}
    if used >= limit:
        hint = "" if key else f" Get a free API key for {KEY_DAILY:,} requests/day: {cfg.site_url}/dashboard"
        return _error(429, f"Daily limit of {limit:,} requests reached; resets at 00:00 UTC.{hint}",
                      {**headers, "X-RateLimit-Remaining": "0"})

    response = await call_next(request)
    try:
        await cfg.db.run(
            "INSERT INTO usage (day, subject, endpoint, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT (day, subject, endpoint) DO UPDATE SET count = count + 1",
            day, subject, _endpoint(request.url.path))
        used += 1
    except Exception as e:  # counting must never take the API down
        print(f"usage count failed: {e}")
    response.headers.update({**headers, "X-RateLimit-Remaining": str(max(limit - used, 0))})
    return response


# ---------------------------------------------------------------- admin API (website only)

def require_admin(request: Request, x_admin_secret: str = Header(None)) -> Config:
    cfg = config(request)
    if cfg is None or not cfg.admin_secret:
        raise HTTPException(503, "Admin API not configured")
    if not x_admin_secret or not hmac.compare_digest(x_admin_secret, cfg.admin_secret):
        raise HTTPException(401, "Bad admin secret")
    return cfg


admin = APIRouter(prefix="/admin", include_in_schema=False)


class UserIn(BaseModel):
    login: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=320)


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@admin.put("/users/{user_id}")
async def upsert_user(user_id: str, body: UserIn, cfg: Config = Depends(require_admin)):
    await cfg.db.run(
        "INSERT INTO users (id, login, email, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET login = excluded.login, email = excluded.email",
        user_id, body.login, body.email or "", _now())
    return {"id": user_id}


@admin.get("/users/{user_id}/keys")
async def list_keys(user_id: str, cfg: Config = Depends(require_admin)):
    rows = await cfg.db.all(
        "SELECT k.id, k.name, k.prefix, k.created_at, k.revoked_at, "
        "  (SELECT MAX(day) FROM usage u WHERE u.subject = 'key:' || k.id) AS last_used, "
        "  (SELECT COALESCE(SUM(count), 0) FROM usage u WHERE u.subject = 'key:' || k.id AND u.day = ?) AS today "
        "FROM api_keys k WHERE k.user_id = ? ORDER BY k.created_at DESC", _today(), user_id)
    return {"keys": rows, "limit_per_key": KEY_DAILY, "max_keys": MAX_KEYS}


@admin.post("/users/{user_id}/keys", status_code=201)
async def create_key(user_id: str, body: KeyIn, cfg: Config = Depends(require_admin)):
    if not await cfg.db.all("SELECT id FROM users WHERE id = ?", user_id):
        raise HTTPException(404, "Unknown user")
    active = await cfg.db.all("SELECT COUNT(*) AS n FROM api_keys WHERE user_id = ? AND revoked_at IS NULL", user_id)
    if int(active[0]["n"]) >= MAX_KEYS:
        raise HTTPException(409, f"An account can have at most {MAX_KEYS} active keys; revoke one first")
    key, key_id, created = new_key(), uuid.uuid4().hex, _now()
    await cfg.db.run(
        "INSERT INTO api_keys (id, user_id, name, prefix, hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        key_id, user_id, body.name.strip(), key[:len(KEY_PREFIX) + 6], hash_key(key), created)
    # the only time the full key is ever returned
    return {"id": key_id, "name": body.name.strip(), "key": key, "created_at": created}


@admin.delete("/users/{user_id}/keys/{key_id}")
async def revoke_key(user_id: str, key_id: str, cfg: Config = Depends(require_admin)):
    rows = await cfg.db.all("SELECT hash FROM api_keys WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                            key_id, user_id)
    if not rows:
        raise HTTPException(404, "No such active key")
    await cfg.db.run("UPDATE api_keys SET revoked_at = ? WHERE id = ?", _now(), key_id)
    _key_cache.pop(rows[0]["hash"], None)
    return {"id": key_id, "revoked": True}


def _since(days: int) -> str:
    days = max(1, min(days, 90))
    return (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days - 1)).isoformat()


@admin.get("/users/{user_id}/usage")
async def user_usage(user_id: str, days: int = 30, cfg: Config = Depends(require_admin)):
    rows = await cfg.db.all(
        "SELECT u.day, substr(u.subject, 5) AS key_id, u.endpoint, u.count FROM usage u "
        "JOIN api_keys k ON u.subject = 'key:' || k.id "
        "WHERE k.user_id = ? AND u.day >= ? ORDER BY u.day", user_id, _since(days))
    return {"since": _since(days), "rows": rows}


@admin.get("/stats")
async def stats(days: int = 30, cfg: Config = Depends(require_admin)):
    """Site-wide usage for the owner's dashboard."""
    since = _since(days)
    by_day = await cfg.db.all(
        "SELECT day, "
        "  SUM(CASE WHEN subject LIKE 'key:%' THEN count ELSE 0 END) AS keyed, "
        "  SUM(CASE WHEN subject LIKE 'anon:%' THEN count ELSE 0 END) AS anonymous, "
        "  COUNT(DISTINCT subject) AS callers "
        "FROM usage WHERE day >= ? GROUP BY day ORDER BY day", since)
    by_endpoint = await cfg.db.all(
        "SELECT endpoint, SUM(count) AS count FROM usage WHERE day >= ? GROUP BY endpoint ORDER BY count DESC", since)
    top_keys = await cfg.db.all(
        "SELECT k.name, k.prefix, us.login, SUM(u.count) AS count FROM usage u "
        "JOIN api_keys k ON u.subject = 'key:' || k.id JOIN users us ON us.id = k.user_id "
        "WHERE u.day >= ? GROUP BY k.id ORDER BY count DESC LIMIT 10", since)
    totals = await cfg.db.all(
        "SELECT (SELECT COUNT(*) FROM users) AS users, "
        "(SELECT COUNT(*) FROM api_keys WHERE revoked_at IS NULL) AS active_keys")
    return {"since": since, "by_day": by_day, "by_endpoint": by_endpoint, "top_keys": top_keys, **totals[0]}
