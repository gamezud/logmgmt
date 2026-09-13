"""GET/POST /alert-rules and PATCH /alert-rules/{id} — role enforcement
(admin manages, viewer reads only), tenant isolation via RLS, and the
UNIQUE(tenant, rule_type) conflict path. See docs/DECISIONS.md.
"""
import pytest


@pytest.mark.asyncio
async def test_admin_can_create_rule_and_viewer_can_read_it(client, mint_token):
    tenant = "test_tenant_rules_create"
    admin_token = mint_token("test_admin", "admin", tenant)
    viewer_token = mint_token("test_viewer", "viewer", tenant)

    create_resp = await client.post(
        "/alert-rules",
        json={"threshold": 3, "window_seconds": 60, "cooldown_seconds": 120},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["rule_type"] == "failed_login_burst"
    assert body["threshold"] == 3
    assert body["enabled"] is True

    list_resp = await client.get("/alert-rules", headers={"Authorization": f"Bearer {viewer_token}"})
    assert list_resp.status_code == 200
    rules = list_resp.json()
    assert len(rules) == 1
    assert rules[0]["id"] == body["id"]


@pytest.mark.asyncio
async def test_viewer_cannot_create_or_patch_rule(client, mint_token):
    tenant = "test_tenant_rules_viewer_forbidden"
    viewer_token = mint_token("test_viewer", "viewer", tenant)

    create_resp = await client.post(
        "/alert-rules", json={}, headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert create_resp.status_code == 403

    patch_resp = await client.patch(
        "/alert-rules/1", json={"enabled": False}, headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_rule_type_conflicts(client, mint_token):
    tenant = "test_tenant_rules_dup"
    admin_token = mint_token("test_admin", "admin", tenant)
    headers = {"Authorization": f"Bearer {admin_token}"}

    first = await client.post("/alert-rules", json={}, headers=headers)
    assert first.status_code == 201

    second = await client.post("/alert-rules", json={}, headers=headers)
    assert second.status_code == 409
    assert "PATCH" in second.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_patch_rule(client, mint_token):
    tenant = "test_tenant_rules_patch"
    admin_token = mint_token("test_admin", "admin", tenant)
    headers = {"Authorization": f"Bearer {admin_token}"}

    created = await client.post("/alert-rules", json={"threshold": 5}, headers=headers)
    rule_id = created.json()["id"]

    patched = await client.patch(f"/alert-rules/{rule_id}", json={"threshold": 10, "enabled": False}, headers=headers)
    assert patched.status_code == 200
    body = patched.json()
    assert body["threshold"] == 10
    assert body["enabled"] is False
    # window_seconds/cooldown_seconds untouched by the partial update.
    assert body["window_seconds"] == 300


@pytest.mark.asyncio
async def test_patch_rule_from_another_tenant_is_404(client, mint_token):
    tenant_a = "test_tenant_rules_isolation_a"
    tenant_b = "test_tenant_rules_isolation_b"
    admin_a = mint_token("test_admin_a", "admin", tenant_a)
    admin_b = mint_token("test_admin_b", "admin", tenant_b)

    created = await client.post("/alert-rules", json={}, headers={"Authorization": f"Bearer {admin_a}"})
    rule_id = created.json()["id"]

    # RLS confines the UPDATE to tenant_a's own rows (docs/DECISIONS.md
    # #6-#8) — tenant_b's admin gets 404, not tenant_a's data, and not a
    # different error that would reveal the row exists under another tenant.
    resp = await client.patch(
        f"/alert-rules/{rule_id}", json={"enabled": False}, headers={"Authorization": f"Bearer {admin_b}"}
    )
    assert resp.status_code == 404

    list_resp = await client.get("/alert-rules", headers={"Authorization": f"Bearer {admin_b}"})
    assert list_resp.json() == []
