"""The alert engine: a standalone process (run via `python -m
alerting.engine`, like `ingest.syslog_server`/`ingest.batch_loader` —
docs/DECISIONS.md #22's "-m, never by path" rule applies here too),
separate from the FastAPI backend. See docs/DECISIONS.md for why this is
its own process rather than a background asyncio task inside
backend/main.py's lifespan, and where its tenant comes from with no JWT to
read one from.

One long-lived connection reused forever (like ingest/db.py's
connect_async — this process has no concurrent-request pool to manage,
unlike backend/db.py), re-evaluating every known tenant on a fixed
interval (ALERT_POLL_INTERVAL_SECONDS, default 30s — docs/DECISIONS.md on
why scheduled polling beats streaming at this scale).
"""
import asyncio
import logging
import os

import psycopg

from alerting.webhook import send_webhook
from ingest.db import connect_async

log = logging.getLogger(__name__)

RULE_TYPE = "failed_login_burst"

SET_TENANT_SQL = "SELECT set_config('app.tenant', %s, true)"

# No RLS on `users` (docs/DECISIONS.md #25) is exactly what makes this
# query possible with no tenant set yet — the same "queryable before any
# tenant is known" property login itself relies on. This is how the engine
# finds out which tenants exist at all, since every other tenant-scoped
# table (alert_rules, events, alerts) would return zero rows without
# app.tenant set first (RLS fail-closed, #7).
DISCOVER_TENANTS_SQL = "SELECT DISTINCT tenant FROM users ORDER BY tenant"

SELECT_RULE_SQL = """
    SELECT id, threshold, window_seconds, cooldown_seconds
    FROM alert_rules
    WHERE rule_type = %s AND enabled = true
"""

# Filters on ingested_at, NOT event_time — immune to a source device's
# clock skew (see docs/DECISIONS.md for the full event_time-vs-ingested_at
# write-up). window_start/window_end are MIN/MAX(event_time) of the
# matched rows: what actually gets reported to an analyst is the real-world
# incident span the source claims, even though that claim never influences
# whether this query matches the row at all.
DETECT_SQL = """
    SELECT
        src_ip,
        count(*)        AS event_count,
        min(event_time) AS window_start,
        max(event_time) AS window_end
    FROM events
    WHERE ingested_at >= now() - (%(window_seconds)s || ' seconds')::interval
      AND src_ip IS NOT NULL
      AND (event_type ILIKE '%%login%%' OR event_type ILIKE '%%logon%%')
      AND (event_type ILIKE '%%fail%%'  OR action ILIKE '%%fail%%')
    GROUP BY src_ip
    HAVING count(*) >= %(threshold)s
"""

# The comparison runs in Postgres, using Postgres's own now() — not the
# engine process's local clock — for the same "don't let a clock this
# system doesn't fully control decide correctness" reasoning as choosing
# ingested_at over event_time above. TRUE if this src_ip has never alerted
# for this rule, or its last alert is old enough that cooldown has elapsed.
PAST_COOLDOWN_SQL = """
    SELECT (
        max(triggered_at) IS NULL
        OR max(triggered_at) <= now() - (%(cooldown_seconds)s || ' seconds')::interval
    )
    FROM alerts
    WHERE tenant = %(tenant)s AND rule_id = %(rule_id)s AND src_ip = %(src_ip)s
"""

INSERT_ALERT_SQL = """
    INSERT INTO alerts (
        tenant, rule_id, src_ip, event_count, threshold, window_seconds,
        window_start, window_end
    ) VALUES (
        %(tenant)s, %(rule_id)s, %(src_ip)s, %(event_count)s, %(threshold)s,
        %(window_seconds)s, %(window_start)s, %(window_end)s
    )
    RETURNING id
"""

MARK_WEBHOOK_SENT_SQL = "UPDATE alerts SET webhook_sent_at = now() WHERE id = %s"


async def discover_tenants(conn: psycopg.AsyncConnection) -> list[str]:
    async with conn.cursor() as cur:
        await cur.execute(DISCOVER_TENANTS_SQL)
        rows = await cur.fetchall()
    return [tenant for (tenant,) in rows]


async def evaluate_tenant(conn: psycopg.AsyncConnection, tenant: str) -> None:
    """Evaluates the failed_login_burst rule for one tenant and inserts any
    alerts past cooldown. Everything here runs inside one transaction that
    sets app.tenant first, so RLS applies to every query exactly the way it
    does for a real HTTP request (backend/db.py's get_tenant_conn) or an
    ingest write (ingest/db.py) — the engine's own bugs can't cross tenants
    because the DB enforces it (alerts' WITH CHECK), not just because this
    function is written correctly.
    """
    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(SET_TENANT_SQL, (tenant,))

            await cur.execute(SELECT_RULE_SQL, (RULE_TYPE,))
            rule = await cur.fetchone()
            if rule is None:
                return
            rule_id, threshold, window_seconds, cooldown_seconds = rule

            await cur.execute(DETECT_SQL, {"window_seconds": window_seconds, "threshold": threshold})
            candidates = await cur.fetchall()

            for src_ip, event_count, window_start, window_end in candidates:
                await cur.execute(
                    PAST_COOLDOWN_SQL,
                    {"tenant": tenant, "rule_id": rule_id, "src_ip": src_ip, "cooldown_seconds": cooldown_seconds},
                )
                (past_cooldown,) = await cur.fetchone()
                if not past_cooldown:
                    continue

                await cur.execute(
                    INSERT_ALERT_SQL,
                    {
                        "tenant": tenant,
                        "rule_id": rule_id,
                        "src_ip": src_ip,
                        "event_count": event_count,
                        "threshold": threshold,
                        "window_seconds": window_seconds,
                        "window_start": window_start,
                        "window_end": window_end,
                    },
                )
                (alert_id,) = await cur.fetchone()
                log.info(
                    "alert fired: tenant=%r rule=%s src_ip=%s event_count=%s (threshold=%s)",
                    tenant, RULE_TYPE, src_ip, event_count, threshold,
                )

                # ALERT_WEBHOOK_URL unset is the expected default (no
                # webhook in .env.example), not an error path — the alert
                # is already durably inserted above regardless of whether
                # a webhook is configured or delivery succeeds.
                webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
                if not webhook_url:
                    log.debug("ALERT_WEBHOOK_URL not set — skipping webhook delivery for alert id=%s", alert_id)
                    continue

                delivered = await send_webhook(
                    webhook_url,
                    {
                        "alert_id": alert_id,
                        "tenant": tenant,
                        "rule_type": RULE_TYPE,
                        "src_ip": str(src_ip),
                        "event_count": event_count,
                        "threshold": threshold,
                        "window_seconds": window_seconds,
                        "window_start": window_start.isoformat(),
                        "window_end": window_end.isoformat(),
                    },
                )
                if delivered:
                    await cur.execute(MARK_WEBHOOK_SENT_SQL, (alert_id,))


async def run_once(conn: psycopg.AsyncConnection) -> None:
    """One scheduler tick: evaluate every known tenant. Each tenant's
    evaluation is isolated in its own try/except + rollback so one tenant's
    bad data or edge case can't leave the shared connection's transaction
    aborted and silently stop alerting for every other tenant on this same
    tick — Postgres refuses any further command on a connection whose
    transaction errored until it's rolled back.
    """
    for tenant in await discover_tenants(conn):
        try:
            await evaluate_tenant(conn, tenant)
        except Exception:
            log.exception("alert evaluation failed for tenant=%r — skipping it this tick", tenant)
            await conn.rollback()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    interval = int(os.environ.get("ALERT_POLL_INTERVAL_SECONDS", "30"))
    webhook_configured = bool(os.environ.get("ALERT_WEBHOOK_URL"))
    log.info("alert engine starting: poll interval=%ss, webhook=%s", interval, "configured" if webhook_configured else "not configured")

    conn = await connect_async()
    while True:
        try:
            await run_once(conn)
        except Exception:
            log.exception("run_once failed — will retry next tick")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
