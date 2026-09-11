-- Partition lifecycle for events: pre-create daily partitions ahead of time,
-- and drop partitions older than the retention window.
--
-- Hand-written SQL functions rather than pg_partman/pg_cron — keeps
-- docker-compose.yml to the plain postgres:16 image + init scripts only (this
-- session's constraint), at the cost of a less automated lifecycle than a
-- dedicated extension. See docs/DECISIONS.md.
--
-- Nothing in this file schedules these functions to run automatically —
-- `make partitions` (see Makefile) invokes them manually/from an external
-- cron; wiring up automatic scheduling is out of scope for this storage-only
-- session.

-- Creates events_YYYY_MM_DD partitions for [today - days_back, today + days_ahead],
-- inclusive on both ends. Idempotent: safe to call repeatedly (IF NOT EXISTS),
-- e.g. daily from cron to keep the lookahead window rolling forward.
--
-- The lookahead should stay generous: every day without a pre-created
-- partition means events land in events_default instead, and every future
-- CREATE TABLE ... PARTITION OF here has to scan events_default (to prove it
-- holds no rows belonging to the new range) under a heavy lock — the more
-- that accumulates there, the slower and more disruptive each of these calls
-- gets. See docs/DECISIONS.md.
CREATE FUNCTION create_daily_partitions(days_back int DEFAULT 1, days_ahead int DEFAULT 7)
RETURNS void AS $$
DECLARE
    day date;
    partition_name text;
BEGIN
    FOR day IN
        SELECT generate_series(CURRENT_DATE - days_back, CURRENT_DATE + days_ahead, interval '1 day')::date
    LOOP
        partition_name := 'events_' || to_char(day, 'YYYY_MM_DD');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF events FOR VALUES FROM (%L) TO (%L)',
            partition_name, day, day + 1
        );

        -- Indexes on the parent propagate to new partitions automatically,
        -- but RLS policies do not (verified empirically — see the comment
        -- above apply_tenant_rls in 02_schema.sql). Without this, a new
        -- partition queried directly by name would either fully bypass
        -- tenant isolation (if RLS were left disabled) or silently return
        -- zero rows to everyone (if enabled with no policy).
        PERFORM apply_tenant_rls(partition_name);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Drops events_YYYY_MM_DD partitions whose date is older than
-- (today - retain_days). Identifies partitions by parsing the naming
-- convention rather than introspecting pg_partition bounds — simpler to read
-- (CLAUDE.md rule 3), at the cost of relying on partitions always being named
-- this way (only this function and create_daily_partitions create them, so
-- that holds in practice).
--
-- DROP TABLE on a partition is a metadata-only operation regardless of how
-- many rows it holds: no per-row scan, no WAL proportional to data volume, no
-- VACUUM needed afterwards, and only the dropped partition is locked — unlike
-- DELETE FROM events WHERE event_time < X, which would need to be. See
-- docs/DECISIONS.md.
CREATE FUNCTION drop_old_partitions(retain_days int DEFAULT 7)
RETURNS void AS $$
DECLARE
    rec record;
    partition_date date;
BEGIN
    FOR rec IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename ~ '^events_\d{4}_\d{2}_\d{2}$'
    LOOP
        partition_date := to_date(substring(rec.tablename FROM 'events_(\d{4}_\d{2}_\d{2})'), 'YYYY_MM_DD');

        IF partition_date < CURRENT_DATE - retain_days THEN
            EXECUTE format('DROP TABLE IF EXISTS %I', rec.tablename);
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
