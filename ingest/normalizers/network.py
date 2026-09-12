"""Normalizer for source="network" (assignment §4.2, RFC3164 router syslog)."""
from ingest.models import NormalizedEvent
from ingest.syslog_parser import SyslogEnvelope


def normalize(envelope: SyslogEnvelope, tenant: str) -> NormalizedEvent:
    fields = envelope.fields
    return NormalizedEvent(
        tenant=tenant,
        event_time=envelope.event_time,
        source="network",
        # Direct indexing: source_hint_from_fields already required
        # "event" to be present to classify this as a network line.
        event_type=fields["event"],
        event_subtype=fields.get("reason"),
        severity=7 - envelope.syslog_severity,
        host=envelope.hostname,
        # `if=` (interface name) and `mac=` have no fitting column — not
        # `host`, which is the device itself (r1), not the interface.
        # Stay in `raw` only.
        raw={"raw_line": envelope.raw_line},
    )
