"""GET /alerts — paginated list of fired alerts, tenant-scoped by RLS (via
get_tenant_conn — see docs/DECISIONS.md). Available to both admin and
viewer, same as /search and /stats/*: this is a read, and viewer's whole
purpose is read-only access to its own tenant's data.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
import psycopg
from psycopg import sql

from backend.db import get_tenant_conn
from backend.schemas import AlertListResponse, AlertResponse

router = APIRouter(tags=["alerting"])

_MAX_LIMIT = 500

_COLUMNS = [
    "id", "tenant", "rule_id", "triggered_at", "src_ip", "event_count",
    "threshold", "window_seconds", "window_start", "window_end", "webhook_sent_at",
]


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    start_time: Optional[datetime] = Query(None, description="inclusive lower bound on triggered_at"),
    end_time: Optional[datetime] = Query(None, description="exclusive upper bound on triggered_at"),
    src_ip: Optional[str] = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> AlertListResponse:
    conditions = []
    params: dict = {}

    if start_time is not None:
        conditions.append(sql.SQL("triggered_at >= %(start_time)s"))
        params["start_time"] = start_time
    if end_time is not None:
        conditions.append(sql.SQL("triggered_at < %(end_time)s"))
        params["end_time"] = end_time
    if src_ip is not None:
        conditions.append(sql.SQL("src_ip = %(src_ip)s"))
        params["src_ip"] = src_ip

    where_clause = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")

    # Same "fetch limit+1, drop the extra row" trick as /search instead of a
    # separate COUNT(*) — see docs/DECISIONS.md #31.
    query = sql.SQL(
        "SELECT {columns} FROM alerts WHERE {where} "
        "ORDER BY triggered_at DESC LIMIT %(fetch_limit)s OFFSET %(offset)s"
    ).format(columns=sql.SQL(", ").join(sql.SQL(c) for c in _COLUMNS), where=where_clause)
    params["fetch_limit"] = limit + 1
    params["offset"] = offset

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        AlertResponse(
            id=row[0], tenant=row[1], rule_id=row[2], triggered_at=row[3], src_ip=row[4],
            event_count=row[5], threshold=row[6], window_seconds=row[7],
            window_start=row[8], window_end=row[9], webhook_sent_at=row[10],
        )
        for row in rows
    ]
    return AlertListResponse(items=items, limit=limit, offset=offset, has_more=has_more)
