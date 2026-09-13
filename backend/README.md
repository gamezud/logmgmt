# backend

FastAPI + Pydantic v2 HTTP API: ingest, search, dashboard stats, and JWT
auth. Sits on top of the storage layer in `backend/db/` — see
`backend/db/README.md` for the schema/RLS this all depends on. See
`docs/DECISIONS.md` for the reasoning behind every non-obvious choice below.

## Endpoints

- `POST /auth/login` — `{"username", "password"}` → JWT (claims: `sub`,
  `role`, `tenant`). `GET /auth/me` — decodes the caller's own token.
- `POST /ingest` — **admin-only**. Body is the assignment's common-schema
  JSON (§4.3-4.7); any `"tenant"` field in the body is ignored — the stored
  tenant is always the caller's JWT claim, never client input.
- `GET /search` — filter by `start_time`/`end_time`/`source`/`event_type`/
  `user`/`src_ip`, paginate with `limit`/`offset`.
- `GET /stats/top?field=ip|user|event_type` and `GET /stats/timeline?interval=minute|hour|day`.
- `GET /health` — no auth; checks DB connectivity for docker-compose/cloud
  healthchecks, reveals nothing else.

`/search` and `/stats/*` accept both `admin` and `viewer` roles (read-only
for viewer); `/ingest` requires `admin`.

## Running

Requires Postgres already running (`make up`) and a real `.env` (copy
`.env.example`, then set `JWT_SECRET_KEY` — the backend refuses to start on
the committed placeholder value, see `backend/config.py`).

```bash
# Create a demo account (prompts for a password if --password is omitted):
.venv/bin/python -m backend.create_user --username admin_a --role admin --tenant demoA

# Run the API locally:
.venv/bin/uvicorn backend.main:app --reload
```

Or via docker-compose: `make up` builds and starts the `backend` service
alongside `postgres`.

## Connecting to Postgres

Connects as `app_user` (`APP_DB_USER`/`APP_DB_PASSWORD`) only, never
`POSTGRES_USER` — `POSTGRES_USER` is a superuser and superusers always
bypass Row-Level Security, which would silently defeat tenant isolation.
See `backend/db/README.md`.

Per-request tenant scoping (`backend/db.py`'s `get_tenant_conn`) uses a
connection pool (`psycopg_pool.AsyncConnectionPool`) with
`set_config('app.tenant', ..., true)` run inside a transaction held open
for the whole request — see `docs/DECISIONS.md` for why this is safe
against leaking one request's tenant into another request that later
reuses the same pooled connection, and the accepted tradeoff of holding a
pool slot for the full request duration.
