"""Shared DB write path for every ingest entrypoint (syslog server, batch
loader). Always connects as APP_DB_USER (app_user), never POSTGRES_USER —
see backend/db/init/01_roles.sh / 02_schema.sql for why. Every write sets
app.tenant inside the same transaction as the INSERT, which is what makes
the RLS policy on `events` actually apply (see docs/DECISIONS.md #7).

IMPORTANT: app.tenant is set via `SELECT set_config('app.tenant', %s, true)`,
NOT `SET LOCAL app.tenant = %s` — Postgres's SET statement does not accept
bind parameters at all (verified against postgres:16: it raises a syntax
error on the placeholder), the same class of limitation already hit with
`FOR VALUES FROM (%s)` in the partition-maintenance SQL. set_config() is a
normal function call, so it takes a bind parameter like any other query —
this keeps the tenant value safely parameterized instead of string-
interpolated into the SQL text (which would open SQL injection via tenant).
Its third argument, `true`, is is_local, which is what makes it behave like
SET LOCAL: scoped to the current transaction only, reverting once it ends
(to '', not NULL — see backend/db/init/02_schema.sql's tenant CHECK and
docs/DECISIONS.md #18-#20 for why that's still safe on a reused connection).
"""
import os

import psycopg
from psycopg.types.json import Jsonb

from ingest.models import NormalizedEvent

INSERT_SQL = """
INSERT INTO events (
    tenant, event_time, source, vendor, product, event_type, event_subtype,
    severity, action, src_ip, src_port, dst_ip, dst_port, protocol,
    "user", host, process, url, http_method, status_code, rule_name, rule_id,
    cloud_account_id, cloud_region, cloud_service, raw, _tags
) VALUES (
    %(tenant)s, %(event_time)s, %(source)s, %(vendor)s, %(product)s, %(event_type)s, %(event_subtype)s,
    %(severity)s, %(action)s, %(src_ip)s, %(src_port)s, %(dst_ip)s, %(dst_port)s, %(protocol)s,
    %(user)s, %(host)s, %(process)s, %(url)s, %(http_method)s, %(status_code)s, %(rule_name)s, %(rule_id)s,
    %(cloud_account_id)s, %(cloud_region)s, %(cloud_service)s, %(raw)s, %(tags)s
)
"""
# The SQL column list says `_tags`; the VALUES placeholder is %(tags)s
# because psycopg's named params key off the params dict (below), which is
# keyed by the NormalizedEvent field name `tags`, not the DB column name.

SET_TENANT_SQL = "SELECT set_config('app.tenant', %s, true)"


def _params(event: NormalizedEvent) -> dict:
    data = event.model_dump()
    data["raw"] = Jsonb(data["raw"])
    return data


def _dsn() -> str:
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['APP_DB_USER']} password={os.environ['APP_DB_PASSWORD']}"
    )


def connect_sync() -> psycopg.Connection:
    return psycopg.connect(_dsn(), autocommit=True)


async def connect_async() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(_dsn(), autocommit=True)


def write_event_sync(conn: psycopg.Connection, event: NormalizedEvent) -> None:
    # set_config(..., true) only takes effect inside an active transaction —
    # on an autocommit connection it silently no-ops outside conn.transaction().
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(SET_TENANT_SQL, (event.tenant,))
            cur.execute(INSERT_SQL, _params(event))


async def write_event_async(conn: psycopg.AsyncConnection, event: NormalizedEvent) -> None:
    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(SET_TENANT_SQL, (event.tenant,))
            await cur.execute(INSERT_SQL, _params(event))
