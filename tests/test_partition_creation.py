"""Verifies create_daily_partitions() creates the expected daily partitions
and that inserted rows are routed into the correct one. See
backend/db/init/03_partition_maintenance.sql and docs/DECISIONS.md.
"""
from datetime import date, timedelta


def test_creates_expected_partition_range(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute("SELECT create_daily_partitions(1, 7)")
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            r"AND tablename ~ '^events_\d{4}_\d{2}_\d{2}$'"
        )
        existing = {row[0] for row in cur.fetchall()}

    today = date.today()
    expected = {
        "events_" + (today + timedelta(days=offset)).strftime("%Y_%m_%d")
        for offset in range(-1, 8)  # matches days_back=1, days_ahead=7 above
    }
    assert expected <= existing


def test_row_lands_in_the_correct_daily_partition(admin_conn):
    today = date.today()
    expected_partition = "events_" + today.strftime("%Y_%m_%d")

    with admin_conn.cursor() as cur:
        cur.execute("SELECT create_daily_partitions(1, 7)")
        cur.execute(
            "INSERT INTO events (tenant, event_time, source, event_type) "
            "VALUES (%s, now(), %s, %s) RETURNING tableoid::regclass::text",
            ("test_partition_probe", "api", "partition_probe"),
        )
        (actual_partition,) = cur.fetchone()

    assert actual_partition == expected_partition


def test_call_is_idempotent(admin_conn):
    """Calling it twice must not error (IF NOT EXISTS) and must not change
    which partitions exist."""
    with admin_conn.cursor() as cur:
        cur.execute("SELECT create_daily_partitions(1, 7)")
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            r"AND tablename ~ '^events_\d{4}_\d{2}_\d{2}$'"
        )
        first_pass = {row[0] for row in cur.fetchall()}

        cur.execute("SELECT create_daily_partitions(1, 7)")
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            r"AND tablename ~ '^events_\d{4}_\d{2}_\d{2}$'"
        )
        second_pass = {row[0] for row in cur.fetchall()}

    assert first_pass == second_pass
