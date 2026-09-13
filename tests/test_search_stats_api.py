"""GET /search and GET /stats/* — tenant isolation over HTTP (via
get_tenant_conn/RLS), filters, pagination, response shape, and aggregations.
"""
from datetime import datetime, timedelta, timezone

import pytest


def _insert_event(admin_conn, tenant, event_type, *, user=None, src_ip=None, event_time=None):
    """Inserts directly as admin_conn (bypasses RLS) — these tests are about
    what /search and /stats/* return, not about write-path RLS (already
    covered by tests/test_rls_tenant_isolation.py)."""
    with admin_conn.cursor() as cur:
        if event_time is None:
            cur.execute(
                "INSERT INTO events (tenant, event_time, source, event_type, \"user\", src_ip) "
                "VALUES (%s, now(), %s, %s, %s, %s)",
                (tenant, "api", event_type, user, src_ip),
            )
        else:
            cur.execute(
                "INSERT INTO events (tenant, event_time, source, event_type, \"user\", src_ip) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (tenant, event_time, "api", event_type, user, src_ip),
            )


@pytest.mark.asyncio
async def test_search_isolates_tenants(client, mint_token, admin_conn):
    _insert_event(admin_conn, "test_tenant_search_a", "login_ok")
    _insert_event(admin_conn, "test_tenant_search_b", "login_ok")
    token_a = mint_token("test_viewer_a", "viewer", "test_tenant_search_a")

    resp = await client.get("/search", headers={"Authorization": f"Bearer {token_a}"})

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["tenant"] == "test_tenant_search_a"


@pytest.mark.asyncio
async def test_search_response_uses_timestamp_alias_not_event_time(client, mint_token, admin_conn):
    """populate_by_name=True (backend/schemas.py) lets SearchResultItem be
    CONSTRUCTED with the field's real name (event_time), but that says
    nothing about what key name gets SERIALIZED into the outgoing JSON —
    FastAPI's response_model serialization must still use the alias
    ("@timestamp") for the assignment's common schema to actually be
    honored on the wire. Construction and serialization are two separate
    guarantees; this asserts the outbound one specifically."""
    _insert_event(admin_conn, "test_tenant_search_alias", "login_ok")
    token = mint_token("test_viewer_alias", "viewer", "test_tenant_search_alias")

    resp = await client.get("/search", headers={"Authorization": f"Bearer {token}"})

    item = resp.json()["items"][0]
    assert "@timestamp" in item
    assert "event_time" not in item


@pytest.mark.asyncio
async def test_search_filters_by_event_type(client, mint_token, admin_conn):
    _insert_event(admin_conn, "test_tenant_search_filter", "login_ok")
    _insert_event(admin_conn, "test_tenant_search_filter", "login_failed")
    token = mint_token("test_viewer_filter", "viewer", "test_tenant_search_filter")

    resp = await client.get(
        "/search", params={"event_type": "login_failed"}, headers={"Authorization": f"Bearer {token}"}
    )

    items = resp.json()["items"]
    assert [item["event_type"] for item in items] == ["login_failed"]


@pytest.mark.asyncio
async def test_search_pagination_has_more(client, mint_token, admin_conn):
    tenant = "test_tenant_search_page"
    base = datetime.now(timezone.utc)
    for i in range(3):
        _insert_event(admin_conn, tenant, f"event_{i}", event_time=base + timedelta(seconds=i))
    token = mint_token("test_viewer_page", "viewer", tenant)
    headers = {"Authorization": f"Bearer {token}"}

    first_page = await client.get("/search", params={"limit": 2}, headers=headers)
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["has_more"] is True

    second_page = await client.get("/search", params={"limit": 2, "offset": 2}, headers=headers)
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["has_more"] is False


@pytest.mark.asyncio
async def test_stats_top(client, mint_token, admin_conn):
    tenant = "test_tenant_stats_top"
    _insert_event(admin_conn, tenant, "login_ok", user="alice")
    _insert_event(admin_conn, tenant, "login_ok", user="alice")
    _insert_event(admin_conn, tenant, "login_ok", user="bob")
    token = mint_token("test_viewer_top", "viewer", tenant)

    resp = await client.get("/stats/top", params={"field": "user"}, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()[0] == {"value": "alice", "count": 2}


@pytest.mark.asyncio
async def test_stats_timeline(client, mint_token, admin_conn):
    tenant = "test_tenant_stats_timeline"
    _insert_event(admin_conn, tenant, "login_ok")
    token = mint_token("test_viewer_timeline", "viewer", tenant)

    resp = await client.get(
        "/stats/timeline", params={"interval": "day"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["count"] == 1
