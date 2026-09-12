"""CLI: load a JSON or CSV log file into `events`. Used both for ad-hoc
loading of real exported logs and, via `make seed` (with
--rebase-timestamps), for loading the assignment's sample files so a
reviewer sees fresh, visible data immediately (see docs/DECISIONS.md for
why the assignment's hardcoded 2025-08-20 sample timestamps would otherwise
fall outside the 7-day retention window and events_default).
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone

from ingest.db import connect_sync, write_event_sync
from ingest.models import NormalizedEvent
from ingest.normalizers import normalize


def _resolve_tenant(record: dict, cli_tenant: str | None) -> str | None:
    return record.get("tenant") or cli_tenant


def _resolve_source(record: dict, cli_source: str | None) -> str | None:
    return record.get("source") or cli_source


def _load_records(path: str) -> list[dict]:
    if path.endswith(".json"):
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    if path.endswith(".csv"):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    raise ValueError(f"unsupported file extension: {path}")


def _rebase_timestamps(events: list[NormalizedEvent]) -> None:
    """Shift every event's event_time by the same offset, anchoring the
    earliest one to "now" and preserving relative spacing between the
    others. Mutates in place. Only called when --rebase-timestamps is
    passed — real historical-data loads must never have their timestamps
    silently rewritten.
    """
    if not events:
        return
    earliest = min(e.event_time for e in events)
    offset = datetime.now(timezone.utc) - earliest
    for e in events:
        e.event_time = e.event_time + offset


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a JSON or CSV log file into events.")
    parser.add_argument("file")
    parser.add_argument("--tenant", help="fallback tenant for records without their own 'tenant' field")
    parser.add_argument("--source", help="fallback source for records without their own 'source' field")
    parser.add_argument(
        "--rebase-timestamps",
        action="store_true",
        help="shift event_time to 'now' (preserving relative spacing) while leaving raw untouched; "
        "for demo/seed data only, never for real historical loads",
    )
    args = parser.parse_args()

    try:
        records = _load_records(args.file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"batch_loader: cannot read {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)

    events: list[NormalizedEvent] = []
    skipped_no_tenant = 0
    for i, record in enumerate(records):
        tenant = _resolve_tenant(record, args.tenant)
        if tenant is None:
            print(
                f"batch_loader: skipping record {i}: no tenant "
                f"('tenant' field missing and --tenant not given)",
                file=sys.stderr,
            )
            skipped_no_tenant += 1
            continue
        source_hint = _resolve_source(record, args.source)
        events.append(normalize(source_hint, record, tenant))

    if args.rebase_timestamps:
        _rebase_timestamps(events)

    conn = connect_sync()
    for event in events:
        write_event_sync(conn, event)

    print(f"batch_loader: {len(events)} inserted, {skipped_no_tenant} skipped (no tenant)")


if __name__ == "__main__":
    main()
