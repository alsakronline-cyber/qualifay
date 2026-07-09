"""Webhook endpoint management — tenants register URLs (n8n/Zapier/custom) and pick
which events fan out to them. Admin-only writes; delivery is handled by webhook_tasks."""
import secrets as _secrets
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.api.auth import get_current_user, require_admin as _require_admin

router = APIRouter()

# The events a tenant can subscribe to. "*" subscribes to everything.
AVAILABLE_EVENTS = [
    "lead.created", "lead.approved", "lead.rejected", "lead.stage_changed",
    "conversation.replied", "message.received",
    "flow.submitted", "booking.created", "sequence.completed",
]


def _w(w) -> dict:
    return {
        "id": w.id, "url": w.url, "events": w.events or [], "active": w.active,
        "description": w.description, "last_status": w.last_status,
        "last_fired_at": w.last_fired_at.isoformat() if w.last_fired_at else None,
        "failure_count": w.failure_count or 0,
        "has_secret": bool(w.secret),
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


class WebhookIn(BaseModel):
    url: str
    events: List[str] = ["*"]
    description: Optional[str] = None
    active: bool = True


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    description: Optional[str] = None
    active: Optional[bool] = None


@router.get("/events")
async def available_events(current_user: dict = Depends(get_current_user)):
    return {"events": AVAILABLE_EVENTS}


@router.get("")
@router.get("/")
async def list_webhooks(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import WebhookEndpoint
    rows = (await db.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.tenant_id == current_user["tenant_id"]).order_by(WebhookEndpoint.created_at.desc())
    )).scalars().all()
    return [_w(w) for w in rows]


@router.post("")
@router.post("/")
async def create_webhook(body: WebhookIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    from app.models.models import WebhookEndpoint
    from app.workers.webhook_tasks import assert_safe_url, UnsafeWebhookURL
    try:
        assert_safe_url(body.url.strip())
    except UnsafeWebhookURL as e:
        raise HTTPException(status_code=400, detail=f"Unsafe webhook URL: {e}")
    w = WebhookEndpoint(
        tenant_id=current_user["tenant_id"], url=body.url.strip(),
        events=body.events or ["*"], description=body.description,
        active=body.active, secret=_secrets.token_hex(24),
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)
    # Return the secret once on creation so the user can configure signature verification.
    out = _w(w)
    out["secret"] = w.secret
    return out


async def _get(wid, tenant_id, db):
    from app.models.models import WebhookEndpoint
    w = (await db.execute(select(WebhookEndpoint).where(and_(
        WebhookEndpoint.id == wid, WebhookEndpoint.tenant_id == tenant_id)))).scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return w


@router.patch("/{wid}")
async def update_webhook(wid: str, body: WebhookUpdate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    w = await _get(wid, current_user["tenant_id"], db)
    if body.url is not None:
        from app.workers.webhook_tasks import assert_safe_url, UnsafeWebhookURL
        try:
            assert_safe_url(body.url.strip())
        except UnsafeWebhookURL as e:
            raise HTTPException(status_code=400, detail=f"Unsafe webhook URL: {e}")
        w.url = body.url.strip()
    if body.events is not None:
        w.events = body.events
    if body.description is not None:
        w.description = body.description
    if body.active is not None:
        w.active = body.active
        if body.active:
            w.failure_count = 0  # re-enabling clears the failure streak
    await db.commit()
    return _w(w)


@router.delete("/{wid}")
async def delete_webhook(wid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    w = await _get(wid, current_user["tenant_id"], db)
    await db.delete(w)
    await db.commit()
    return {"deleted": True}


@router.post("/{wid}/test")
async def test_webhook(wid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    await _get(wid, current_user["tenant_id"], db)
    from app.workers.webhook_tasks import emit
    emit(current_user["tenant_id"], "webhook.test", {"message": "Qualifay test event", "webhook_id": wid})
    return {"queued": True}
