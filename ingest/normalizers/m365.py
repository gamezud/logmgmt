"""Normalizer for source="m365" (assignment §4.6, abridged Unified Audit Log)."""
from ingest.models import NormalizedEvent
from ingest.timeutil import parse_rfc3339


def normalize(payload: dict, tenant: str) -> NormalizedEvent:
    return NormalizedEvent(
        tenant=tenant,
        event_time=parse_rfc3339(payload["@timestamp"]),
        source="m365",
        event_type=payload["event_type"],
        user=payload.get("user"),
        src_ip=payload.get("ip"),
        # `action` has no enforced enum (docs/DECISIONS.md #3) precisely
        # because vendor "what happened" values vary — "Success" describing
        # a logon outcome plays the same role here as firewall's
        # allow/deny or CrowdStrike's quarantine, so it's reused rather
        # than adding a single-source-only `status` column.
        action=payload.get("status"),
        # `workload` ("Exchange") has no fitting column — not `product`,
        # which implies a vendor product name, not an M365 sub-app. Stays
        # in `raw` only.
        raw=dict(payload),
    )
