"""Dispatcher: picks the right per-source normalizer and, on any failure,
falls back to a valid source="unknown" event rather than dropping the
message (docs/DECISIONS.md). Both ingest/syslog_server.py and
ingest/batch_loader.py call this same function — the single fallback path
for the whole system.
"""
import logging
from datetime import datetime, timezone

from ingest.models import NormalizedEvent
from ingest.normalizers import ad, api, aws, crowdstrike, firewall, m365, network
from ingest.syslog_parser import SyslogEnvelope

log = logging.getLogger(__name__)

NORMALIZERS = {
    "api": api.normalize,
    "crowdstrike": crowdstrike.normalize,
    "aws": aws.normalize,
    "m365": m365.normalize,
    "ad": ad.normalize,
    "firewall": firewall.normalize,
    "network": network.normalize,
}


def normalize(source_hint: str | None, payload, tenant: str) -> NormalizedEvent:
    normalizer = NORMALIZERS.get(source_hint) if source_hint else None
    if normalizer is not None:
        try:
            return normalizer(payload, tenant)
        except Exception as exc:
            log.warning(
                "normalizer for source_hint=%r raised %s: %s — "
                "falling back to source=unknown",
                source_hint, type(exc).__name__, exc,
            )
            fallback_reason = f"{type(exc).__name__}: {exc}"
    else:
        fallback_reason = f"unrecognized or missing source_hint={source_hint!r}"
        log.warning("no normalizer for source_hint=%r — falling back to source=unknown", source_hint)

    raw = _coerce_raw(payload)
    raw["_fallback_reason"] = fallback_reason
    raw["_fallback_source_hint"] = source_hint
    return NormalizedEvent(
        tenant=tenant,
        event_time=datetime.now(timezone.utc),
        source="unknown",
        event_type="unparsed",
        raw=raw,
        tags=["fallback"],
    )


def _coerce_raw(payload) -> dict:
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, SyslogEnvelope):
        return {"raw_line": payload.raw_line}
    return {"_raw_text": str(payload)}
