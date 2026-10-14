"""Email system API — status + a self-test send, so email can be verified from the UI
instead of over SSH. (Per-tenant email accounts are a later step; for now this reflects
the single system-level SMTP/IMAP account.)"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.email_service import email_service
from app.api.auth import get_current_user, require_admin

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
    require_admin(current_user)   # mailbox SMTP/IMAP credentials — admin only
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
    require_admin(current_user)
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
    require_admin(current_user)
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


# ─── Email reports: sent / opened / bounced / replied / unsubscribed ───────

def _range(days: int):
    from datetime import datetime, timedelta
    days = max(1, min(int(days or 30), 365))
    return days, datetime.utcnow() - timedelta(days=days)


@router.get("/analytics")
async def email_analytics(days: int = 30, current_user: dict = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Totals, rates and a per-day series for this tenant's cold emails over `days`."""
    from sqlalchemy import text
    from app.models.models import Tenant
    from app.services.email_tracking import tracking_enabled
    days, since = _range(days)
    p = {"t": current_user["tenant_id"], "s": since}
    row = (await db.execute(text("""
        SELECT count(*), count(*) FILTER (WHERE tracked), count(opened_at), count(bounced_at),
               count(replied_at), count(unsubscribed_at),
               count(*) FILTER (WHERE tracked AND bounced_at IS NULL)
        FROM email_sends WHERE tenant_id = :t AND sent_at >= :s"""), p)).one()
    sent, tracked, opened, bounced, replied, unsub, tracked_delivered = row
    delivered = sent - bounced

    def pct(n, d):
        return round(100 * n / d, 1) if d else 0.0

    # Bucket by the Cairo calendar day (sent_at is naive UTC; Postgres handles Egypt's DST).
    series = (await db.execute(text("""
        SELECT to_char(((sent_at AT TIME ZONE 'UTC') AT TIME ZONE 'Africa/Cairo')::date, 'YYYY-MM-DD') AS d,
               count(*), count(opened_at), count(bounced_at), count(replied_at), count(unsubscribed_at)
        FROM email_sends WHERE tenant_id = :t AND sent_at >= :s
        GROUP BY 1 ORDER BY 1"""), p)).all()
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user["tenant_id"]))).scalar_one_or_none()
    return {
        "days": days,
        "totals": {"sent": sent, "delivered": delivered, "opened": opened, "bounced": bounced,
                   "replied": replied, "unsubscribed": unsub, "tracked": tracked},
        "rates": {"open": pct(opened, tracked_delivered), "bounce": pct(bounced, sent),
                  "reply": pct(replied, delivered), "unsubscribe": pct(unsub, delivered)},
        "series": [{"day": d, "sent": s, "opened": o, "bounced": b, "replied": r, "unsubscribed": u}
                   for d, s, o, b, r, u in series],
        "tracking_enabled": tracking_enabled(tenant),
    }


@router.get("/sends")
async def email_sends(days: int = 30, status: Optional[str] = None, search: Optional[str] = None,
                      page: int = 1, page_size: int = 25,
                      current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The individual emails behind the analytics, newest first, filterable by outcome."""
    from sqlalchemy import func, or_
    from app.models.models import EmailSend, Lead
    days, since = _range(days)
    page, page_size = max(1, page), max(1, min(page_size, 100))
    q = (select(EmailSend, Lead.company, Lead.name)
         .outerjoin(Lead, Lead.id == EmailSend.lead_id)
         .where(EmailSend.tenant_id == current_user["tenant_id"], EmailSend.sent_at >= since))
    if status == "opened":
        q = q.where(EmailSend.opened_at.isnot(None))
    elif status == "not_opened":
        q = q.where(EmailSend.opened_at.is_(None), EmailSend.bounced_at.is_(None))
    elif status in ("bounced", "replied", "unsubscribed"):
        q = q.where(getattr(EmailSend, f"{status}_at").isnot(None))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(EmailSend.to_email.ilike(like), EmailSend.subject.ilike(like),
                        Lead.company.ilike(like), Lead.name.ilike(like)))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    rows = (await db.execute(q.order_by(EmailSend.sent_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).all()
    iso = lambda d: d.isoformat() + "Z" if d else None  # noqa: E731 — stored as naive UTC
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "id": s.id, "lead_id": s.lead_id, "company": company, "name": name,
            "to_email": s.to_email, "subject": s.subject, "source": s.source, "tracked": s.tracked,
            "sent_at": iso(s.sent_at), "opened_at": iso(s.opened_at), "open_count": s.open_count,
            "bounced_at": iso(s.bounced_at), "replied_at": iso(s.replied_at),
            "unsubscribed_at": iso(s.unsubscribed_at),
        } for s, company, name in rows],
    }


class TrackingToggle(BaseModel):
    enabled: bool


@router.put("/tracking")
async def set_open_tracking(body: TrackingToggle, current_user: dict = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Tenant admins turn open tracking (the HTML part + pixel) on or off for future emails."""
    from app.models.models import Tenant
    require_admin(current_user)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user["tenant_id"]))).scalar_one()
    tenant.tenant_profile = {**(tenant.tenant_profile or {}), "track_email_opens": body.enabled}
    await db.commit()
    return {"tracking_enabled": body.enabled}
