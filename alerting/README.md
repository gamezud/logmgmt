# alerting

The alert engine: a standalone process, separate from the FastAPI backend
(see `docs/DECISIONS.md` for why). Every `ALERT_POLL_INTERVAL_SECONDS`
(default 30), it re-evaluates the `failed_login_burst` rule for every known
tenant and inserts a row into `alerts` for anything past its rule's
cooldown, optionally POSTing a webhook.

There is exactly one rule type in this session: **≥`threshold` failed
logins from the same `src_ip` within `window_seconds`**, both
admin-configurable per tenant via `PATCH /alert-rules/{id}`
(`backend/routers/alert_rules.py`). See `docs/DECISIONS.md` for:
- why this is a scheduled poll, not a streaming/trigger-based pipeline;
- how the cooldown is designed so it suppresses duplicate alerts for one
  ongoing incident without ever suppressing a genuinely new one;
- why detection filters on `ingested_at` (this system's own arrival-time
  clock) rather than `event_time` (the source device's claimed timestamp),
  while still *reporting* `event_time` on the fired alert;
- how this process finds out which tenants exist at all with no JWT to
  read one from.

## Running

**Always invoke as a module** (`python -m alerting.engine`, not
`python alerting/engine.py`) — same reason as `ingest/README.md` /
`docs/DECISIONS.md` #22.

```bash
# needs postgres running (`make up`) and at least one alert rule configured
# via PATCH /alert-rules/{id} for a tenant that has a user account
.venv/bin/python -m alerting.engine
```

## Environment variables

- `ALERT_POLL_INTERVAL_SECONDS` (default `30`) — how often to re-evaluate.
- `ALERT_WEBHOOK_URL` (optional, unset by default) — if set, a JSON POST is
  sent here for every fired alert. Left unset, the engine still fires and
  records alerts normally; it just never attempts delivery — this is the
  default local-dev state, not an error condition.

Also needs the same `POSTGRES_*` / `APP_DB_*` variables as `backend` and
`ingest` (see `.env.example`) — it connects as `app_user`, never
`POSTGRES_USER`, same as every other write path in this project.
