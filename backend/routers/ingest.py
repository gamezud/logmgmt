"""POST /ingest — admin-only (see docs/DECISIONS.md for the accepted risk of
a machine credential holding admin rights, and why a write-only "ingestor"
role is deliberately not implemented in this session).

Reuses ingest/normalizers.normalize and ingest/db.write_event_async
directly rather than reimplementing normalization or the RLS-safe write
path — both already exist and are already tested.

Tenant for the stored event is ALWAYS the caller's verified JWT claim,
never anything in the request body. The assignment's own POST /ingest
sample payloads (§4.3-4.7) embed a "tenant" field in the JSON — that field
is read here and then explicitly discarded before the payload reaches
normalize(), on purpose. See docs/DECISIONS.md.
"""
from fastapi import APIRouter, Body, Depends
import psycopg

from backend.db import get_pooled_conn
from backend.deps import require_role
from backend.security import TokenClaims
from ingest.db import write_event_async
from ingest.normalizers import normalize

router = APIRouter(tags=["ingest"])


@router.post("/ingest", status_code=201)
async def ingest(
    body: dict = Body(...),
    claims: TokenClaims = Depends(require_role("admin")),
    conn: psycopg.AsyncConnection = Depends(get_pooled_conn),
) -> dict:
    source_hint = body.get("source")
    payload = {key: value for key, value in body.items() if key != "tenant"}
    event = normalize(source_hint, payload, claims.tenant)
    await write_event_async(conn, event)
    return {"status": "accepted", "tenant": claims.tenant, "source": event.source, "event_type": event.event_type}
