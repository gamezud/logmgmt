"""Backend configuration, read once from the environment at import time.

Mirrors ingest/db.py's env-var names (APP_DB_USER/APP_DB_PASSWORD, never
POSTGRES_USER — see docs/DECISIONS.md) and adds the JWT settings this
session introduces.

JWT_SECRET_KEY gets a fail-fast check, deliberately run here at *import*
time rather than deferred to the first login/token-verify call: this file
(and .env.example, which is committed to the repo) ship a placeholder value
for JWT_SECRET_KEY. If a real deployment ever ran with that placeholder
still in place, anyone who read the public repo could mint a validly-signed
JWT with any tenant/role they want — which makes every Row-Level Security
policy in this system meaningless, since RLS's safety depends entirely on
app.tenant coming from a signature only the server can produce (see
docs/DECISIONS.md). Failing at import time means a misconfigured deployment
never accepts a single request; failing lazily on first use would let it
run for a while looking fine.
"""
import os

PLACEHOLDER_JWT_SECRET_KEY = "changeme-generate-a-real-secret"


def validate_jwt_secret(secret: str | None) -> str:
    """Raises RuntimeError if `secret` is missing/empty or still the
    committed .env.example placeholder. Kept as its own function (not just
    bare module-level code) so tests can call it directly with different
    inputs, without needing importlib.reload tricks to re-trigger it."""
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Copy .env.example to .env and set "
            "JWT_SECRET_KEY to a real random value before starting the backend."
        )
    if secret == PLACEHOLDER_JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is still the placeholder value from .env.example, "
            "which is committed to the repo and therefore public. Generate a "
            "real secret (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`) "
            "and set it in .env before starting the backend."
        )
    return secret


POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ["POSTGRES_DB"]
APP_DB_USER = os.environ["APP_DB_USER"]
APP_DB_PASSWORD = os.environ["APP_DB_PASSWORD"]

JWT_SECRET_KEY = validate_jwt_secret(os.environ.get("JWT_SECRET_KEY"))
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# The frontend's origin, for CORS (backend/main.py). Vite's default dev port
# — a browser running the frontend is a different origin than this API, so
# without this every fetch() from it would be blocked by the browser itself
# before the request even reaches FastAPI's own auth checks.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")


def dsn() -> str:
    return (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
        f"user={APP_DB_USER} password={APP_DB_PASSWORD}"
    )
