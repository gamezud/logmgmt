"""FastAPI app entrypoint. Run via `uvicorn backend.main:app` (from the repo
root, like ingest's `python -m ingest.xxx` convention — see
docs/DECISIONS.md #22 for why running a file by path instead of as a module
breaks its package-relative imports).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from backend.config import FRONTEND_ORIGIN
from backend.db import pool
from backend.routers import alert_rules, alerts, auth, ingest, search, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The pool is opened here (not implicitly on first use) and closed here,
    # so its lifecycle is tied to the app's own startup/shutdown — see
    # backend/db.py.
    await pool.open()
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(title="Log Management System", lifespan=lifespan)

# allow_credentials=False: every request carries its JWT as a manually-
# attached `Authorization: Bearer` header (see docs/DECISIONS.md on JWT
# storage), never a cookie — so there's nothing here that needs the
# credentialed-CORS mode, just a plain allowed-origin allowlist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(search.router)
app.include_router(stats.router)
app.include_router(alert_rules.router)
app.include_router(alerts.router)


@app.get("/health")
async def health() -> dict:
    """No auth — used by docker-compose's healthcheck and by the SaaS
    deployment's load balancer/uptime check. Deliberately reveals nothing
    beyond "can this process reach the database right now": no Postgres
    version, no connection string, no exception detail — anything more is
    unnecessary information to hand to an unauthenticated caller.
    Returns 503 (not 200-with-a-status-field) when the database is
    unreachable, so a plain `curl -f` style healthcheck actually fails.
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable",
        ) from exc
    return {"status": "ok", "database": "ok"}
