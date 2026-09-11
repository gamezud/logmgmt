"""Storage-layer tests. These connect to a Postgres that must already be
running — run `make up` before `make test`; these tests don't start
docker-compose themselves (per CLAUDE.md rule 6: don't leave servers running).

Reads connection settings from the environment. `make test` gets these from
.env automatically (the Makefile exports it); running pytest directly
requires sourcing .env yourself first.
"""
import os

import psycopg
import pytest


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
def _clean_test_tenant_rows(admin_conn):
    """Tests write rows tagged with tenant names starting 'test_'. app_user
    has no DELETE grant (events is append-only by design — see
    docs/DECISIONS.md), so cleanup runs as admin_conn, which bypasses RLS."""

    def _clean():
        with admin_conn.cursor() as cur:
            cur.execute(r"DELETE FROM events WHERE tenant LIKE 'test\_%' ESCAPE '\'")

    _clean()
    yield
    _clean()
