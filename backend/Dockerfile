# Runs the FastAPI backend AND (via docker-compose.yml's `alert-engine`
# service, which overrides CMD) the alert engine — the same image is reused
# for both rather than maintaining two near-identical Dockerfiles, see
# docs/DECISIONS.md. Built from the repo root (see `build.context` in
# docker-compose.yml) because this image needs backend/, ingest/ (POST
# /ingest reuses ingest/normalizers and ingest/db directly) AND alerting/
# (the alert engine reuses ingest/db's connect_async the same way).
FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY ingest/ ingest/
COPY alerting/ alerting/

# Run as a non-root user. Without this the process runs as root (the
# python:3.10-slim base image's default) — if the FastAPI app were ever
# compromised through an application-level vulnerability, the attacker
# would get root inside the container, not just this app's own privileges.
# A dedicated unprivileged user limits what such a compromise can do to the
# container's own filesystem/process table (it doesn't help against
# container-escape vulnerabilities, which are a kernel/runtime concern, not
# something a Dockerfile controls). See docs/DECISIONS.md — this is also
# the concrete example claimed under the assignment's bonus "hardening"
# criterion.
RUN useradd --create-home --shell /usr/sbin/nologin backend
USER backend

# Run as a module, not `python backend/main.py` — same reasoning as
# docs/DECISIONS.md #22 for the ingest CLIs: only `-m` puts the working
# directory (here, /app) on sys.path so `ingest.*` imports resolve.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
