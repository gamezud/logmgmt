"""Dispatcher fallback behavior (ingest/normalizers/__init__.py): any
failure to normalize a message must still produce a valid NormalizedEvent
with source="unknown" rather than dropping the message, per
docs/DECISIONS.md's ingestion-stability requirement. All three trigger
paths funnel through the same fallback block, so each is asserted
identically: source, tags, the _fallback_reason marker, and that the
original data survives inside `raw`.
"""
from ingest.normalizers import normalize


def test_unrecognized_source_hint_falls_back_to_unknown():
    payload = {"anything": "goes here"}
    result = normalize("not_a_real_source", payload, tenant="demoA")

    assert result.source == "unknown"
    assert result.tags == ["fallback"]
    assert "_fallback_reason" in result.raw
    assert result.raw["anything"] == "goes here"


def test_normalizer_raising_falls_back_to_unknown():
    # "api" is a real, registered source_hint, but a payload missing the
    # required "@timestamp"/"event_type" keys makes api.normalize() raise
    # KeyError -- this exercises the dispatcher's `except Exception` path,
    # not the "unrecognized source_hint" path.
    payload = {"user": "alice"}
    result = normalize("api", payload, tenant="demoA")

    assert result.source == "unknown"
    assert result.tags == ["fallback"]
    assert "_fallback_reason" in result.raw
    assert "KeyError" in result.raw["_fallback_reason"]
    assert result.raw["user"] == "alice"


def test_unparseable_string_falls_back_to_unknown():
    # Mirrors ingest/syslog_server.py's handle_message(): a line that fails
    # parse_syslog_line's ValueError is passed to normalize() as a plain
    # string with source_hint="unknown".
    raw_text = "this is not a valid RFC3164 syslog line"
    result = normalize("unknown", raw_text, tenant="demoA")

    assert result.source == "unknown"
    assert result.tags == ["fallback"]
    assert "_fallback_reason" in result.raw
    assert result.raw["_raw_text"] == raw_text
