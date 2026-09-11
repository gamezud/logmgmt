# backend/db

SQL that defines the storage layer. Runs automatically as Postgres
`docker-entrypoint-initdb.d` scripts the first time the `postgres` data volume
is initialized (they do **not** re-run on every `docker compose up` — only on
a fresh volume).

## Files (run in this order, by filename)

- `01_roles.sh` — creates the `app_user` role the backend must connect as.
  A shell script (not `.sql`) so the password comes from the `APP_DB_PASSWORD`
  env var instead of being written into a committed file.
- `02_schema.sql` — the `events` table (partitioned by day on `event_time`),
  the `events_default` partition, Row-Level Security setup, grants, and
  indexes. See inline comments for the reasoning behind each choice, and
  `docs/DECISIONS.md` for the full write-up.
- `03_partition_maintenance.sql` — `create_daily_partitions()` and
  `drop_old_partitions()`, the functions behind 7-day retention. Not scheduled
  automatically; see `make partitions`.
- `04_seed_partitions.sql` — calls `create_daily_partitions()` once so the
  database is writable immediately after first startup.

## The one thing to know before touching this

**Row-Level Security policies do not propagate from the partitioned parent
table to its partitions** — unlike indexes, which do propagate automatically.
This was verified empirically against `postgres:16` (not assumed from
documentation) before writing `02_schema.sql`. Concretely:

- A query through the parent (`SELECT ... FROM events`) is filtered by the
  **parent's** policy across every partition, regardless of each partition's
  own RLS state.
- A query directly against a partition by name is governed only by *that
  partition's own* RLS state — if RLS was never enabled on it, direct access
  is a full bypass; if RLS is enabled but it has no policy, direct access
  silently returns zero rows to everyone.

So every partition needs its own copy of the same policy. `apply_tenant_rls()`
in `02_schema.sql` makes this idempotent and is called for `events_default`
there, and for every new partition inside `create_daily_partitions()` in
`03_partition_maintenance.sql`. In this project's setup this is mostly
belt-and-suspenders anyway, since `app_user` is only ever granted access on
the parent `events` table and gets a plain permission-denied error if it
tries to query a partition directly — but the policy still needs to exist for
any role/tool that *is* granted direct partition access (an admin script, a
backup tool, a future ops role).

## Connecting

- `POSTGRES_USER` (superuser) — migrations, `make psql`, admin tasks only.
  Bypasses RLS entirely; never use it from the backend application.
- `APP_DB_USER` (`app_user`) — what the backend connects as. Only has
  `SELECT, INSERT` on `events`. RLS applies to it fully.
