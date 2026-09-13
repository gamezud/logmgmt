"""Webhook delivery for fired alerts. A single global `ALERT_WEBHOOK_URL`
env var (not a per-tenant DB column) — matches the assignment's own wording
("ส่ง webhook ได้ ตั้งค่าผ่าน env var") and avoids building rule-config UI
for a feature (per-tenant webhook destinations) nothing has asked for yet.
See docs/DECISIONS.md.

Unset ALERT_WEBHOOK_URL is the expected default (a fresh `make up` has no
webhook configured — .env.example doesn't set one), not an error path:
alerting/engine.py checks for a configured URL before ever calling
send_webhook, so an unconfigured deployment alerts normally, it just never
attempts delivery.
"""
import logging

import httpx

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0


async def send_webhook(url: str, payload: dict) -> bool:
    """POSTs `payload` as JSON to `url`. Returns True on a 2xx response,
    False on any error — never raises. No retry: a failed delivery is
    logged and the caller leaves alerts.webhook_sent_at NULL, but the
    alert row itself is already durably stored and visible via GET /alerts
    regardless of whether this call succeeds."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return True
    except Exception:
        log.exception("webhook delivery to %s failed", url)
        return False
