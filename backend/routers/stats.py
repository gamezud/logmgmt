"""GET /stats/top and GET /stats/timeline — dashboard aggregations, scoped to
the caller's tenant by RLS (via get_tenant_conn). Available to both admin
and viewer, same as /search.
"""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
import psycopg
from psycopg import sql

from backend.db import get_tenant_conn
from backend.schemas import TimelineBucket, TopStatItem

router = APIRouter(prefix="/stats", tags=["stats"])

# Whitelist mapping the API's field names to actual DB columns — never
# interpolate a client-supplied string directly as a column/identifier.
_TOP_FIELD_COLUMNS = {
    "ip": sql.Identifier("src_ip"),
    "user": sql.Identifier("user"),
    "event_type": sql.Identifier("event_type"),
}


@router.get("/top", response_model=list[TopStatItem])
async def top(
    field: Literal["ip", "user", "event_type"],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(10, ge=1, le=100),
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> list[TopStatItem]:
    column = _TOP_FIELD_COLUMNS[field]
    conditions = [sql.SQL("{column} IS NOT NULL").format(column=column)]
    params: dict = {}
    if start_time is not None:
        conditions.append(sql.SQL("event_time >= %(start_time)s"))
        params["start_time"] = start_time
    if end_time is not None:
        conditions.append(sql.SQL("event_time < %(end_time)s"))
        params["end_time"] = end_time
    where_clause = sql.SQL(" AND ").join(conditions)

    query = sql.SQL(
        "SELECT {column}::text AS value, count(*) AS count FROM events "
        "WHERE {where} GROUP BY {column} ORDER BY count DESC LIMIT %(limit)s"
    ).format(column=column, where=where_clause)
    params["limit"] = limit

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()
    return [TopStatItem(value=value, count=count) for value, count in rows]


@router.get("/timeline", response_model=list[TimelineBucket])
async def timeline(
    interval: Literal["minute", "hour", "day"] = "hour",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    conn: psycopg.AsyncConnection = Depends(get_tenant_conn),
) -> list[TimelineBucket]:
    conditions = []
    params: dict = {"interval": interval}
    if start_time is not None:
        conditions.append(sql.SQL("event_time >= %(start_time)s"))
        params["start_time"] = start_time
    if end_time is not None:
        conditions.append(sql.SQL("event_time < %(end_time)s"))
        params["end_time"] = end_time
    where_clause = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")

    # date_trunc's first argument is a plain function parameter, not an
    # identifier, so it can safely be a bind parameter — this isn't the same
    # class of problem as interpolating a column/table name (see
    # _TOP_FIELD_COLUMNS above). It's still restricted to the Literal type's
    # three values by FastAPI/Pydantic validation before this code ever runs.
    query = sql.SQL(
        "SELECT date_trunc(%(interval)s, event_time) AS bucket, count(*) AS count FROM events "
        "WHERE {where} GROUP BY bucket ORDER BY bucket"
    ).format(where=where_clause)

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()
    return [TimelineBucket(bucket=bucket, count=count) for bucket, count in rows]
