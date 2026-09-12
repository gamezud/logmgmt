-- events: the normalized common-schema table for all ingested log sources.
-- Partitioned by day on event_time (see 03_partition_maintenance.sql for how
-- partitions are created/dropped). See docs/DECISIONS.md for the reasoning
-- behind every non-obvious choice below.

CREATE TABLE events (
    id            bigint GENERATED ALWAYS AS IDENTITY,

    -- Multi-tenant isolation key. Enforced by the RLS policy below, not by
    -- application code adding WHERE tenant = ? — see docs/DECISIONS.md.
    -- CHECK (not just NOT NULL): the RLS policy compares tenant to
    -- current_setting('app.tenant', true), which comes back as '' (not
    -- NULL) on a connection that touched app.tenant earlier and later ran
    -- a query outside any transaction without resetting it (a real
    -- scenario for a long-lived ingest connection reused across tenants).
    -- That still fails closed today only because no real tenant value is
    -- ever ''  — this CHECK makes that an enforced invariant instead of a
    -- coincidence. See docs/DECISIONS.md.
    tenant        text NOT NULL CHECK (tenant <> ''),

    -- Common schema's "@timestamp" field. Stored as event_time internally
    -- (Postgres can't use "@timestamp" as an unquoted identifier); the future
    -- HTTP API keeps exposing "@timestamp" via a Pydantic alias. This is the
    -- partition key.
    event_time    timestamptz NOT NULL,

    source        text NOT NULL,   -- firewall|crowdstrike|aws|m365|ad|api|network (convention, not enforced — see DECISIONS.md)
    vendor        text,
    product       text,
    event_type    text NOT NULL,
    event_subtype text,
    severity      smallint CHECK (severity BETWEEN 0 AND 10),

    -- No CHECK enum: the assignment's own CrowdStrike sample uses
    -- action = "quarantine", outside its suggested allow|deny|create|delete|
    -- login|logout|alert list. See docs/DECISIONS.md.
    action        text,

    src_ip        inet,
    src_port      integer CHECK (src_port BETWEEN 0 AND 65535),
    dst_ip        inet,
    dst_port      integer CHECK (dst_port BETWEEN 0 AND 65535),
    protocol      text,

    "user"        text,   -- quoted: "user" is a reserved word
    host          text,
    process       text,
    url           text,
    http_method   text,
    status_code   integer,
    rule_name     text,
    rule_id       text,

    -- Flattened from the schema's dotted cloud.* naming — see docs/DECISIONS.md.
    cloud_account_id text,
    cloud_region      text,
    cloud_service     text,

    raw           jsonb NOT NULL DEFAULT '{}'::jsonb,
    _tags         text[] NOT NULL DEFAULT '{}'::text[],

    -- Arrival time, distinct from event_time (when the source says the event
    -- happened). Not part of the assignment's schema; added for future
    -- pipeline-lag monitoring.
    ingested_at   timestamptz NOT NULL DEFAULT now(),

    -- Composite PK: Postgres requires the partition key to be part of any
    -- unique constraint on a partitioned table.
    PRIMARY KEY (id, event_time)
) PARTITION BY RANGE (event_time);

-- Catches any row whose event_time falls outside every pre-created daily
-- partition (clock skew, late batches) so inserts never hard-fail. See
-- docs/DECISIONS.md for the lock/scan cost this creates if rows pile up here.
CREATE TABLE events_default PARTITION OF events DEFAULT;

-- Row-Level Security ---------------------------------------------------------
-- FORCE (not just ENABLE) so the policy also applies to the table owner —
-- though note POSTGRES_USER (the owner here) is a superuser, and superusers
-- always bypass RLS regardless of FORCE. The real protection is that the
-- backend must connect as app_user (see 01_roles.sh), which is neither the
-- owner nor a superuser, so ENABLE/FORCE fully apply to it.
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;

-- current_setting(..., true) (missing_ok = true) can come back two
-- different ways depending on history, and this policy fails closed in
-- both, for two different reasons:
--   1. NULL, if app.tenant was never set on this connection at all —
--      `tenant = NULL` is never true under normal SQL NULL semantics, so
--      no row matches.
--   2. '' (empty string), if app.tenant WAS set earlier via set_config(...,
--      true) inside a transaction that has since ended (COMMIT/ROLLBACK) —
--      Postgres resets a custom GUC placeholder to '' on transaction end,
--      not back to NULL. This matters for a long-lived connection reused
--      across tenants (e.g. the ingest syslog server), where a later query
--      could run without re-setting app.tenant first. Here `tenant = ''`
--      fails closed NOT because of NULL semantics but because of the
--      `CHECK (tenant <> '')` constraint on the column above, which makes
--      "no real tenant is ever ''" an enforced invariant instead of a
--      coincidence this policy happens to rely on. Verified against
--      postgres:16 — see docs/DECISIONS.md.
CREATE POLICY tenant_isolation ON events
    USING (tenant = current_setting('app.tenant', true))
    WITH CHECK (tenant = current_setting('app.tenant', true));

-- IMPORTANT: Postgres does NOT propagate a partitioned parent's RLS policy to
-- its partitions the way it propagates indexes. Verified empirically against
-- postgres:16 before writing this:
--   * A query THROUGH the parent (`SELECT ... FROM events`) is filtered by
--     the PARENT's policy across all partitions, regardless of each
--     partition's own RLS state.
--   * A query directly against a partition by name (`SELECT ... FROM
--     events_2026_09_11`) is governed ONLY by that partition's own RLS state:
--     - if RLS was never enabled on it, direct access is a full bypass (every
--       tenant's rows visible, no filtering at all);
--     - if RLS is enabled but it has no policy of its own, direct access
--       default-denies (zero rows, even for the "right" tenant).
-- So every partition needs ENABLE + FORCE + its OWN copy of the same policy.
-- This helper makes that idempotent and reusable from
-- create_daily_partitions() in 03_partition_maintenance.sql, so every new
-- partition gets it automatically instead of relying on someone remembering.
CREATE FUNCTION apply_tenant_rls(partition_name text) RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', partition_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', partition_name);

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = partition_name
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I '
            'USING (tenant = current_setting(''app.tenant'', true)) '
            'WITH CHECK (tenant = current_setting(''app.tenant'', true))',
            partition_name
        );
    END IF;
END;
$$ LANGUAGE plpgsql;

SELECT apply_tenant_rls('events_default');

-- Least-privilege grants ------------------------------------------------------
-- Append-only: no UPDATE/DELETE, so a leaked app_user credential can't alter
-- or erase existing log data. Granting on the partitioned parent is enough —
-- verified empirically that INSERT/SELECT routed through `events` are
-- checked against the PARENT's grants, with no separate grant needed on each
-- partition (unlike RLS policies, which do need to be per-partition).
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT ON events TO app_user;

-- Indexes ----------------------------------------------------------------------
-- Created on the partitioned parent; Postgres automatically creates a matching
-- index on every existing partition and on every partition created later
-- (including by create_daily_partitions() in 03_partition_maintenance.sql).
-- Unlike RLS policies, index propagation to partitions IS automatic — this is
-- the contrast that made the RLS behavior above worth checking rather than
-- assuming it worked the same way.
--
-- Every btree index below leads with tenant: every query is RLS-scoped by
-- tenant, so leading with it lets the index itself narrow to the tenant's
-- rows instead of relying on RLS to filter after a broader scan. Kept to only
-- what the dashboard's Top-N/timeline and the one required alert rule need —
-- see docs/DECISIONS.md for what was cut, and why, given this table's
-- continuous-ingest write cost (every index here is updated on every INSERT).

-- Timeline + time-range filter: "this tenant's events in a time range, most recent first".
CREATE INDEX idx_events_tenant_time ON events (tenant, event_time DESC);

-- Top IP aggregation, and the required alert rule (repeated failed logins from the same src_ip).
CREATE INDEX idx_events_tenant_src_ip_time ON events (tenant, src_ip, event_time DESC);

-- Top User aggregation.
CREATE INDEX idx_events_tenant_user_time ON events (tenant, "user", event_time DESC);

-- Top Event Type aggregation.
CREATE INDEX idx_events_tenant_event_type_time ON events (tenant, event_type, event_time DESC);

-- Search inside vendor-specific fields not promoted to columns. Default
-- jsonb_ops (not jsonb_path_ops) supports both containment (@>) and
-- key-existence (?, ?|, ?&) operators, at the cost of a larger index.
CREATE INDEX idx_events_raw_gin ON events USING GIN (raw);

-- Tag-based filtering, e.g. _tags @> ARRAY['suspicious'].
CREATE INDEX idx_events_tags_gin ON events USING GIN (_tags);
