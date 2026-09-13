"""GET/POST /alert-rules and PATCH /alert-rules/{id} — admin-configurable
alert rule config, tenant-scoped via RLS like every other tenant-data
endpoint (get_tenant_conn — see backend/db.py, docs/DECISIONS.md).

GET is available to both roles (same "viewer reads, admin writes" split as
the rest of this backend); POST/PATCH require admin (require_role) — the
assignment's own wording: "admin จัดการ alert rule ได้ viewer ดูได้อย่างเดียว".

Only one rule_type exists this session ("failed_login_burst", enforced by
alert_rules' own CHECK constraint — backend/db/init/06_alerts_schema.sql),
set here server-side rather than accepted from the client.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, status
import psycopg
from psycopg import sql

from backend.db import get_tenant_conn
from backend.deps import require_role
from backend.schemas import AlertRuleCreate, AlertRuleResponse, AlertRuleUpdate
from backend.security import TokenClaims

router = APIRouter(prefix="/alert-rules", tags=["alerting"])

RULE_TYPE = "failed_login_burst"

_COLUMNS = "id, tenant, rule_type, threshold, window_seconds, cooldown_seconds, enabled, created_at, updated_at"

# Whitelist mapping AlertRuleUpdate's field names to actual DB columns —
# same "never interpolate a client-influenced string directly as an
# identifier" reasoning as backend/routers/stats.py's _TOP_FIELD_COLUMNS,
# even though these particular keys are already constrained to exactly
# these four by Pydantic (AlertRuleUpdate declares no others).
_UPDATABLE_COLUMNS = {
    "threshold": sql.Identifier("threshold"),
    "window_seconds": sql.Identifier("window_seconds"),
    "cooldown_seconds": sql.Identifier("cooldown_seconds"),
    "enabled": sql.Identifier("enabled"),
}


def _row_to_response(row) -> AlertRuleResponse:
    id_, tenant, rule_type, threshold, window_seconds, cooldown_seconds, enabled, created_at, updated_at = row
    return AlertRuleResponse(
        id=id_, tenant=tenant, rule_type=rule_type, threshold=threshold,
        window_seconds=window_seconds, cooldown_seconds=cooldown_seconds,
        enabled=enabled, created_at=created_at, updated_at=updated_at,
    )


@router.get("", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> list[AlertRuleResponse]:
    async with conn.cursor() as cur:
        await cur.execute(f"SELECT {_COLUMNS} FROM alert_rules ORDER BY id")
        rows = await cur.fetchall()
    return [_row_to_response(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AlertRuleResponse)
async def create_alert_rule(
    body: AlertRuleCreate,
    claims: TokenClaims = Depends(require_role("admin")),
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> AlertRuleResponse:
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                INSERT INTO alert_rules (tenant, rule_type, threshold, window_seconds, cooldown_seconds, enabled)
                VALUES (%(tenant)s, %(rule_type)s, %(threshold)s, %(window_seconds)s, %(cooldown_seconds)s, %(enabled)s)
                RETURNING {_COLUMNS}
                """,
                {
                    "tenant": claims.tenant,
                    "rule_type": RULE_TYPE,
                    "threshold": body.threshold,
                    "window_seconds": body.window_seconds,
                    "cooldown_seconds": body.cooldown_seconds,
                    "enabled": body.enabled,
                },
            )
            row = await cur.fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a {RULE_TYPE!r} rule already exists for this tenant — use PATCH /alert-rules/{{id}} to update it",
        ) from exc
    return _row_to_response(row)


@router.patch("/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    body: AlertRuleUpdate = Body(...),
    claims: TokenClaims = Depends(require_role("admin")),
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> AlertRuleResponse:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no fields to update")

    assignments = sql.SQL(", ").join(
        sql.SQL("{column} = %s").format(column=_UPDATABLE_COLUMNS[field]) for field in updates
    )
    query = sql.SQL(
        "UPDATE alert_rules SET {assignments}, updated_at = now() "
        "WHERE id = %s RETURNING " + _COLUMNS
    ).format(assignments=assignments)
    values = [*updates.values(), rule_id]

    async with conn.cursor() as cur:
        await cur.execute(query, values)
        row = await cur.fetchone()

    # RLS's USING clause already confines this UPDATE to the caller's own
    # tenant (docs/DECISIONS.md #6-#8) — a rule_id belonging to another
    # tenant, or one that doesn't exist at all, both come back as zero rows
    # updated, which reads identically as 404 either way (no cross-tenant
    # existence leak: this endpoint never distinguishes "not yours" from
    # "doesn't exist").
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert rule not found")
    return _row_to_response(row)
