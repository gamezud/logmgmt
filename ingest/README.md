# ingest

This implements three ingest paths, all sharing the same per-source
normalizers: the syslog UDP/TCP listener, the CLI batch loader, and FastAPI
HTTP ingest (`POST /ingest`, in `backend/routers/ingest.py` — admin-only,
tenant taken only from the verified JWT claim, never from the request body,
even though the assignment's own sample payloads include one; see
`docs/DECISIONS.md` #23).

Every incoming log — regardless of source — is normalized into the single
`NormalizedEvent` model in `models.py`, which maps the common schema's
`@timestamp` field to the `events.event_time` column and flattens `cloud.*`
into `cloud_account_id`/`cloud_region`/`cloud_service` (see
`docs/DECISIONS.md` #1-#2). Unparseable input is never dropped — it's
stored as `source="unknown"` with the original payload preserved in `raw`
(see `docs/DECISIONS.md`, and `ingest/normalizers/__init__.py`).

## Running

**Always invoke both scripts with `python -m`, never as a bare file path**
(`python -m ingest.syslog_server`, not `python ingest/syslog_server.py`) —
the latter fails with `ModuleNotFoundError: No module named 'ingest'`
because Python puts the *script's own directory* on `sys.path`, not the
repo root, when run as a path. See `docs/DECISIONS.md` #22.

```bash
# Syslog listener (needs postgres running: `make up`).
# Port 514 needs root; use a high port for local testing.
.venv/bin/python -m ingest.syslog_server --tenant demoA --udp-port 1514 --tcp-port 1514

# Batch file loader (JSON or CSV).
.venv/bin/python -m ingest.batch_loader samples/api.json --rebase-timestamps
```

`--rebase-timestamps` shifts the loaded records' `event_time` to "now"
(preserving relative spacing between them) while leaving `raw` — and the
sample files on disk — byte-identical to the original payload. It exists
because the assignment's sample logs carry a fixed `2025-08-20` timestamp
that would otherwise eventually fall outside the 7-day retention window
and land in `events_default` instead of a real daily partition; see
`docs/DECISIONS.md`. Only pass it for demo/seed data, never for a real
historical log export.
