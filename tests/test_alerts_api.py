"""GET /alerts — tenant isolation (via get_tenant_conn/RLS, same as
tests/test_search_stats_api.py's pattern for /search) and pagination.
"""
from datetime import datetime, timedelta, timezone

import pytest


def _insert_alert_rule(admin_conn, tenant: str) -> int:
    """Inserts directly as admin_conn (bypasses RLS) — these tests are about
    what GET /alerts returns, not about the rule-management endpoints
    (covered separately by tests/test_alert_rules_api.py)."""
    with admin_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alert_rules (tenant, rule_type) VALUES (%s, 'failed_login_burst') RETURNING id",
            (tenant,),
        )
        (rule_id,) = cur.fetchone()
    return rule_id


def _insert_alert(admin_conn, tenant: str, rule_id: int, *, src_ip="203.0.113.7", triggered_at=None):
    now = datetime.now(timezone.utc)
    with admin_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts (
                tenant, rule_id, src_ip, event_count, threshold, window_seconds,
                window_start, window_end, triggered_at
            ) VALUES (%s, %s, %s, 5, 5, 300, %s, %s, %s)
            """,
            (tenant, rule_id, src_ip, now - timedelta(minutes=5), now, triggered_at or now),
        )


@pytest.mark.asyncio
async def test_alerts_isolates_tenants(client, mint_token, admin_conn):
    tenant_a = "test_tenant_alerts_a"
    tenant_b = "test_tenant_alerts_b"
    rule_a = _insert_alert_rule(admin_conn, tenant_a)
    rule_b = _insert_alert_rule(admin_conn, tenant_b)
    _insert_alert(admin_conn, tenant_a, rule_a)
    _insert_alert(admin_conn, tenant_b, rule_b)

    token_a = mint_token("test_viewer_a", "viewer", tenant_a)
    resp = await client.get("/alerts", headers={"Authorization": f"Bearer {token_a}"})

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["tenant"] == tenant_a


@pytest.mark.asyncio
async def test_alerts_available_to_viewer_and_admin(client, mint_token, admin_conn):
    tenant = "test_tenant_alerts_roles"
    rule_id = _insert_alert_rule(admin_conn, tenant)
    _insert_alert(admin_conn, tenant, rule_id)

    for role in ("admin", "viewer"):
        token = mint_token(f"test_{role}", role, tenant)
        resp = await client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_alerts_pagination_has_more(client, mint_token, admin_conn):
    tenant = "test_tenant_alerts_page"
    rule_id = _insert_alert_rule(admin_conn, tenant)
    base = datetime.now(timezone.utc)
    for i in range(3):
        _insert_alert(admin_conn, tenant, rule_id, triggered_at=base + timedelta(seconds=i))
    token = mint_token("test_viewer_page", "viewer", tenant)
    headers = {"Authorization": f"Bearer {token}"}

    first_page = await client.get("/alerts", params={"limit": 2}, headers=headers)
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["has_more"] is True

    second_page = await client.get("/alerts", params={"limit": 2, "offset": 2}, headers=headers)
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["has_more"] is False
