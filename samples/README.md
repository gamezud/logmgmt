# samples

One sample log file per source (assignment §4, verbatim) plus two sender
scripts:

- `firewall.log`, `network.log` — raw RFC3164 syslog lines (§4.1, §4.2).
- `api.json`, `crowdstrike.json`, `aws.json`, `m365.json`, `ad.json` — the
  JSON payloads (§4.3-§4.7), unmodified.
- `send_syslog.sh` — sends the two `.log` files to a running
  `ingest/syslog_server.py` over both UDP and TCP.
- `post_logs.py` — POSTs the JSON samples to a `POST /ingest` HTTP
  endpoint. **This targets a future FastAPI backend that does not exist
  yet in this session** — running it now fails with connection-refused, by
  design; it's included because the assignment's deliverables (§6) ask for
  it alongside `send_syslog.sh`.

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
```

`send_syslog.sh` rewrites just the date/time portion of each line to the
current UTC time before sending, and `--rebase-timestamps` shifts loaded
records' `event_time` to "now" — both leave the sample files' own content
(and each record's `raw`) untouched, but keep the *effective* timestamp
fresh enough to land in a real daily partition and stay inside the 7-day
retention window. See `docs/DECISIONS.md`.
