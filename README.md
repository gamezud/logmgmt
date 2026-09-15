# Log Management System

Full-stack intern assignment. See `docs/FullStack_Developer_Intern_Assignment_EN.pdf`
for the brief and `docs/DECISIONS.md` for the reasoning behind every
structural decision made while building this.

## Status

Storage, ingest, backend (auth/RBAC/RLS-scoped API), alerting, the frontend,
and TLS/Caddy + containerized deployment (appliance mode, and both SaaS
modes — real domain, and bare-IP with the HTTP-only caveat documented in
`docs/DECISIONS.md` #55) are all implemented. See `docs/architecture.md`
for the system diagram and tenant-isolation model, `docs/setup_appliance.md`
and `docs/setup_saas.md` for how to run each mode, and `docs/DECISIONS.md`
for the reasoning behind every non-obvious choice.

## Layout

```
backend/db/     PostgreSQL schema, partitioning, RLS, alert_rules/alerts (implemented)
backend/        FastAPI app: auth, RBAC, /search, /stats, /ingest, /alert-rules, /alerts (implemented)
alerting/       Scheduled alert engine — a separate process from backend (implemented)
frontend/       React + Vite + Recharts dashboard: Login/Dashboard/Search/Alerts (implemented)
ingest/         Syslog/HTTP/CLI ingest (implemented)
samples/        Sample logs + sender scripts (implemented)
tests/          pytest — storage, backend, and alerting
docs/           Assignment brief + docs/DECISIONS.md
```

## Getting started

```
cp .env.example .env    # fill in real values for local dev; .env is gitignored
make up                 # docker compose -f docker-compose.yml -f docker-compose.dev.yml up --wait
                         # starts postgres, backend, frontend, caddy, and the alert engine
make psql                # optional: open a psql shell (\dt to see all tables/partitions)
make install && make test   # run the full pytest suite (storage, backend, alerting)
make down                # stop the stack
```

`docker-compose.dev.yml` is the only compose file that publishes `backend`'s
port 8000 and `postgres`'s port 5432 directly to the host — for local
debugging only (`make psql`, calling the API without going through Caddy).
See `docs/setup_saas.md` for why production/SaaS compose chains never do
this. See `docs/setup_appliance.md` for the full appliance walkthrough,
including generating `JWT_SECRET_KEY` and creating a user.

`make partitions` manually (re)runs the daily-partition-creation and
old-partition-cleanup functions against the running container — see
`backend/db/README.md` and `docs/DECISIONS.md` for why this isn't scheduled
automatically yet.

For frontend-only iteration (hot reload, without rebuilding the container —
`make up` already starts a built frontend container alongside Caddy):

```
cd frontend && npm install && npm run dev
```

Create a demo account first (`.venv/bin/python -m backend.create_user` — see
`docs/setup_appliance.md`), and see `frontend/README.md` for the pages this
covers and `alerting/README.md` for the alert engine `make up` starts
alongside `backend`.
