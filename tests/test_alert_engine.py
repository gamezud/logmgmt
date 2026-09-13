"""alerting/engine.py's evaluate_tenant() — the core detection + cooldown +
webhook logic, called directly against a real Postgres connection (no HTTP
layer; the engine has none). See docs/DECISIONS.md for the design this
verifies: scheduled detection, per-(tenant, rule_id, src_ip) cooldown, and
—the case this file exists for— detecting on `ingested_at` (immune to a
source device's clock skew) while reporting `event_time` (the real-world
span the source claims).
"""
from datetime import datetime, timedelta, timezone

import pytest

from alerting.engine import evaluate_tenant


def _insert_alert_rule(admin_conn, tenant, *, threshold=5, window_seconds=300, cooldown_seconds=900):
    with admin_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alert_rules (tenant, rule_type, threshold, window_seconds, cooldown_seconds) "
            "VALUES (%s, 'failed_login_burst', %s, %s, %s) RETURNING id",
            (tenant, threshold, window_seconds, cooldown_seconds),
        )
        (rule_id,) = cur.fetchone()
    return rule_id


def _insert_matching_event(admin_conn, tenant, src_ip, *, event_time=None, ingested_at=None):
    """A row that matches the engine's failed-login heuristic
    (event_type contains both "login"/"logon" and "fail" — see
    docs/DECISIONS.md #39). event_time defaults to now(); ingested_at
    defaults to the column's own DEFAULT now() unless given explicitly."""
    event_time = event_time or datetime.now(timezone.utc)
    with admin_conn.cursor() as cur:
        if ingested_at is None:
            cur.execute(
                "INSERT INTO events (tenant, event_time, source, event_type, src_ip) "
                "VALUES (%s, %s, 'api', 'app_login_failed', %s)",
                (tenant, event_time, src_ip),
            )
        else:
            cur.execute(
                "INSERT INTO events (tenant, event_time, source, event_type, src_ip, ingested_at) "
                "VALUES (%s, %s, 'api', 'app_login_failed', %s, %s)",
                (tenant, event_time, src_ip, ingested_at),
            )


def _fetch_alerts(admin_conn, tenant):
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT src_ip, event_count, threshold, window_start, window_end, triggered_at "
            "FROM alerts WHERE tenant = %s ORDER BY triggered_at",
            (tenant,),
        )
        return cur.fetchall()


@pytest.mark.asyncio
async def test_fires_alert_when_threshold_met_within_window(engine_conn, admin_conn):
    tenant = "test_tenant_engine_basic"
    _insert_alert_rule(admin_conn, tenant, threshold=5, window_seconds=300)
    src_ip = "203.0.113.10"
    now = datetime.now(timezone.utc)
    for i in range(5):
        _insert_matching_event(admin_conn, tenant, src_ip, event_time=now - timedelta(seconds=i))

    await evaluate_tenant(engine_conn, tenant)

    rows = _fetch_alerts(admin_conn, tenant)
    assert len(rows) == 1
    matched_src_ip, event_count, threshold, window_start, window_end, _ = rows[0]
    assert str(matched_src_ip) == src_ip
    assert event_count == 5
    assert threshold == 5
    # window_start/window_end are MIN/MAX(event_time) of the matched rows.
    assert window_start <= window_end


@pytest.mark.asyncio
async def test_below_threshold_does_not_fire(engine_conn, admin_conn):
    tenant = "test_tenant_engine_below_threshold"
    _insert_alert_rule(admin_conn, tenant, threshold=5)
    src_ip = "203.0.113.11"
    for _ in range(4):
        _insert_matching_event(admin_conn, tenant, src_ip)

    await evaluate_tenant(engine_conn, tenant)

    assert _fetch_alerts(admin_conn, tenant) == []


@pytest.mark.asyncio
async def test_no_rule_configured_never_fires(engine_conn, admin_conn):
    tenant = "test_tenant_engine_no_rule"
    src_ip = "203.0.113.12"
    for _ in range(10):
        _insert_matching_event(admin_conn, tenant, src_ip)

    await evaluate_tenant(engine_conn, tenant)  # no alert_rules row at all for this tenant

    assert _fetch_alerts(admin_conn, tenant) == []


@pytest.mark.asyncio
async def test_cooldown_suppresses_duplicate_then_fires_again_after_it_elapses(engine_conn, admin_conn):
    tenant = "test_tenant_engine_cooldown"
    _insert_alert_rule(admin_conn, tenant, threshold=5, cooldown_seconds=900)
    src_ip = "203.0.113.13"
    for _ in range(5):
        _insert_matching_event(admin_conn, tenant, src_ip)

    await evaluate_tenant(engine_conn, tenant)
    assert len(_fetch_alerts(admin_conn, tenant)) == 1

    # Same ongoing burst, evaluated again immediately — still within the
    # 900s cooldown, so no second alert.
    await evaluate_tenant(engine_conn, tenant)
    assert len(_fetch_alerts(admin_conn, tenant)) == 1

    # Backdate the fired alert past its cooldown — simulates the next tick
    # that happens to land after cooldown_seconds have elapsed while the
    # burst (still present in `events`) is ongoing.
    with admin_conn.cursor() as cur:
        cur.execute(
            "UPDATE alerts SET triggered_at = now() - interval '901 seconds' WHERE tenant = %s",
            (tenant,),
        )

    await evaluate_tenant(engine_conn, tenant)
    assert len(_fetch_alerts(admin_conn, tenant)) == 2


@pytest.mark.asyncio
async def test_clock_skew_event_time_in_past_still_fires_and_is_reported_accurately(engine_conn, admin_conn):
    """The case docs/DECISIONS.md's event_time-vs-ingested_at decision
    exists for: a source device whose clock runs 2 hours behind. Detection
    must not be blinded by that (it uses ingested_at, not event_time), but
    the fired alert must still report the real (skewed) event_time span,
    not "now"."""
    tenant = "test_tenant_engine_clock_skew"
    _insert_alert_rule(admin_conn, tenant, threshold=5, window_seconds=300)
    src_ip = "203.0.113.14"
    skewed_time = datetime.now(timezone.utc) - timedelta(hours=2)
    for i in range(5):
        # event_time is skewed 2 hours into the past; ingested_at is left
        # at its DEFAULT now() — exactly what a real insert looks like when
        # the source's clock is wrong but this system's own clock isn't.
        _insert_matching_event(admin_conn, tenant, src_ip, event_time=skewed_time - timedelta(seconds=i))

    await evaluate_tenant(engine_conn, tenant)

    rows = _fetch_alerts(admin_conn, tenant)
    assert len(rows) == 1, "an event_time outside the window must not blind detection, which filters on ingested_at"
    _, _, _, window_start, window_end, triggered_at = rows[0]
    assert window_end <= skewed_time + timedelta(seconds=1)
    assert triggered_at - window_end >= timedelta(hours=1), "the alert must report the real, skewed event_time span, not now()"


@pytest.mark.asyncio
async def test_stale_ingested_at_is_not_counted(engine_conn, admin_conn):
    """The window's other edge: rows that arrived (ingested_at) longer ago
    than window_seconds must not count, even if event_time looks recent —
    confirms the ingested_at filter actually bounds the window rather than
    matching unconditionally."""
    tenant = "test_tenant_engine_stale_arrival"
    _insert_alert_rule(admin_conn, tenant, threshold=5, window_seconds=300)
    src_ip = "203.0.113.15"
    stale_ingested_at = datetime.now(timezone.utc) - timedelta(seconds=600)
    for _ in range(5):
        _insert_matching_event(admin_conn, tenant, src_ip, ingested_at=stale_ingested_at)

    await evaluate_tenant(engine_conn, tenant)

    assert _fetch_alerts(admin_conn, tenant) == []


@pytest.mark.asyncio
async def test_webhook_unset_still_fires_alert_without_raising(engine_conn, admin_conn, monkeypatch):
    """ALERT_WEBHOOK_URL unset is the expected local-dev default, not an
    error path (docs/DECISIONS.md) — evaluate_tenant must complete
    normally, still insert the alert, and simply leave webhook_sent_at
    NULL."""
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    tenant = "test_tenant_engine_no_webhook"
    _insert_alert_rule(admin_conn, tenant, threshold=5)
    src_ip = "203.0.113.16"
    for _ in range(5):
        _insert_matching_event(admin_conn, tenant, src_ip)

    await evaluate_tenant(engine_conn, tenant)  # must not raise

    with admin_conn.cursor() as cur:
        cur.execute("SELECT webhook_sent_at FROM alerts WHERE tenant = %s", (tenant,))
        (webhook_sent_at,) = cur.fetchone()
    assert webhook_sent_at is None
