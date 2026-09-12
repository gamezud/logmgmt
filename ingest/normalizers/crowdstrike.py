"""Normalizer for source="crowdstrike" (assignment §4.4)."""
from ingest.models import NormalizedEvent, clamp_severity
from ingest.timeutil import parse_rfc3339


def normalize(payload: dict, tenant: str) -> NormalizedEvent:
    return NormalizedEvent(
        tenant=tenant,
        event_time=parse_rfc3339(payload["@timestamp"]),
        source="crowdstrike",
        event_type=payload["event_type"],
        severity=clamp_severity(int(payload["severity"])),
        # No CHECK enum on `action` (docs/DECISIONS.md #3) precisely
        # because vendor values like "quarantine" don't fit a fixed list —
        # pass it through as-is.
        action=payload.get("action"),
        host=payload.get("host"),
        process=payload.get("process"),
        # `sha256` has no dedicated column; stays in `raw` only.
        raw=dict(payload),
    )
