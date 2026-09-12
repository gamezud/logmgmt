"""Normalizer for source="aws" (assignment §4.5, abridged CloudTrail)."""
from ingest.models import NormalizedEvent
from ingest.timeutil import parse_rfc3339


def normalize(payload: dict, tenant: str) -> NormalizedEvent:
    cloud = payload.get("cloud", {})
    return NormalizedEvent(
        tenant=tenant,
        event_time=parse_rfc3339(payload["@timestamp"]),
        source="aws",
        event_type=payload["event_type"],
        user=payload.get("user"),
        # Flattened per docs/DECISIONS.md #2 (dotted cloud.* -> columns).
        cloud_service=cloud.get("service"),
        cloud_account_id=cloud.get("account_id"),
        cloud_region=cloud.get("region"),
        # The whole inbound object, verbatim — including its own nested
        # "raw" key, left untouched. Simplest, most literal reading of
        # "always preserve the original payload"; nothing is lost, since
        # raw.raw.eventName etc. stay reachable through the GIN index.
        raw=dict(payload),
    )
