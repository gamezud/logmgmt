# ingest

Python asyncio syslog (UDP+TCP 514), FastAPI HTTP ingest, and the CLI batch
loader — not implemented yet (out of scope for this session, which covers
project scaffolding and the storage layer only).

Whatever normalizes incoming logs here maps the common schema's `@timestamp`
field to the `events.event_time` column — see `docs/DECISIONS.md`.
