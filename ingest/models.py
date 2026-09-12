"""The single normalized-event shape every source's normalizer produces.
Field names and types mirror backend/db/init/02_schema.sql exactly — see
docs/DECISIONS.md #1 (event_time / "@timestamp" alias) and #2 (flattened
cloud.* columns) for why the DB column names differ from the assignment's
common schema in those two spots.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant: str
    event_time: datetime = Field(alias="@timestamp")
    source: str
    vendor: Optional[str] = None
    product: Optional[str] = None
    event_type: str
    event_subtype: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=0, le=10)
    action: Optional[str] = None
    src_ip: Optional[IPvAnyAddress] = None
    src_port: Optional[int] = Field(default=None, ge=0, le=65535)
    dst_ip: Optional[IPvAnyAddress] = None
    dst_port: Optional[int] = Field(default=None, ge=0, le=65535)
    protocol: Optional[str] = None
    user: Optional[str] = None
    host: Optional[str] = None
    process: Optional[str] = None
    url: Optional[str] = None
    http_method: Optional[str] = None
    status_code: Optional[int] = None
    rule_name: Optional[str] = None
    rule_id: Optional[str] = None
    cloud_account_id: Optional[str] = None
    cloud_region: Optional[str] = None
    cloud_service: Optional[str] = None
    raw: dict = Field(default_factory=dict)

    # Maps to the DB's `_tags` column (see ingest/db.py's INSERT params).
    # Named `tags`, not `_tags`, on the model itself: nothing this session
    # ever reads or writes `_tags` from incoming JSON, so a Pydantic alias
    # for it would be unused ceremony.
    tags: list[str] = Field(default_factory=list)


def clamp_severity(value: int) -> int:
    """Defensively clamp an already-0-10-scaled, source-provided severity
    (currently only CrowdStrike) into the column's valid range. Severities
    this project derives itself (the syslog inversion formula,
    7 - syslog_severity) are mathematically already within [0, 7] and don't
    need this.
    """
    return max(0, min(10, value))
