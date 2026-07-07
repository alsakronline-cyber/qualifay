"""Email system API — status + a self-test send, so email can be verified from the UI
instead of over SSH. (Per-tenant email accounts are a later step; for now this reflects
the single system-level SMTP/IMAP account.)"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.email_service import email_service
from app.api.auth import get_current_user

router = APIRouter()


@router.get("/status")
async def email_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Whether the email channel is configured, how it's set up, and today's warmup state."""
    from app.services.warmup_service import warmup_service
    tenant_id = current_user["tenant_id"]
    day = await warmup_service.email_day_of_life(tenant_id, db)
    allowed, used, cap = await warmup_service.check_email_limit(tenant_id, db)
    return {
        "configured": email_service.is_configured(),
        "from_address": email_service._from() if email_service.is_configured() else None,
        "from_name": settings.SMTP_FROM_NAME,
        "smtp_host": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "imap_host": settings.IMAP_HOST,
        "imap_poll_enabled": settings.IMAP_POLL_ENABLED,
        "warmup": {
            "day": day,
            "daily_cap": cap,
            "sent_today": used,
            "sending_allowed": allowed,
        },
    }


class TestEmailRequest(BaseModel):
    to: Optional[str] = None   # defaults to the current user's own email


@router.post("/test")
async def send_test_email(
    body: TestEmailRequest,
    current_user: dict = Depends(get_current_user),
):
    """Send a test email (to yourself by default) to confirm sending works."""
    if not email_service.is_configured():
        raise HTTPException(status_code=400, detail="Email is not configured")
    to = (body.to or current_user.get("email") or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="No recipient address")
    try:
        await email_service.send(
            to,
            "Qualifay — اختبار البريد",
            "هذه رسالة اختبار من Qualifay. نظام البريد يعمل بشكل صحيح.",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Test email failed: {e}")
    return {"sent": True, "to": to}
