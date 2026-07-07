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


# ─── Multiple sending identities (Email Accounts) ─────────────

def _account_dict(a) -> dict:
    from app.services.email_account_service import account_day_of_life, account_cap
    return {
        "id": a.id,
        "from_name": a.from_name,
        "from_email": a.from_email,
        "smtp_host": a.smtp_host,
        "smtp_port": a.smtp_port,
        "smtp_user": a.smtp_user,
        "imap_host": a.imap_host,
        "imap_port": a.imap_port,
        "status": a.status,
        "paused": bool(a.paused),
        "sent_today": a.sent_today or 0,
        "warmup_day": account_day_of_life(a),
        "daily_cap": account_cap(a),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


class AccountCreate(BaseModel):
    from_email: str
    from_name: Optional[str] = None
    smtp_host: str
    smtp_port: int = 465
    smtp_user: Optional[str] = None       # defaults to from_email
    smtp_password: str
    imap_host: Optional[str] = None
    imap_port: int = 993


class AccountUpdate(BaseModel):
    from_name: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    status: Optional[str] = None
    paused: Optional[bool] = None


@router.get("/accounts")
async def list_accounts(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import EmailAccount
    from sqlalchemy import select
    rows = (await db.execute(
        select(EmailAccount).where(EmailAccount.tenant_id == current_user["tenant_id"])
        .order_by(EmailAccount.created_at.desc())
    )).scalars().all()
    return [_account_dict(a) for a in rows]


@router.post("/accounts")
async def create_account(body: AccountCreate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import EmailAccount
    from app.core.crypto import encrypt
    acc = EmailAccount(
        tenant_id=current_user["tenant_id"],
        from_email=body.from_email, from_name=body.from_name,
        smtp_host=body.smtp_host, smtp_port=body.smtp_port,
        smtp_user=body.smtp_user or body.from_email,
        smtp_password_enc=encrypt(body.smtp_password),
        imap_host=body.imap_host, imap_port=body.imap_port,
        status="active",
    )
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return _account_dict(acc)


async def _get_account(account_id, tenant_id, db):
    from app.models.models import EmailAccount
    from sqlalchemy import select, and_
    acc = (await db.execute(select(EmailAccount).where(and_(
        EmailAccount.id == account_id, EmailAccount.tenant_id == tenant_id
    )))).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, body: AccountUpdate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.core.crypto import encrypt
    acc = await _get_account(account_id, current_user["tenant_id"], db)
    data = body.dict(exclude_none=True)
    if "smtp_password" in data:
        acc.smtp_password_enc = encrypt(data.pop("smtp_password"))
    for k, v in data.items():
        setattr(acc, k, v)
    await db.commit()
    return _account_dict(acc)


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    acc = await _get_account(account_id, current_user["tenant_id"], db)
    await db.delete(acc)
    await db.commit()
    return {"deleted": True}


@router.post("/accounts/{account_id}/test")
async def test_account(account_id: str, body: TestEmailRequest, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    acc = await _get_account(account_id, current_user["tenant_id"], db)
    to = (body.to or current_user.get("email") or acc.from_email).strip()
    try:
        await email_service.send_via_account(acc, to, "Qualifay — اختبار الحساب", "هذا الحساب يعمل بشكل صحيح.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Test failed: {e}")
    return {"sent": True, "to": to}
