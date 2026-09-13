"""Pure unit tests, no DB: every timestamp format this project accepts
must convert to UTC correctly, including the two non-obvious cases
documented in docs/DECISIONS.md -- the RFC3339 "Z" suffix Python 3.10
can't parse natively, and RFC3164's missing year/timezone.
"""
from datetime import datetime, timezone

from ingest.timeutil import parse_rfc3164, parse_rfc3339


def test_parse_rfc3339_z_suffix():
    assert parse_rfc3339("2025-08-20T07:20:00Z") == datetime(
        2025, 8, 20, 7, 20, 0, tzinfo=timezone.utc
    )


def test_parse_rfc3339_explicit_offset():
    assert parse_rfc3339("2025-08-20T07:20:00+00:00") == datetime(
        2025, 8, 20, 7, 20, 0, tzinfo=timezone.utc
    )


def test_parse_rfc3164_assumes_current_year_and_utc():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    result = parse_rfc3164("Aug 20 12:44:56", now=now)
    assert result == datetime(2026, 8, 20, 12, 44, 56, tzinfo=timezone.utc)


def test_parse_rfc3164_rolls_back_a_year_at_the_boundary():
    """A 'Dec 31' line processed just after New Year's would otherwise be
    computed as being in the future -- roll back to the previous year.
    """
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    result = parse_rfc3164("Dec 31 23:59:59", now=now)
    assert result == datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def test_parse_rfc3164_does_not_roll_back_when_not_in_the_future():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    result = parse_rfc3164("Jan 1 00:00:00", now=now)
    assert result == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_parse_rfc3164_tolerates_small_clock_skew_without_rolling_back():
    """A timestamp a couple of minutes in the future is normal clock skew
    (the sending device's clock running slightly fast), not a year-boundary
    straggler -- must not trigger the year rollback. Guards the
    timedelta(minutes=5) tolerance in parse_rfc3164 from being deleted or
    shrunk to zero by accident.
    """
    now = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    result = parse_rfc3164("Sep 12 10:02:00", now=now)
    assert result == datetime(2026, 9, 12, 10, 2, 0, tzinfo=timezone.utc)
