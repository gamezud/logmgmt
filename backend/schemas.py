"""Pydantic v2 request/response models for the HTTP API. SearchResultItem
mirrors ingest/models.py's NormalizedEvent field-for-field (same
event_time/"@timestamp" alias, same flattened cloud_* names — see
docs/DECISIONS.md #1 and #2) since it's the same row shape coming back out
of `events` that went in.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SearchResultItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    tenant: str
    event_time: datetime = Field(alias="@timestamp")
    source: str
    vendor: Optional[str] = None
    product: Optional[str] = None
    event_type: str
    event_subtype: Optional[str] = None
    severity: Optional[int] = None
    action: Optional[str] = None
    src_ip: Optional[IPvAnyAddress] = None
    src_port: Optional[int] = None
    dst_ip: Optional[IPvAnyAddress] = None
    dst_port: Optional[int] = None
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
    raw: dict
    tags: list[str]


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    limit: int
    offset: int
    has_more: bool


class TopStatItem(BaseModel):
    value: str
    count: int


class TimelineBucket(BaseModel):
    bucket: datetime
    count: int


# --- Alerting (docs/DECISIONS.md #35-#41) -----------------------------------
# No `rule_type` field on Create/Update: the only valid value this session
# is "failed_login_burst" (enforced by alert_rules' own CHECK constraint),
# so the router sets it server-side rather than asking the client to send a
# constant back to us.

class AlertRuleCreate(BaseModel):
    threshold: int = Field(default=5, gt=0)
    window_seconds: int = Field(default=300, gt=0)
    cooldown_seconds: int = Field(default=900, gt=0)
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    # All optional: PATCH only touches the fields the caller actually sent.
    threshold: Optional[int] = Field(default=None, gt=0)
    window_seconds: Optional[int] = Field(default=None, gt=0)
    cooldown_seconds: Optional[int] = Field(default=None, gt=0)
    enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: int
    tenant: str
    rule_type: str
    threshold: int
    window_seconds: int
    cooldown_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AlertResponse(BaseModel):
    id: int
    tenant: str
    rule_id: int
    triggered_at: datetime
    src_ip: IPvAnyAddress
    event_count: int
    threshold: int
    window_seconds: int
    # The real-world span the source claims (MIN/MAX(event_time) of the
    # matched rows) — NOT the ingested_at window that decided whether to
    # fire. See docs/DECISIONS.md and alerting/engine.py.
    window_start: datetime
    window_end: datetime
    webhook_sent_at: Optional[datetime] = None


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    limit: int
    offset: int
    has_more: bool
