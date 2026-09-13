"""Regression guard for backend/db.py's get_pooled_conn: it deliberately
yields a connection with NO app.tenant set (see its docstring — it exists
only for POST /ingest, which sets tenant itself via ingest.db.write_event_async).

This proves that reusing a pooled connection is safe even if get_pooled_conn
were ever misused to query a tenant-isolated table directly: a connection
that previously had app.tenant set to one tenant, inside a transaction that
has since committed, must NOT leak that tenant's rows to a later checkout
that never re-sets app.tenant. It must see zero rows (fail-closed, same as
any other unset-app.tenant case — docs/DECISIONS.md #7, #18-#20), not the
previous tenant's data.
"""
import pytest
from psycopg_pool import AsyncConnectionPool

import backend.db as backend_db
from backend.config import dsn


@pytest.mark.asyncio
async def test_pooled_conn_reuse_does_not_leak_previous_tenant(make_app_conn, monkeypatch):
    seed_conn = make_app_conn()
    with seed_conn.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_pool_a'")
        cur.execute(
            "INSERT INTO events (tenant, event_time, source, event_type) "
            "VALUES (%s, now(), %s, %s)",
            ("test_tenant_pool_a", "api", "pool_probe"),
        )

    # min_size=max_size=1 forces the second checkout below onto the exact
    # same physical connection as the first — the scenario this test exists
    # to cover.
    test_pool = AsyncConnectionPool(dsn(), min_size=1, max_size=1, open=False)
    await test_pool.open()
    monkeypatch.setattr(backend_db, "pool", test_pool)
    try:
        # First checkout: a legitimate request for tenant A that sets
        # app.tenant and commits — mirrors what get_tenant_conn does.
        async with test_pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(backend_db.SET_TENANT_SQL, ("test_tenant_pool_a",))
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT tenant FROM events WHERE tenant = %s",
                        ("test_tenant_pool_a",),
                    )
                    assert await cur.fetchall() != []

        # Second checkout via get_pooled_conn itself, with NO set_config —
        # same physical connection (pool size 1). Must not see tenant A's row.
        agen = backend_db.get_pooled_conn()
        conn = await agen.__anext__()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT tenant FROM events")
                assert await cur.fetchall() == []
        finally:
            await agen.aclose()
    finally:
        await test_pool.close()
