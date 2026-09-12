"""Pure RFC3164 syslog parsing. No asyncio, no I/O — this module only turns
a line of text into structured data, so it's fully unit-testable in
isolation and reusable by both the live listener and any offline replay.
"""
import re
from dataclasses import dataclass
from datetime import datetime

from ingest.timeutil import parse_rfc3164

# <PRI>Mon DD HH:MM:SS host rest-of-message
LINE_RE = re.compile(
    r"^<(?P<pri>\d{1,3})>"
    r"(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<rest>.*)$"
)

# Non-greedy value capture with a lookahead for the next "key=" or end of
# string — needed because values can contain spaces with no quoting (e.g.
# `msg=DNS blocked policy=Block-DNS`). A naive str.split() would mis-tokenize
# "blocked" as a stray key-less token.
KV_RE = re.compile(r"(\w+)=(.*?)(?=\s\w+=|$)")


@dataclass
class SyslogEnvelope:
    facility: int
    syslog_severity: int  # 0=Emergency..7=Debug, RFC3164 direction (not yet inverted)
    event_time: datetime
    hostname: str
    fields: dict[str, str]
    raw_line: str


def parse_syslog_line(line: str, now: datetime | None = None) -> SyslogEnvelope:
    match = LINE_RE.match(line.strip())
    if not match:
        raise ValueError(f"line does not match RFC3164 shape: {line!r}")

    pri = int(match["pri"])
    facility, syslog_severity = divmod(pri, 8)
    event_time = parse_rfc3164(
        f'{match["month"]} {int(match["day"]):02d} {match["time"]}', now=now
    )
    return SyslogEnvelope(
        facility=facility,
        syslog_severity=syslog_severity,
        event_time=event_time,
        hostname=match["host"],
        fields=_parse_kv(match["rest"]),
        raw_line=line,
    )


def _parse_kv(rest: str) -> dict[str, str]:
    return dict(KV_RE.findall(rest))


def source_hint_from_fields(fields: dict[str, str]) -> str:
    """Content-key-sniffing dispatch (docs/DECISIONS.md): PRI facility isn't
    a portable source signal across real vendors, but the two sample
    formats have distinct, non-overlapping key vocabularies.
    """
    if "action" in fields and "src" in fields:
        return "firewall"
    if "if" in fields and "event" in fields:
        return "network"
    return "unknown"
