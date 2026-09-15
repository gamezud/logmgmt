# Appliance / local setup

Runs the whole stack (Postgres, backend, frontend, Caddy, alert engine) on a single
machine with self-signed TLS. Tested on Ubuntu 22.04 with Docker, Python 3.10, and
Node 20 — see `docs/architecture.md` for how the pieces fit together and
`docs/DECISIONS.md` for the reasoning behind each choice below.

## 1. Prerequisites

- Docker + Docker Compose v2 (`docker compose version`)
- `git`

## 2. Clone and configure

```
git clone <repo-url> logmgmt
cd logmgmt
cp .env.example .env
```

## 3. Generate a real `JWT_SECRET_KEY`

```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into `.env` as `JWT_SECRET_KEY=...`. This step is not optional:
`backend/config.py`'s `validate_jwt_secret` runs at import time, before the backend
accepts any request, and raises `RuntimeError` — crashing the container on startup,
not silently running insecurely — if `JWT_SECRET_KEY` is unset or still equal to the
placeholder shipped in `.env.example` (`changeme-generate-a-real-secret`). A
guessable secret would let anyone forge a validly-signed JWT for any tenant or role,
which defeats every Row-Level Security policy in the system (see
`docs/architecture.md`'s tenant model section and `docs/DECISIONS.md` #28).

## 4. Start the stack

```
make up
```

This runs `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
--wait`, starting `postgres`, `backend`, `frontend`, `caddy`, and the alert engine,
and waits for their healthchecks. Note that `docker-compose.dev.yml` is the *only*
compose file that publishes `backend`'s port 8000 and `postgres`'s port 5432
directly to the host — for local debugging only (`make psql`, calling the API
directly without going through Caddy). Production/SaaS deployments never include
this file — see `docs/setup_saas.md`.

## 5. Install dependencies, create users, and load sample data

```
make install
```

Creates `.venv` and installs the dependencies needed to run backend scripts and
tests from the host. Every script below is invoked with `python -m`, not as a bare
script path — running `backend/create_user.py` directly instead of
`-m backend.create_user` breaks its package-relative imports (see
`docs/DECISIONS.md` #22).

```
.venv/bin/python -m backend.create_user --username admin_a --role admin --tenant demoA
.venv/bin/python -m backend.create_user --username viewer_a --role viewer --tenant demoA
```

Leave out `--password` and you'll be prompted for it interactively instead — do
that rather than passing `--password` on the command line, so the password never
ends up sitting in your shell history.

```
make seed
```

Loads `samples/*.json` into `demoA` (and the other sample tenants) via the CLI
batch loader.

## 6. Open the app

Visit `https://localhost/`. Caddy terminates TLS on port 443 using its own local CA
(`tls internal` in the appliance `Caddyfile`, bound to `localhost`/`127.0.0.1`) —
your browser will warn that the certificate isn't trusted, because it wasn't issued
by a public CA. This is expected here; click through it:

- **Chrome:** "Your connection is not private" → click "Advanced" → "Proceed to
  localhost (unsafe)".
- **Firefox:** "Warning: Potential Security Risk Ahead" → click "Advanced..." →
  "Accept the Risk and Continue".

This is a different situation from the bare-IP SaaS case documented in
`docs/DECISIONS.md` #55 and `docs/setup_saas.md`: here the TLS handshake actually
succeeds (it's just an untrusted, self-signed cert), rather than failing outright.

## 7. Run tests

```
make test
```

## 8. Stop the stack

```
make down
```
