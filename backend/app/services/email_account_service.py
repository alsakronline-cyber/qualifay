"""Email account rotation — picks which sending identity to use, respecting each
account's independent warmup ramp and daily cap, and spreading volume (least-used first)."""
from datetime import datetime, date

from sqlalchemy import select, update

from app.services.warmup_service import email_cap_for_day


def account_day_of_life(account) -> int:
    if not account.email_started_at:
        return 1
    return (date.today() - account.email_started_at.date()).days + 1


def account_cap(account) -> int:
    return email_cap_for_day(account_day_of_life(account))


async def pick_account(tenant_id: str, db):
    """Return an active, non-paused account still under its daily cap (least-used first),
    or None if the tenant has no usable accounts (caller falls back to the system account)."""
    from app.models.models import EmailAccount
    accounts = (await db.execute(
        select(EmailAccount).where(
            EmailAccount.tenant_id == tenant_id,
            EmailAccount.status == "active",
            EmailAccount.paused == False,  # noqa: E712
        )
    )).scalars().all()

    candidates = [
        (a.sent_today or 0, a) for a in accounts
        if (a.sent_today or 0) < account_cap(a)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])  # spread load: least-used first
    return candidates[0][1]


async def record_account_send(account, db) -> None:
    account.sent_today = (account.sent_today or 0) + 1
    account.sent_total = (account.sent_total or 0) + 1
    if not account.email_started_at:
        account.email_started_at = datetime.utcnow()  # anchor this account's ramp
    await db.commit()


# Hard-bounce guard. Mailbox providers throttle a sender above roughly 5% bounces and
# blacklist the domain not far above that — which would take the company's ordinary mail
# down too, not just campaigns. MIN_SAMPLE stops one early bounce in a tiny batch from
# pausing the account on noise.
BOUNCE_PAUSE_RATE = 0.05
BOUNCE_MIN_SAMPLE = 20


def bounce_rate(account) -> float:
    sent = account.sent_total or 0
    return (account.bounce_total or 0) / sent if sent else 0.0


async def record_account_bounce(account, db, reason: str = "") -> dict:
    """Count a hard bounce and pause the account if the rate is unsafe. Returns the state so
    callers can surface it."""
    account.bounce_total = (account.bounce_total or 0) + 1
    account.last_bounce_at = datetime.utcnow()
    rate = bounce_rate(account)
    paused_now = False
    if (account.sent_total or 0) >= BOUNCE_MIN_SAMPLE and rate >= BOUNCE_PAUSE_RATE:
        if not account.paused:
            account.paused = True
            paused_now = True
    await db.commit()
    return {"bounces": account.bounce_total, "sent": account.sent_total,
            "rate": round(rate, 4), "paused": bool(account.paused),
            "paused_now": paused_now, "reason": reason}


async def reset_all_accounts(db) -> int:
    """Zero every account's sent_today — called by the daily beat reset."""
    from app.models.models import EmailAccount
    res = await db.execute(update(EmailAccount).values(sent_today=0, last_reset_at=datetime.utcnow()))
    await db.commit()
    return res.rowcount or 0
