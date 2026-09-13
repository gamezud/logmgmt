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
