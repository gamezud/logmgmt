"""FastAPI dependencies for authentication/authorization. Every endpoint in
this backend depends (directly or via backend/db.py's get_tenant_conn) on
get_current_claims — it's the one place a request's tenant/role are
established, from the verified JWT, never from anything the client sent
elsewhere in the request. See docs/DECISIONS.md.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from backend.security import TokenClaims, decode_access_token

# HTTPBearer, not OAuth2PasswordBearer: login here is plain JSON, not an
# OAuth2 password-grant form body, so HTTPBearer reflects what's actually
# implemented instead of implying an OAuth2 flow that doesn't exist. See
# docs/DECISIONS.md.
_bearer_scheme = HTTPBearer()


def get_current_claims(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> TokenClaims:
    try:
        return decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from exc


def require_role(role: str):
    """Returns a dependency that 403s unless the caller's verified role
    matches exactly. Used as Depends(require_role("admin")) on POST /ingest
    (admin-only — see docs/DECISIONS.md for the accepted risk of a machine
    credential holding admin rights, and why a third write-only 'ingestor'
    role is deliberately not implemented in this session)."""

    def _check(claims: TokenClaims = Depends(get_current_claims)) -> TokenClaims:
        if claims.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role={role}",
            )
        return claims

    return _check
