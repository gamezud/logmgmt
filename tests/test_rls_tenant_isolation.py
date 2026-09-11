"""Verifies Row-Level Security actually isolates tenants when queried through
the app_user role (the same role the backend will connect as), that it fails
closed rather than open, that WITH CHECK blocks cross-tenant writes, and that
the RLS-per-partition fix in apply_tenant_rls() (see backend/db/README.md and
02_schema.sql) is actually load-bearing. See docs/DECISIONS.md for the design.

Both a WITH CHECK violation and a plain grant-based denial surface as
psycopg.errors.InsufficientPrivilege (SQLSTATE 42501) — verified empirically
against postgres:16 before writing these assertions.
"""
import os

import psycopg
import pytest
from psycopg import sql


def test_tenant_cannot_see_another_tenants_rows(make_app_conn):
    conn_a = make_app_conn()
    with conn_a.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_a'")
        cur.execute(
            "INSERT INTO events (tenant, event_time, source, event_type) "
            "VALUES (%s, now(), %s, %s)",
            ("test_tenant_a", "api", "rls_probe"),
        )

    conn_b = make_app_conn()
    with conn_b.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_b'")
        cur.execute("SELECT tenant FROM events WHERE tenant = %s", ("test_tenant_a",))
        assert cur.fetchall() == []


def test_unset_tenant_sees_no_rows(make_app_conn):
    """No SET app.tenant on this connection at all — current_setting(...,
    true) returns NULL, and `tenant = NULL` is never true, so RLS must deny
    every row rather than default to showing everything."""
    seed_conn = make_app_conn()
    with seed_conn.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_a'")
        cur.execute(
            "INSERT INTO events (tenant, event_time, source, event_type) "
            "VALUES (%s, now(), %s, %s)",
            ("test_tenant_a", "api", "rls_probe"),
        )

    unset_conn = make_app_conn()
    with unset_conn.cursor() as cur:
        cur.execute("SELECT tenant FROM events")
        assert cur.fetchall() == []


def test_tenant_cannot_insert_as_another_tenant(make_app_conn):
    """WITH CHECK must reject an insert whose tenant column doesn't match the
    session's app.tenant, even though the session is otherwise authorized to
    insert into events at all — this is what stops a compromised/buggy
    backend from writing data under the wrong tenant."""
    conn = make_app_conn()
    with conn.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_a'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO events (tenant, event_time, source, event_type) "
                "VALUES (%s, now(), %s, %s)",
                ("test_tenant_b", "api", "rls_probe"),
            )


def test_direct_partition_access_is_isolated(admin_conn, make_app_conn):
    """Regression guard for the bug caught during review: Postgres does NOT
    propagate RLS policies from a partitioned parent to its partitions the
    way it propagates indexes (verified empirically — see
    backend/db/README.md). If a future change ever drops the
    `PERFORM apply_tenant_rls(partition_name)` call inside
    create_daily_partitions(), this test must catch it.
    """
    conn_a = make_app_conn()
    with conn_a.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_a'")
        cur.execute(
            "INSERT INTO events (tenant, event_time, source, event_type) "
            "VALUES (%s, now(), %s, %s) RETURNING tableoid::regclass::text",
            ("test_tenant_a", "api", "rls_probe"),
        )
        (partition_name,) = cur.fetchone()

    select_from_partition = sql.SQL("SELECT tenant FROM {}").format(
        sql.Identifier(partition_name)
    )

    # app_user is only ever granted access on the parent `events`, never on
    # individual partitions, so direct access is normally denied before RLS
    # even gets evaluated — that's a real, independent layer of defense, so
    # record it here rather than treat it as incidental.
    direct_conn = make_app_conn()
    with direct_conn.cursor() as cur:
        cur.execute("SET app.tenant = 'test_tenant_a'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(select_from_partition)

    # That grant-level block would hide a regression in the RLS policy
    # itself, since it denies access regardless of whether apply_tenant_rls()
    # ever ran. Temporarily grant SELECT on just this one partition so the
    # next query is decided by RLS alone — this is the part that would fail
    # if apply_tenant_rls() were ever removed from create_daily_partitions().
    app_user = os.environ["APP_DB_USER"]
    grant = sql.SQL("GRANT SELECT ON {} TO {}").format(
        sql.Identifier(partition_name), sql.Identifier(app_user)
    )
    revoke = sql.SQL("REVOKE SELECT ON {} FROM {}").format(
        sql.Identifier(partition_name), sql.Identifier(app_user)
    )
    with admin_conn.cursor() as cur:
        cur.execute(grant)
    try:
        wrong_tenant_conn = make_app_conn()
        with wrong_tenant_conn.cursor() as cur:
            cur.execute("SET app.tenant = 'test_tenant_b'")
            cur.execute(select_from_partition)
            assert cur.fetchall() == []
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(revoke)
