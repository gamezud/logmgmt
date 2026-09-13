-- users: backend authentication accounts (POST /auth/login). Deliberately
-- separate from the tenant-isolated event-data model in 02_schema.sql — see
-- docs/DECISIONS.md for the full write-up of why this table has NO
-- Row-Level Security, unlike every other table in this schema.
--
-- Short version: POST /auth/login receives only {username, password} — no
-- tenant, by the same client-can-never-supply-tenant rule that governs every
-- other endpoint (see CLAUDE.md). So the login lookup has to find the user's
-- tenant FROM the username, before app.tenant is known — RLS's fail-closed
-- behavior (docs/DECISIONS.md #7) would make that lookup always return zero
-- rows if this table had the same tenant_isolation policy as `events`. This
-- table is instead treated as an internal auth table outside the
-- tenant-isolated model, queried only by the login code path (there is no
-- GET /users endpoint in this session).

CREATE TABLE users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Globally unique (not unique-per-tenant): this is what makes
    -- "look up a user by username alone, with no tenant supplied by the
    -- client" unambiguous. See docs/DECISIONS.md.
    username      text NOT NULL UNIQUE,

    -- bcrypt's own encoded output already carries the salt and cost factor,
    -- so no separate salt column is needed. See docs/DECISIONS.md for why
    -- bcrypt (the `bcrypt` package) over passlib/argon2.
    password_hash text NOT NULL,

    -- Locked to exactly two roles per CLAUDE.md ("roles: admin กับ viewer").
    role          text NOT NULL CHECK (role IN ('admin', 'viewer')),

    -- The tenant this account belongs to. Baked into the JWT at login time —
    -- never supplied by the client on any request. Same CHECK as
    -- events.tenant, for the same reason (see 02_schema.sql).
    tenant        text NOT NULL CHECK (tenant <> ''),

    created_at    timestamptz NOT NULL DEFAULT now()
);

-- No ENABLE ROW LEVEL SECURITY here — see the file-level comment above.

-- app_user needs SELECT (login lookup) and INSERT (backend/create_user.py,
-- the operator CLI used to create demo/real accounts — there is no HTTP
-- endpoint that creates users in this session). No UPDATE/DELETE grant yet:
-- nothing in this session needs to change or remove an account.
GRANT SELECT, INSERT ON users TO app_user;
