"""Password hashing (bcrypt) and JWT issuing/verification (PyJWT). See
docs/DECISIONS.md for why bcrypt over passlib/argon2, and PyJWT + HS256 +
HTTPBearer over python-jose / RS256 / OAuth2PasswordBearer.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from pydantic import BaseModel

from backend.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


# A fixed, precomputed bcrypt hash of an arbitrary password, used ONLY to
# absorb bcrypt's cost when POST /auth/login gets a username that doesn't
# exist. Without this, "username not found" (no bcrypt call at all) returns
# measurably faster than "username found, wrong password" (one bcrypt
# verify) — an attacker measuring response times could enumerate valid
# usernames without ever guessing a password. Running verify_password
# against this dummy hash on the not-found path makes both paths pay the
# same bcrypt cost. This is a mitigation, not a formal constant-time
# guarantee (network jitter etc. still introduce some variance) — see
# docs/DECISIONS.md.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-safety-only")


def verify_password_or_dummy(plain_password: str, password_hash: str | None) -> bool:
    """Like verify_password, but if password_hash is None (username not
    found), still runs a bcrypt verify against a fixed dummy hash and
    returns False — so the caller's response time doesn't reveal whether
    the username exists."""
    if password_hash is None:
        verify_password(plain_password, _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(plain_password, password_hash)


class TokenClaims(BaseModel):
    sub: str
    role: str
    tenant: str


def create_access_token(claims: TokenClaims) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **claims.model_dump(),
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims:
    """Raises jwt.PyJWTError (or a subclass) on any invalid/expired/
    wrongly-signed token — callers (backend/deps.py) turn that into a 401."""
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    return TokenClaims(sub=payload["sub"], role=payload["role"], tenant=payload["tenant"])
