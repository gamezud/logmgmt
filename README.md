# Log Management System

Full-stack intern assignment. See `docs/FullStack_Developer_Intern_Assignment_EN.pdf`
for the brief and `docs/DECISIONS.md` for the reasoning behind every
structural decision made while building this.

## Status

This repo currently implements **project scaffolding + the storage layer
only**: the `events` table (daily partitioning, Row-Level Security,
multi-tenant isolation) and the minimal `docker-compose.yml` needed to run
Postgres. Backend, frontend, and ingest are not implemented yet — see the
`README.md` in each of those folders.

## Layout

```
backend/db/     PostgreSQL schema, partitioning, and RLS (implemented)
backend/        FastAPI app (not yet implemented)
frontend/       React dashboard (not yet implemented)
ingest/         Syslog/HTTP/CLI ingest (not yet implemented)
samples/        Sample logs + sender scripts (not yet implemented)
tests/          pytest — currently covers the storage layer only
docs/           Assignment brief + docs/DECISIONS.md
```

## Getting started

```
cp .env.example .env    # fill in real values for local dev; .env is gitignored
make up                 # starts postgres, waits for the healthcheck
make psql                # optional: open a psql shell (\dt events* to see partitions)
make install && make test   # run the pytest storage-layer tests
make down                # stop the stack
```

`make partitions` manually (re)runs the daily-partition-creation and
old-partition-cleanup functions against the running container — see
`backend/db/README.md` and `docs/DECISIONS.md` for why this isn't scheduled
automatically yet.
