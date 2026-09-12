#!/usr/bin/env bash
# Sends the two syslog samples over UDP and TCP using nc, not `logger` --
# `logger` regenerates its own PRI/timestamp/hostname rather than
# forwarding the exact bytes in the file, which would defeat testing our
# own RFC3164 parser against the literal sample line.
#
# The date/time portion of each line is rewritten to the current UTC time
# before sending (samples/*.log on disk stay byte-identical to the
# assignment brief) -- otherwise the fixed "Aug 20" date would eventually
# fall outside the 7-day retention window and land in events_default
# instead of a real daily partition. See docs/DECISIONS.md.
set -euo pipefail

if ! command -v nc >/dev/null 2>&1; then
  echo "send_syslog.sh: 'nc' (netcat) is required but not installed." >&2
  echo "  Ubuntu/Debian: sudo apt install -y netcat-openbsd" >&2
  exit 1
fi

HOST="${SYSLOG_HOST:-127.0.0.1}"
UDP_PORT="${SYSLOG_UDP_PORT:-1514}"
TCP_PORT="${SYSLOG_TCP_PORT:-1514}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

now_ts=$(date -u '+%b %e %H:%M:%S')

rewrite_date() {
  sed -E "s/^(<[0-9]+>)[A-Za-z]{3} +[0-9]{1,2} [0-9]{2}:[0-9]{2}:[0-9]{2} /\1${now_ts} /"
}

for f in "$SCRIPT_DIR/firewall.log" "$SCRIPT_DIR/network.log"; do
  echo "UDP -> $f"
  rewrite_date < "$f" | nc -u -w1 "$HOST" "$UDP_PORT"
  echo "TCP -> $f"
  rewrite_date < "$f" | nc -w1 "$HOST" "$TCP_PORT"
done

# Manual alternative for a quick one-off check (regenerates its own
# PRI/timestamp, so it won't exercise the RFC3164 parser the same way):
#   logger -n "$HOST" -P "$UDP_PORT" -d "some test message"
