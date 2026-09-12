"""Normalizer for source="firewall" (assignment §4.1, RFC3164 syslog)."""
from ingest.models import NormalizedEvent
from ingest.syslog_parser import SyslogEnvelope


def normalize(envelope: SyslogEnvelope, tenant: str) -> NormalizedEvent:
    fields = envelope.fields
    return NormalizedEvent(
        tenant=tenant,
        event_time=envelope.event_time,
        source="firewall",
        vendor=fields.get("vendor"),
        product=fields.get("product"),
        # The wire format has no explicit event type; a fixed literal is
        # used rather than deriving one from `action` (e.g.
        # "traffic_deny"), which would just re-encode a column that
        # already exists, for no query benefit.
        event_type="traffic",
        # RFC3164 severity is 0=Emergency..7=Debug, inverted from this
        # schema's higher=more-severe convention (docs/DECISIONS.md #4).
        severity=7 - envelope.syslog_severity,
        # Direct indexing (not .get()) below: these are the same keys
        # source_hint_from_fields used to classify this line as firewall
        # in the first place, so a missing one means genuinely malformed
        # input that should raise and fall through to the dispatcher's
        # unknown-source fallback, not silently produce a half-populated row.
        action=fields["action"],
        src_ip=fields["src"],
        src_port=int(fields["spt"]),
        dst_ip=fields["dst"],
        dst_port=int(fields["dpt"]),
        protocol=fields.get("proto"),
        host=envelope.hostname,
        rule_name=fields.get("policy"),
        raw={"raw_line": envelope.raw_line},
    )
