# SaaS / public deployment

Deploys the stack on a cloud VM, reachable over the public internet through Caddy.
See `docs/architecture.md` for how the pieces fit together and `docs/DECISIONS.md`
for the reasoning behind each choice below.

**Before you deploy publicly, generate fresh secrets.** Never reuse `.env` values,
seeded demo passwords, or any credential from local/appliance development on a
deployment reachable from the internet.

There are two cases, depending on whether you have a domain pointed at the VM, plus
a note on firewalling that applies to both.

## Case 1 — you have a domain (recommended)

Uses `Caddyfile.saas`, which gets automatic HTTPS via Let's Encrypt.

**Before starting Caddy:** the domain's DNS A record must already resolve to the
VM's public IP — Let's Encrypt's HTTP-01 challenge needs to reach the VM at that
hostname to issue the certificate. Port 80 must also be reachable from the internet
for that challenge to complete (443 is used for the site itself afterward).

In `.env`, set `SITE_DOMAIN` (your domain), `ACME_EMAIL` (for Let's Encrypt
notices), and a freshly generated `JWT_SECRET_KEY` (see
`docs/setup_appliance.md` step 3 for the command).

```
docker compose -f docker-compose.yml -f docker-compose.saas.yml up -d --build --wait
```

Verify `backend` and `postgres` have no ports published to the host:

```
docker compose -f docker-compose.yml -f docker-compose.saas.yml ps
```

Only `caddy` should show published ports (80, 443).

## Case 2 — no domain, bare IP only

Uses `Caddyfile.saas-ip`. **This serves plain HTTP, not HTTPS.** `tls internal`
(Caddy's self-signed-cert mode) was tried here and fails against a bare IP target —
TLS's SNI extension only carries hostnames, so clients connecting to an IP literal
send no SNI, and Caddy can't match the connection to a certificate. This is a
structural limitation of TLS-via-SNI against bare IPs, not a configuration mistake,
and it's documented in full — including that TLS was independently proven working
on appliance mode — in `docs/DECISIONS.md` #55. If you can get a domain, use Case 1
instead; `Caddyfile.saas` needs no code changes to work once DNS is pointed at it.

Because of this, treat any bare-IP deployment as demo-only:

- Traffic is unencrypted, including the JWT and the login password sent to
  `POST /auth/login`. Use a throwaway account created just for the demo — never
  real credentials or real data.
- Delete the VM once the demo is done. Don't leave a bare-IP deployment running
  as a permanent public endpoint.

In `.env`, set `SITE_ADDRESS` to the VM's public IP, plus a freshly generated
`JWT_SECRET_KEY`.

```
docker compose -f docker-compose.yml -f docker-compose.saas.yml -f docker-compose.saas-ip.yml up -d --build --wait
```

Verify the same way as Case 1:

```
docker compose -f docker-compose.yml -f docker-compose.saas.yml -f docker-compose.saas-ip.yml ps
```

`backend`/`postgres` should still show no published ports, even though Caddy is
only using port 80 (not 443) for this site.

## A note on `ufw`: second layer, not the only one

`docs/DECISIONS.md` #54 covers this in detail. The short version: `backend` and
`postgres` are never published to the host in `docker-compose.yml`,
`docker-compose.saas.yml`, or `docker-compose.saas-ip.yml` — only
`docker-compose.dev.yml` does that (for local appliance/dev debugging), and that
file is never part of any SaaS command above. So a host firewall like `ufw` is
defense-in-depth against some future service accidentally binding a host port, not
the mechanism this isolation actually depends on. A reasonable baseline, if you use
one:

```
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw default deny incoming
sudo ufw enable
```
