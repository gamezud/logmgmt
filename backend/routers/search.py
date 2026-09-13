"""GET /search — filterable, paginated search over `events`, scoped to the
caller's tenant by RLS (via get_tenant_conn — see docs/DECISIONS.md).
Available to both admin and viewer: this is a read, and viewer's whole
purpose is read-only access to its own tenant.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
import psycopg
from psycopg import sql

from backend.db import get_tenant_conn
from backend.deps import get_current_claims
from backend.schemas import SearchResponse, SearchResultItem
from backend.security import TokenClaims

router = APIRouter(tags=["search"])

_MAX_LIMIT = 500

_COLUMNS = [
    "id", "tenant", "event_time", "source", "vendor", "product", "event_type",
    "event_subtype", "severity", "action", "src_ip", "src_port", "dst_ip",
    "dst_port", "protocol", '"user"', "host", "process", "url", "http_method",
    "status_code", "rule_name", "rule_id", "cloud_account_id", "cloud_region",
    "cloud_service", "raw", "_tags",
]


@router.get("/search", response_model=SearchResponse)
async def search(
    start_time: Optional[datetime] = Query(None, description="inclusive lower bound on event_time"),
    end_time: Optional[datetime] = Query(None, description="exclusive upper bound on event_time"),
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    user: Optional[str] = None,
    src_ip: Optional[str] = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    claims: TokenClaims = Depends(get_current_claims),
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> SearchResponse:
    conditions = []
    params: dict = {}

    if start_time is not None:
        conditions.append(sql.SQL("event_time >= %(start_time)s"))
        params["start_time"] = start_time
    if end_time is not None:
        conditions.append(sql.SQL("event_time < %(end_time)s"))
        params["end_time"] = end_time
    if source is not None:
        conditions.append(sql.SQL("source = %(source)s"))
        params["source"] = source
    if event_type is not None:
        conditions.append(sql.SQL("event_type = %(event_type)s"))
        params["event_type"] = event_type
    if user is not None:
        conditions.append(sql.SQL('"user" = %(user)s'))
        params["user"] = user
    if src_ip is not None:
        conditions.append(sql.SQL("src_ip = %(src_ip)s"))
        params["src_ip"] = src_ip

    where_clause = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")

    # Fetch limit+1 rows rather than a separate COUNT(*) query to compute
    # has_more — COUNT(*) over a filtered range of a high-volume log table
    # is its own expensive scan; fetching one extra row and dropping it if
    # present is effectively free by comparison. See docs/DECISIONS.md.
    query = sql.SQL(
        "SELECT {columns} FROM events WHERE {where} "
        "ORDER BY event_time DESC LIMIT %(fetch_limit)s OFFSET %(offset)s"
    ).format(columns=sql.SQL(", ").join(sql.SQL(c) for c in _COLUMNS), where=where_clause)
    params["fetch_limit"] = limit + 1
    params["offset"] = offset

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        # populate_by_name=True on SearchResultItem (see backend/schemas.py)
        # lets us pass event_time here by its actual field name, instead of
        # needing its "@timestamp" alias (which isn't a valid Python
        # keyword-argument name).
        SearchResultItem(
            id=row[0], tenant=row[1], event_time=row[2], source=row[3], vendor=row[4],
            product=row[5], event_type=row[6], event_subtype=row[7], severity=row[8], action=row[9],
            src_ip=row[10], src_port=row[11], dst_ip=row[12], dst_port=row[13], protocol=row[14],
            user=row[15], host=row[16], process=row[17], url=row[18], http_method=row[19],
            status_code=row[20], rule_name=row[21], rule_id=row[22], cloud_account_id=row[23],
            cloud_region=row[24], cloud_service=row[25], raw=row[26], tags=row[27],
        )
        for row in rows
    ]
    return SearchResponse(items=items, limit=limit, offset=offset, has_more=has_more)
