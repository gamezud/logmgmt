"""DB-backed tests for ingest/db.py's write path against real RLS.

These specifically guard the set_config-based tenant scoping (see
docs/DECISIONS.md #18-#20): a long-lived connection reused across tenants
(exactly what ingest/syslog_server.py does) must never leak one tenant's
rows into a query made under a different — or absent — tenant setting.
"""
from datetime import datetime, timezone

import psycopg
import pytest

from ingest.db import connect_async, write_event_async, write_event_sync
from ingest.models import NormalizedEvent


def _event(tenant: str) -> NormalizedEvent:
    return NormalizedEvent(
        tenant=tenant,
        event_time=datetime.now(timezone.utc),
        source="api",
        event_type="roundtrip_test",
        raw={},
    )


def test_write_then_read_back_under_same_tenant(make_app_conn):
    conn = make_app_conn()
    write_event_sync(conn, _event("test_rw_a"))

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant', %s, true)", ("test_rw_a",))
            cur.execute("SELECT tenant FROM events WHERE tenant = 'test_rw_a'")
            assert cur.fetchall() == [("test_rw_a",)]


def test_no_leak_on_same_connection_after_transaction_ends(make_app_conn):
    """The critical scenario for a persistent ingest connection: after
    write_event_sync's transaction commits, app.tenant resets to '' (not
    NULL — a Postgres quirk for custom GUC placeholders, verified against
    postgres:16). A bare query on the same connection that forgets to
    re-set app.tenant must still see zero rows, not every tenant's data.
    """
    conn = make_app_conn()
    write_event_sync(conn, _event("test_leak_a"))

    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('app.tenant', true)")
        # Confirm the precondition this test exists to guard: the setting
        # really did reset to '', not NULL, not the old tenant value.
        assert cur.fetchone() == ("",)

        cur.execute("SELECT tenant FROM events WHERE tenant = 'test_leak_a'")
        assert cur.fetchall() == []


def test_sequential_tenants_isolated_on_same_connection(make_app_conn):
    """Still on the SAME connection as above: writing a second tenant right
    after must only ever see that second tenant's rows, never the first's.
    """
    conn = make_app_conn()
    write_event_sync(conn, _event("test_leak_a"))
    write_event_sync(conn, _event("test_leak_b"))

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant', %s, true)", ("test_leak_b",))
            cur.execute(
                "SELECT tenant FROM events WHERE tenant IN ('test_leak_a', 'test_leak_b')"
            )
            assert cur.fetchall() == [("test_leak_b",)]


def test_empty_string_tenant_rejected_by_check_constraint(admin_conn):
    """The RLS policy's fail-closed behavior for a reset ('') app.tenant
    setting depends on no real tenant ever being '' — this must be an
    enforced DB invariant (events.tenant CHECK (tenant <> '')), not a
    coincidence. admin_conn bypasses RLS (it's the superuser) but not CHECK
    constraints, so this proves the constraint itself, independent of RLS.
    """
    with pytest.raises(psycopg.errors.CheckViolation):
        with admin_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (tenant, event_time, source, event_type, raw, _tags)
                VALUES ('', now(), 'api', 'should_fail', '{}'::jsonb, '{}'::text[])
                """
            )
    admin_conn.rollback()


@pytest.mark.asyncio
async def test_write_event_async_under_rls():
    """The async path (used by the syslog server) must apply the same
    set_config-based scoping as the sync path. Uses connect_async() itself
    — not a hand-rolled DSN — so this actually exercises the shipped code
    path and stays correct if _dsn() ever changes.
    """
    conn = await connect_async()
    try:
        await write_event_async(conn, _event("test_async_a"))
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute("SELECT set_config('app.tenant', %s, true)", ("test_async_a",))
                await cur.execute("SELECT tenant FROM events WHERE tenant = 'test_async_a'")
                assert await cur.fetchall() == [("test_async_a",)]
    finally:
        await conn.close()
