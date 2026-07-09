"""Outbound webhooks — fan out domain events to tenant-configured URLs (n8n, Zapier,
custom). Delivery runs in Celery so the request path never blocks on a slow endpoint."""
import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime

import httpx
from sqlalchemy import select

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro
    return asyncio.run(_wrapped())


def _subscribed(events, event: str) -> bool:
    if not events:
        return False
    return "*" in events or event in events


async def _deliver(endpoint, event: str, payload: dict):
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
