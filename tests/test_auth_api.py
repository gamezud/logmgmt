"""POST /auth/login and GET /auth/me — success, failure, the anti-enumeration
timing mitigation (docs/DECISIONS.md #29), and token validation on /auth/me.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest

from backend.config import JWT_ALGORITHM, JWT_SECRET_KEY
from backend import security


def _expired_token(tenant: str = "test_tenant_auth") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "test_expired_user",
        "role": "admin",
        "tenant": tenant,
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def test_verify_password_or_dummy_runs_bcrypt_even_when_username_not_found(monkeypatch):
    """The fix for the login-timing side channel (docs/DECISIONS.md #29):
    when there's no real password_hash (username not found), this must
    still invoke bcrypt against the fixed dummy hash rather than skipping
    the bcrypt call entirely — that's what keeps this path's cost equal to
    the "found, wrong password" path. Spies on bcrypt.checkpw rather than
    measuring wall-clock time, which would be flaky.
    """
    calls = []
    original_checkpw = bcrypt.checkpw

    def spy_checkpw(password, hashed):
        calls.append(hashed)
        return original_checkpw(password, hashed)

    monkeypatch.setattr(security.bcrypt, "checkpw", spy_checkpw)

    result = security.verify_password_or_dummy("whatever-password", None)

    assert result is False
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_login_success_then_me(client, make_test_user):
    user = make_test_user("test_auth_admin", "correct-password", "admin", "test_tenant_auth")

    login_resp = await client.post(
        "/auth/login", json={"username": user["username"], "password": user["password"]}
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["token_type"] == "bearer"
    token = body["access_token"]

    me_resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json() == {"sub": "test_auth_admin", "role": "admin", "tenant": "test_tenant_auth"}


@pytest.mark.asyncio
async def test_login_wrong_password_is_401(client, make_test_user):
    user = make_test_user("test_auth_wrongpw", "correct-password", "viewer", "test_tenant_auth")

    resp = await client.post("/auth/login", json={"username": user["username"], "password": "nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_and_wrong_password_give_identical_response(client, make_test_user):
    """Same HTTP status and same response body for both failure modes —
    the message itself must not reveal whether the username exists (see
    docs/DECISIONS.md #29)."""
    user = make_test_user("test_auth_identical", "correct-password", "viewer", "test_tenant_auth")

    resp_missing = await client.post(
        "/auth/login", json={"username": "test_auth_does_not_exist", "password": "whatever"}
    )
    resp_wrong = await client.post(
        "/auth/login", json={"username": user["username"], "password": "wrong-password"}
    )

    assert resp_missing.status_code == 401
    assert resp_wrong.status_code == 401
    assert resp_missing.json() == resp_wrong.json()


@pytest.mark.asyncio
async def test_me_without_token_is_rejected(client):
    # This 401 comes from the HTTPBearer security scheme itself rejecting
    # the request before get_current_claims ever runs (no Authorization
    # header to even parse) — unlike the next two tests, where the header
    # IS present and 401 comes from get_current_claims' own
    # jwt.PyJWTError handling instead. Originally expected FastAPI's
    # HTTPBearer to default to 403 ("Not authenticated") for a missing
    # header, based on older documented behavior; running this against the
    # actual installed fastapi/starlette version showed 401 instead, which
    # is arguably more correct per HTTP semantics anyway (401 Unauthorized
    # for "no/invalid credentials supplied", 403 Forbidden for "credentials
    # were fine but you're not allowed") — so this test asserts the real,
    # verified behavior rather than the original assumption.
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_garbage_token_is_401(client):
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_token_is_401(client):
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {_expired_token()}"})
    assert resp.status_code == 401
