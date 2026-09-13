"""Per-request Postgres access for the FastAPI backend.

Unlike ingest/db.py, which opens one long-lived connection per process (a
syslog listener is one tenant for its whole life), this backend serves
concurrent HTTP requests from many tenants in one process, so it needs a
connection pool. See docs/DECISIONS.md for the full explanation of how the
pool and per-request `set_config('app.tenant', ..., true)` interact without
ever leaking one request's tenant into another request that later reuses
the same physical connection.
"""
from collections.abc import AsyncIterator

import psycopg
from fastapi import Depends
from psycopg_pool import AsyncConnectionPool

from backend.config import dsn
from backend.deps import get_current_claims
from backend.security import TokenClaims

SET_TENANT_SQL = "SELECT set_config('app.tenant', %s, true)"

# open=False: the pool is opened explicitly from main.py's lifespan on
# startup and closed on shutdown, so its lifecycle is tied to the app's own
# lifecycle rather than to whichever request happens to run first.
pool = AsyncConnectionPool(dsn(), open=False)


async def get_pooled_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    """A bare pooled connection with NO tenant set — app.tenant on it is
    whatever a previous, unrelated request left behind (almost certainly
    '', since transactions using set_config's is_local form reset it back
    to '' when they end — see docs/DECISIONS.md #18-#20), never a value
    this dependency itself set.

    DO NOT use this for any endpoint that queries a tenant-isolated table
    (events, or anything else with the tenant_isolation RLS policy). If you
    need to run a SELECT/INSERT against such a table, use get_tenant_conn
    instead, which sets app.tenant from the verified JWT claim before
    yielding.

    The ONLY caller in this codebase is POST /ingest, and only because it
    immediately hands the connection to ingest.db.write_event_async, which
    does its own set_config + insert inside one transaction per call — it
    never runs a query on this connection before setting tenant itself.
    Regression test: tests/test_db_pool_tenant_safety.py proves that
    querying `events` through a connection this function yields, without
    ever calling set_config on it, returns zero rows rather than a previous
    tenant's data — fail-closed the same way an unset app.tenant always
    does (docs/DECISIONS.md #7), not a leak.
    """
    async with pool.connection() as conn:
        yield conn


async def get_tenant_conn(
    claims: TokenClaims = Depends(get_current_claims),
) -> AsyncIterator[psycopg.AsyncConnection]:
    """Checks out one connection exclusively for this request, sets
    app.tenant from the verified JWT claim inside a transaction that stays
    open for the whole request, and returns the connection to the pool once
    the request finishes.

    Two things combine to make this safe against cross-request tenant
    leakage even though the pool reuses physical connections:
    1. pool.connection() gives this request exclusive use of the connection
       for the entire `async with` block — no two requests ever run queries
       on it concurrently.
    2. Every request using this dependency sets its own tenant as the first
       statement of its own transaction, before running anything else — so
       it never depends on whatever a previous, unrelated request left
       behind on this same physical connection.

    The transaction intentionally stays open for the whole request (yield
    happens inside `async with conn.transaction()`), not just for the
    set_config call — see docs/DECISIONS.md for why (set_config's is_local
    scoping requires an open transaction for as long as anything depending
    on it runs) and the accepted tradeoff (a slow request holds a pool slot
    for its full duration, not just its query time).

    Used by every endpoint that runs ordinary SELECT queries against
    tenant-isolated tables: /search, /stats/top, /stats/timeline.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute(SET_TENANT_SQL, (claims.tenant,))
            yield conn
