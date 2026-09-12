"""Normalizer for source="api" — JSON POSTed straight in the common schema
shape (assignment §4.3). Simplest of the seven: field names already mostly
match the target model.
"""
from ingest.models import NormalizedEvent
from ingest.timeutil import parse_rfc3339


def normalize(payload: dict, tenant: str) -> NormalizedEvent:
    return NormalizedEvent(
        tenant=tenant,
        event_time=parse_rfc3339(payload["@timestamp"]),
        source="api",
        event_type=payload["event_type"],
        # `reason` has no dedicated column; a login failure's specific
        # reason ("wrong_password") reads naturally as a subtype of
        # event_type="app_login_failed", and event_subtype is otherwise
        # unused for this source — a free, query-useful signal rather than
        # leaving it stranded in raw only.
        event_subtype=payload.get("reason"),
        src_ip=payload.get("ip"),
        user=payload.get("user"),
        raw=dict(payload),
    )
