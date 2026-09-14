# Multi-stage: build the static bundle with Node, then serve it with a small
# runtime image. VITE_API_BASE_URL must be known at build time (Vite bakes
# import.meta.env.VITE_* into the compiled JS, there's no runtime env
# mechanism in this app) — default "/api" is a relative path that works
# unchanged in both appliance and SaaS modes because both put the frontend
# and backend behind the same Caddy origin (see docs/DECISIONS.md #50/#51).
# Do NOT use this default for `npm run dev` — see frontend/.env.example for
# why that needs an absolute URL instead.
FROM node:20-alpine AS build

WORKDIR /app

# Copied separately from the rest of the source so `npm ci` only reruns when
# dependencies actually change, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Serve the built static files with Caddy rather than adding nginx as a
# second, unexplained proxy/static-server technology — Caddy is already this
# project's locked-in proxy/TLS layer (CLAUDE.md), so reusing it here keeps
# the packaging surface to one tool. This inner Caddy only does file_server;
# the outer Caddy (repo root Caddyfile) is what handles TLS/routing and
# reverse-proxies to this container.
FROM caddy:2-alpine

WORKDIR /srv

COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

# Non-root: Caddy still needs to write its own state under /data and
# /config even when only serving static files, so both must be writable by
# the new user, not just /srv.
RUN adduser -D -H frontend \
    && chown -R frontend /srv /data /config

USER frontend

# >1024 so the non-root user doesn't need CAP_NET_BIND_SERVICE.
EXPOSE 8080

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
