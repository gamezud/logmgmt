"""The single "produce a UTC-aware datetime" code path for ingest. Every
timestamp format this project accepts (RFC3339 from JSON sources, RFC3164
from syslog) is converted to UTC here and nowhere else — see
docs/DECISIONS.md for the reasoning behind each assumption below.
"""
from datetime import datetime, timedelta, timezone


def parse_rfc3339(ts: str) -> datetime:
    """'...Z'-suffixed RFC3339 -> tz-aware UTC datetime.

    Python 3.10's datetime.fromisoformat() rejects a trailing 'Z' (only
    fixed in 3.11+), and this project is locked to 3.10 (CLAUDE.md) — so
    swap it for '+00:00' first.
    """
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def parse_rfc3164(month_day_time: str, now: datetime | None = None) -> datetime:
    """RFC3164's 'Mon DD HH:MM:SS' has no year and no timezone. Assume UTC
    and the current year; if that would put the timestamp in the future (a
    year-boundary straggler, e.g. a 'Dec 31' line processed on Jan 2), roll
    back one year instead.

    `now` is an injectable parameter (never called internally as
    datetime.now()) purely so tests can pin the rollover boundary
    deterministically.
    """
    now = now or datetime.now(timezone.utc)
    candidate = datetime.strptime(
        f"{now.year} {month_day_time}", "%Y %b %d %H:%M:%S"
    ).replace(tzinfo=timezone.utc)
    if candidate > now + timedelta(minutes=5):
        candidate = candidate.replace(year=now.year - 1)
    return candidate
