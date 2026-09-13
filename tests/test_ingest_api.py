"""POST /ingest — admin-only, and tenant always comes from the JWT claim,
never the request body, even when the body itself carries a "tenant" field
(see docs/DECISIONS.md #23, #24).
"""
import pytest


@pytest.mark.asyncio
async def test_admin_can_ingest(client, mint_token, admin_conn):
    token = mint_token("test_ingest_admin", "admin", "test_tenant_ingest")
    body = {
        "source": "api",
        "event_type": "app_login_failed",
        "user": "alice",
        "ip": "203.0.113.7",
        "@timestamp": "2025-08-20T07:20:00Z",
    }

    resp = await client.post("/ingest", json=body, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    assert resp.json()["tenant"] == "test_tenant_ingest"
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT tenant, event_type FROM events WHERE tenant = %s",
            ("test_tenant_ingest",),
        )
        assert cur.fetchall() == [("test_tenant_ingest", "app_login_failed")]


@pytest.mark.asyncio
async def test_viewer_cannot_ingest(client, mint_token):
    token = mint_token("test_ingest_viewer", "viewer", "test_tenant_ingest")

    resp = await client.post(
        "/ingest",
        json={"source": "api", "event_type": "probe", "@timestamp": "2025-08-20T07:20:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_client_supplied_tenant_in_body_is_ignored(client, mint_token, admin_conn):
    """The assignment's own POST /ingest samples (§4.3-§4.7) embed a
    "tenant" field in the body — this must never be trusted. The stored
    tenant is always the caller's JWT claim (here: test_tenant_real), never
    the body's test_tenant_fake."""
    token = mint_token("test_ingest_admin2", "admin", "test_tenant_real")
    body = {
        "tenant": "test_tenant_fake",
        "source": "api",
        "event_type": "tenant_override_probe",
        "@timestamp": "2025-08-20T07:20:00Z",
    }

    resp = await client.post("/ingest", json=body, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    assert resp.json()["tenant"] == "test_tenant_real"
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT tenant FROM events WHERE event_type = %s",
            ("tenant_override_probe",),
        )
        assert cur.fetchall() == [("test_tenant_real",)]
