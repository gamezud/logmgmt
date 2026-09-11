#!/bin/sh
# Runs automatically on first container start (docker-entrypoint-initdb.d runs
# .sh scripts directly, with the same env vars the postgres image itself sees).
#
# Creates the least-privilege application role. It is a *separate* script from
# the .sql files (rather than hardcoding CREATE ROLE ... PASSWORD in SQL) so the
# real password comes from the APP_DB_PASSWORD env var (sourced from .env, which
# is gitignored) instead of ever being written into a committed file.
#
# Both statements below are piped into psql via stdin heredoc rather than
# passed with -c. Verified empirically (against postgres:16) that psql's -c /
# -tAc command-line mode does NOT perform :'var' / :"var" substitution at all
# — only stdin input and -f script files do. An earlier version of this script
# used -tAc and got the *literal* text ":'app_user'" sent to the server,
# which fails outright. A related pitfall (also checked): substitution is
# also skipped inside dollar-quoted ($$ ... $$) blocks, so the existence
# check can't be wrapped in a plpgsql DO $$ ... $$ block either — it has to
# be a plain statement, checked from the shell.
set -eu

if [ -z "${APP_DB_USER:-}" ] || [ -z "${APP_DB_PASSWORD:-}" ]; then
  echo "01_roles.sh: APP_DB_USER and APP_DB_PASSWORD must both be set (check .env)" >&2
  exit 1
fi

existing=$(psql -tA \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v app_user="$APP_DB_USER" <<'SQL'
SELECT 1 FROM pg_roles WHERE rolname = :'app_user';
SQL
)

if [ "$existing" != "1" ]; then
  # :"app_user" substitutes as a quoted identifier, :'app_password' as a
  # quoted literal — both safe against SQL injection from the env var contents.
  psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v app_user="$APP_DB_USER" \
    -v app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
SQL
fi
