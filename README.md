# Log Management System

Full-stack intern assignment. See `docs/FullStack_Developer_Intern_Assignment_EN.pdf`
for the brief and `docs/DECISIONS.md` for the reasoning behind every
structural decision made while building this.

## Status

Storage, ingest, backend (auth/RBAC/RLS-scoped API), alerting, and the
frontend are all implemented. TLS/Caddy and containerized SaaS deployment
are not yet — see `frontend/README.md` and `alerting/README.md` for what
each of those two most-recently-added pieces covers, and
`docs/DECISIONS.md` for the reasoning behind every non-obvious choice.

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
make up                 # starts postgres, backend, and the alert engine; waits for healthchecks
make psql                # optional: open a psql shell (\dt to see all tables/partitions)
make install && make test   # run the full pytest suite (storage, backend, alerting)
make down                # stop the stack
```

`make partitions` manually (re)runs the daily-partition-creation and
old-partition-cleanup functions against the running container — see
`backend/db/README.md` and `docs/DECISIONS.md` for why this isn't scheduled
automatically yet.

For the frontend (not part of `docker-compose.yml` yet — see
`docs/DECISIONS.md`):

```
cd frontend && npm install && npm run dev
```

Create a demo account first (`backend/create_user.py` — see
`samples/README.md`), and see `frontend/README.md` for the pages this
covers and `alerting/README.md` for the alert engine `make up` just
started alongside `backend`.
