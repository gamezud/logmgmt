# backend

FastAPI + Pydantic v2 app — not implemented yet (out of scope for this
session, which covers project scaffolding and the storage layer only).

The storage layer it will sit on top of already exists: see `backend/db/`.
The backend must connect to Postgres as the `app_user` role (never as
`POSTGRES_USER`) so Row-Level Security actually applies — see
`backend/db/README.md`.
