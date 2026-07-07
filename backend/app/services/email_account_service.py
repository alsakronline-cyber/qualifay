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
    if not account.email_started_at:
        account.email_started_at = datetime.utcnow()  # anchor this account's ramp
    await db.commit()


async def reset_all_accounts(db) -> int:
    """Zero every account's sent_today — called by the daily beat reset."""
    from app.models.models import EmailAccount
    res = await db.execute(update(EmailAccount).values(sent_today=0, last_reset_at=datetime.utcnow()))
    await db.commit()
    return res.rowcount or 0
