"""Verifies drop_old_partitions() removes partitions past the retention
window and leaves in-window partitions alone. See
backend/db/init/03_partition_maintenance.sql and docs/DECISIONS.md for why
this is a DROP TABLE (metadata-only, near-instant) rather than a DELETE
(row-by-row, needs VACUUM afterwards).
"""
from datetime import date, timedelta

from psycopg import sql


def _partition_exists(admin_conn, partition_name: str) -> bool:
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = %s",
            (partition_name,),
        )
        return cur.fetchone() is not None


def test_drops_only_partitions_older_than_retention(admin_conn):
    old_day = date.today() - timedelta(days=10)
    old_partition = "events_" + old_day.strftime("%Y_%m_%d")

    with admin_conn.cursor() as cur:
        # Partition bounds in FOR VALUES FROM/TO must be literal constants —
        # Postgres's DDL parser doesn't accept bind parameters there ($1/$2).
        # sql.Literal() safely embeds them as quoted literals instead.
        cur.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {} PARTITION OF events "
                "FOR VALUES FROM ({}) TO ({})"
            ).format(
                sql.Identifier(old_partition),
                sql.Literal(old_day),
                sql.Literal(old_day + timedelta(days=1)),
            )
        )
        cur.execute("SELECT apply_tenant_rls(%s)", (old_partition,))

        # A row in the old partition, inserted through the parent so it's
        # routed automatically — confirms drop_old_partitions() removes data
        # along with the partition, not just an empty table.
        cur.execute(
            "INSERT INTO events (tenant, event_time, source, event_type) "
            "VALUES (%s, %s, %s, %s)",
            ("test_retention_probe", old_day, "api", "retention_probe"),
        )

        # Make sure current-window partitions exist too, so we can assert
        # they *aren't* touched by the drop below.
        cur.execute("SELECT create_daily_partitions(1, 7)")
        today_partition = "events_" + date.today().strftime("%Y_%m_%d")
        assert _partition_exists(admin_conn, today_partition)
        assert _partition_exists(admin_conn, old_partition)

        cur.execute("SELECT drop_old_partitions(7)")

    assert not _partition_exists(admin_conn, old_partition)
    assert _partition_exists(admin_conn, today_partition)


def test_call_is_idempotent(admin_conn):
    """Calling it with nothing left to drop must not error."""
    with admin_conn.cursor() as cur:
        cur.execute("SELECT drop_old_partitions(7)")
        cur.execute("SELECT drop_old_partitions(7)")
