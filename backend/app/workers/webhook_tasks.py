"""Outbound webhooks — fan out domain events to tenant-configured URLs (n8n, Zapier,
custom). Delivery runs in Celery so the request path never blocks on a slow endpoint."""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class UnsafeWebhookURL(ValueError):
    """Raised when a webhook target resolves to a private/internal address (SSRF guard)."""


def assert_safe_url(url: str):
    """Reject anything that isn't a plain http(s) URL resolving to a public address.

    The backend runs on the host network and can reach internal services (Postgres,
    Redis, Qdrant, n8n, MinIO, cloud metadata at 169.254.169.254), so a webhook target
    must never point inward. Resolve the host and check every returned address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeWebhookURL("URL must use http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeWebhookURL("URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeWebhookURL(f"could not resolve host: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise UnsafeWebhookURL(f"host resolves to a non-public address ({ip})")


from app.workers._loop import run_async


def _subscribed(events, event: str) -> bool:
    if not events:
        return False
    return "*" in events or event in events


async def _deliver(endpoint, event: str, payload: dict):
    assert_safe_url(endpoint.url)  # SSRF guard — re-checked at send time, not just on create
    body = json.dumps({"event": event, "data": payload, "sent_at": datetime.utcnow().isoformat()},
                      ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Qualifay-Event": event}
    if endpoint.secret:
        sig = hmac.new(endpoint.secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Qualifay-Signature"] = f"sha256={sig}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(endpoint.url, content=body, headers=headers)
        return resp.status_code


@celery_app.task(name="webhooks.dispatch")
def dispatch_event(tenant_id: str, event: str, payload: dict):
    """Deliver one event to every active, subscribed endpoint for a tenant."""
    return run_async(_dispatch(tenant_id, event, payload))


async def _dispatch(tenant_id: str, event: str, payload: dict):
    from app.core.database import AsyncSessionLocal
    from app.models.models import WebhookEndpoint

    async with AsyncSessionLocal() as db:
        endpoints = (await db.execute(select(WebhookEndpoint).where(
            WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.active == True  # noqa: E712
        ))).scalars().all()

        delivered = 0
        for ep in endpoints:
            if not _subscribed(ep.events or [], event):
                continue
            try:
                status = await _deliver(ep, event, payload)
                ep.last_status = status
                ep.failure_count = 0 if 200 <= status < 300 else (ep.failure_count or 0) + 1
                delivered += 1
            except Exception as e:  # network/timeout — record and keep going
                logger.warning("webhook delivery failed %s: %s", ep.url, e)
                ep.last_status = 0
                ep.failure_count = (ep.failure_count or 0) + 1
            ep.last_fired_at = datetime.utcnow()
            # Auto-disable an endpoint that keeps failing so we stop hammering dead URLs.
            if (ep.failure_count or 0) >= 15:
                ep.active = False
        await db.commit()
        return {"event": event, "delivered": delivered}


def emit(tenant_id: str, event: str, payload: dict):
    """Fire-and-forget helper callable from anywhere (API or workers)."""
    try:
        dispatch_event.delay(tenant_id, event, payload)
    except Exception as e:  # broker down — never break the caller over a webhook
        logger.warning("could not queue webhook %s: %s", event, e)
