"""Normalizer for source="ad" (assignment §4.7, abridged Windows Security 4625)."""
from ingest.models import NormalizedEvent
from ingest.timeutil import parse_rfc3339


def normalize(payload: dict, tenant: str) -> NormalizedEvent:
    return NormalizedEvent(
        tenant=tenant,
        event_time=parse_rfc3339(payload["@timestamp"]),
        source="ad",
        event_type=payload["event_type"],
        user=payload.get("user"),
        host=payload.get("host"),
        src_ip=payload.get("ip"),
        # A Windows Security Event ID is exactly the kind of stable,
        # vendor-defined "what kind of thing triggered this" identifier
        # rule_id represents for other sources.
        rule_id=str(payload["event_id"]) if "event_id" in payload else None,
        # `logon_type` (interactive/network/service enum) has no fitting
        # column — not `protocol`, not `action`. Stays in `raw` only.
        raw=dict(payload),
    )
