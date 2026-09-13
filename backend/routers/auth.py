"""POST /auth/login and GET /auth/me.

Login is the one request in this whole backend that runs before tenant is
known — it looks up `users` by username alone (globally unique — see
docs/DECISIONS.md and backend/db/init/05_users_schema.sql), which is why it
uses get_pooled_conn (no app.tenant to set yet) rather than get_tenant_conn.
"""
from fastapi import APIRouter, Depends, HTTPException, status
import psycopg

from backend.db import get_pooled_conn
from backend.deps import get_current_claims
from backend.schemas import LoginRequest, TokenResponse
from backend.security import TokenClaims, create_access_token, verify_password_or_dummy

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS_DETAIL = "invalid username or password"


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    conn: psycopg.AsyncConnection = Depends(get_pooled_conn),
) -> TokenResponse:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT password_hash, role, tenant FROM users WHERE username = %s",
            (body.username,),
        )
        row = await cur.fetchone()

    # verify_password_or_dummy always runs a bcrypt check, whether or not
    # `row` exists — see its docstring in backend/security.py for why: a
    # username-not-found response that skipped bcrypt entirely would be
    # measurably faster than a wrong-password response, letting an attacker
    # enumerate valid usernames purely from response timing.
    password_hash = row[0] if row is not None else None
    if not verify_password_or_dummy(body.password, password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS_DETAIL)

    _, role, tenant = row
    token = create_access_token(TokenClaims(sub=body.username, role=role, tenant=tenant))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=TokenClaims)
async def me(claims: TokenClaims = Depends(get_current_claims)) -> TokenClaims:
    # No DB query: the verified JWT payload already carries everything this
    # endpoint returns, and it's already been checked for authenticity by
    # get_current_claims — re-querying `users` here would only reintroduce a
    # DB round trip for data we already trust.
    return claims
