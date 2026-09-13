# samples

One sample log file per source (assignment §4, verbatim) plus two sender
scripts:

- `firewall.log`, `network.log` — raw RFC3164 syslog lines (§4.1, §4.2).
- `api.json`, `crowdstrike.json`, `aws.json`, `m365.json`, `ad.json` — the
  JSON payloads (§4.3-§4.7), unmodified.
- `send_syslog.sh` — sends the two `.log` files to a running
  `ingest/syslog_server.py` over both UDP and TCP.
- `post_logs.py` — logs in, then POSTs the JSON samples to `POST /ingest`
  (admin-only — see `docs/DECISIONS.md`). Requires the backend running
  (`make up`) and a demo admin account (see Usage below).
  
**`batch_loader.py` vs `post_logs.py`** — both load the same JSON samples
but exercise different paths. `ingest.batch_loader` (used by `make seed`)
writes straight to the database — no HTTP, no auth — for seeding demo data.
`post_logs.py` goes through the real `POST /ingest` endpoint, authenticating
first via `POST /auth/login`, which is what actually exercises JWT auth and
the admin-only role check — the path the assignment's acceptance checklist
means by "Call POST /ingest with the sample JSON."
  

## Requirements

`send_syslog.sh` needs `nc` (netcat), which is **not installed by default
on Ubuntu 22.04**:

```bash
sudo apt install -y netcat-openbsd
```

The script checks for `nc` on startup and exits with this same instruction
if it's missing, rather than failing partway through with a bare
"command not found".

## Usage

```bash
# 1. Start the syslog listener (needs `make up` first):
.venv/bin/python -m ingest.syslog_server --tenant demoA --udp-port 1514 --tcp-port 1514

# 2. In another terminal, send the syslog samples:
SYSLOG_UDP_PORT=1514 SYSLOG_TCP_PORT=1514 bash samples/send_syslog.sh

# 3. Load the JSON samples via the batch loader (or `make seed`):
.venv/bin/python -m ingest.batch_loader samples/api.json --rebase-timestamps

# 4. Create a demo admin account (one time). The password must match
#    post_logs.py's DEFAULT_PASSWORD, or pass --password to both:
.venv/bin/python -m backend.create_user --username admin_a --role admin --tenant demoA

# 5. Log in and POST the JSON samples through the real HTTP API:
.venv/bin/python samples/post_logs.py
```

`send_syslog.sh` rewrites just the date/time portion of each line to the
current UTC time before sending, and `--rebase-timestamps` shifts loaded
records' `event_time` to "now" — both leave the sample files' own content
(and each record's `raw`) untouched, but keep the *effective* timestamp
fresh enough to land in a real daily partition and stay inside the 7-day
retention window. See `docs/DECISIONS.md`.