"""Storage-layer tests. These connect to a Postgres that must already be
running — run `make up` before `make test`; these tests don't start
docker-compose themselves (per CLAUDE.md rule 6: don't leave servers running).

Reads connection settings from the environment. `make test` gets these from
.env automatically (the Makefile exports it); running pytest directly
requires sourcing .env yourself first.
"""
import os

import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg_pool import AsyncConnectionPool

import backend.db as backend_db
from backend.config import dsn as backend_dsn
from backend.main import app
from backend.security import TokenClaims, create_access_token, hash_password
from ingest.db import connect_async


def _dsn(user: str, password: str) -> str:
    return (
        f"host=localhost port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'logmgmt')} "
        f"user={user} password={password}"
    )


@pytest.fixture
def admin_conn():
    """Superuser connection (POSTGRES_USER) — bypasses RLS entirely. Used for
    test setup/teardown and for partition-mechanics tests that aren't
    exercising RLS itself."""
    dsn = _dsn(os.environ["POSTGRES_USER"], os.environ["POSTGRES_PASSWORD"])
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_app_conn():
    """Factory for opening app_user connections — the same least-privilege
    role the backend will connect as, so RLS actually applies. A factory
    (not a single fixture) because RLS tests need more than one independent
    connection/session to simulate different tenants' requests."""
    dsn = _dsn(os.environ["APP_DB_USER"], os.environ["APP_DB_PASSWORD"])
    opened = []

    def _open():
        conn = psycopg.connect(dsn, autocommit=True)
        opened.append(conn)
        return conn

    yield _open

    for conn in opened:
        conn.close()


@pytest.fixture(autouse=True)
def _clean_test_rows(admin_conn):
    """Tests write rows tagged with names starting 'test_' — tenants in
    `events`/`alert_rules`/`alerts`, usernames in `users`. app_user has no
    DELETE grant on any of these (events/alerts are append-only by design;
    alert_rules only allows admin to UPDATE, not DELETE — see
    docs/DECISIONS.md; users has no delete path at all in this session), so
    cleanup runs as admin_conn, which bypasses RLS. `users.username` is
    UNIQUE, so leftover test users from a previous run would otherwise
    collide with a later run's insert — this must clean up both before AND
    after each test, not just after, in case a previous run crashed
    mid-test without reaching its own teardown. `alerts` is deleted before
    `alert_rules` since it has a FOREIGN KEY on (tenant, rule_id).
    """

    def _clean():
        with admin_conn.cursor() as cur:
            cur.execute(r"DELETE FROM alerts WHERE tenant LIKE 'test\_%' ESCAPE '\'")
            cur.execute(r"DELETE FROM alert_rules WHERE tenant LIKE 'test\_%' ESCAPE '\'")
            cur.execute(r"DELETE FROM events WHERE tenant LIKE 'test\_%' ESCAPE '\'")
            cur.execute(r"DELETE FROM users WHERE username LIKE 'test\_%' ESCAPE '\'")

    _clean()
    yield
    _clean()


@pytest_asyncio.fixture
async def client(monkeypatch):
    """httpx.AsyncClient driving the FastAPI app in-process via ASGI
    transport — no uvicorn process is started or left running (CLAUDE.md
    rule 6). Creates a fresh connection pool scoped to this one test
    (rather than reusing backend.db's module-level pool across tests) so
    the pool's lifetime never crosses pytest-asyncio's per-test event loop
    boundary, and monkeypatches it into backend.db.pool so the app's own
    dependencies (get_pooled_conn, get_tenant_conn — both read the `pool`
    name from backend.db's module globals at call time) pick it up. Same
    pattern as tests/test_db_pool_tenant_safety.py.
    """
    test_pool = AsyncConnectionPool(backend_dsn(), open=False)
    await test_pool.open()
    monkeypatch.setattr(backend_db, "pool", test_pool)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await test_pool.close()


@pytest_asyncio.fixture
async def engine_conn():
    """A plain app_user async connection with no tenant set yet — the same
    starting point alerting/engine.py's main() creates via
    ingest.db.connect_async(), reused across many evaluate_tenant() calls
    within one test. Used by tests/test_alert_engine.py to call
    alerting.engine.evaluate_tenant()/run_once() directly, without going
    through the HTTP layer (the engine has no HTTP surface of its own)."""
    conn = await connect_async()
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def mint_token():
    """Factory: build a JWT with arbitrary claims directly via
    backend.security.create_access_token, bypassing POST /auth/login and
    the `users` table entirely. For tests that only care about how a
    downstream endpoint (/ingest, /search, /stats/*) enforces role/tenant
    from an already-valid token — the login flow itself (looking up
    `users`, verifying the password hash) is covered separately by
    make_test_user + test_auth_api.py."""

    def _mint(sub: str, role: str, tenant: str) -> str:
        return create_access_token(TokenClaims(sub=sub, role=role, tenant=tenant))

    return _mint


@pytest.fixture
def make_test_user(admin_conn):
    """Factory: insert a real row into `users` (via admin_conn, which
    bypasses RLS — not that `users` has any, see docs/DECISIONS.md) with a
    real bcrypt hash of the given password, for tests that exercise the
    actual POST /auth/login flow rather than minting a token directly.
    Returns the plaintext username/password so the test can POST them.
    Tracks every created username and deletes it in its own teardown,
    independent of (and in addition to) the autouse _clean_test_rows safety
    net above — same factory-with-teardown shape as make_app_conn.
    """
    created_usernames = []

    def _create(username: str, password: str, role: str, tenant: str) -> dict:
        assert username.startswith("test_"), "test users must use a 'test_' username so cleanup can find them"
        with admin_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, tenant) VALUES (%s, %s, %s, %s)",
                (username, hash_password(password), role, tenant),
            )
        created_usernames.append(username)
        return {"username": username, "password": password, "role": role, "tenant": tenant}

    yield _create

    with admin_conn.cursor() as cur:
        for username in created_usernames:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
