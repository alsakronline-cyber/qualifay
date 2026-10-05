"""Daily drip outreach — sends a staged contact list a little at a time, every day.

A lead joins a drip when raw_data["drip"] is set (by an import), e.g.
    {"name": "reconnect_2026_10", "wa_tpl": "<template id>", "email_tpl": "<id>", "priority": 0}

Once a day the scheduler sends exactly as many messages as each channel's warmup cap still
allows — never a blast — and spaces them out:
    WhatsApp: random 60-180 s apart  (a burst of near-identical texts is the main ban trigger)
    Email:    5 s apart              (SMTP has no such pattern detection; the cap does the work)

Safety properties:
  * Idempotent: a lead stamped wa_contacted_at / email_contacted_at is never sent again on that
    channel, and send_one re-checks the stamp, so a re-delivered task cannot double-message.
  * Respects unsubscribe/invalid status and the per-number pause switch.
  * Lower `priority` goes first (e.g. customers before cold leads), so if reply/report rates
    look bad the riskiest segment hasn't been touched yet.
"""
import logging
import random

from sqlalchemy import select, text

from app.workers.celery_app import celery_app
from app.workers._loop import run_async as _run_async

logger = logging.getLogger(__name__)

WA_GAP = (60, 180)      # seconds between WhatsApp sends
EMAIL_GAP = 5           # seconds between emails
START_DELAY = 30        # small head-start before the first send


def run_async(coro):
    return _run_async(coro)


@celery_app.task(name="drip.run_daily")
def run_daily():
    return run_async(_run_daily())


async def _pending(db, tenant_id, contact_col, stamp, limit):
    """Drip leads still owed a first message on one channel, highest priority first."""
    if limit <= 0:
        return []
    rows = (await db.execute(text(f"""
        SELECT id FROM leads
        WHERE tenant_id = :t
          AND raw_data->'drip' IS NOT NULL
          AND {contact_col} IS NOT NULL
          AND COALESCE(raw_data->>'{stamp}', '') = ''
          AND status = 'active'
        ORDER BY COALESCE((raw_data->'drip'->>'priority')::int, 9), created_at
        LIMIT :n
    """), {"t": tenant_id, "n": limit})).scalars().all()
    return list(rows)


async def _run_daily():
    from app.core.database import AsyncSessionLocal
    from app.models.models import WaInstance
    from app.services.warmup_service import warmup_service
    from app.services.email_account_service import pick_account, account_cap

    report = {}
    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(text(
            "SELECT DISTINCT tenant_id FROM leads WHERE raw_data->'drip' IS NOT NULL"
        ))).scalars().all()

        for tid in tenants:
            r = {"whatsapp": 0, "email": 0}

            # ── WhatsApp: fill whatever the warmup cap still allows today ──
            inst = (await db.execute(select(WaInstance).where(
                WaInstance.tenant_id == tid,
                WaInstance.status.in_(["open", "connected"]),
            ))).scalars().first()
            if inst and not getattr(inst, "paused", False):
                allowed, used, cap = await warmup_service.check_wa_limit(inst.id, db)
                ids = await _pending(db, tid, "phone", "wa_contacted_at",
                                     (cap - used) if allowed else 0)
                delay = START_DELAY
                for lid in ids:
                    send_one.apply_async(args=[lid, "whatsapp"], queue="outreach", countdown=delay)
                    delay += random.randint(*WA_GAP)
                r["whatsapp"] = len(ids)
                r["wa_spread_min"] = round(delay / 60)

            # ── Email: same idea against the sending account's own warmup cap ──
            acct = await pick_account(tid, db)
            if acct:
                from app.core.config import settings
                left = min(account_cap(acct), settings.DRIP_EMAIL_DAILY_MAX) - (acct.sent_today or 0)
                ids = await _pending(db, tid, "email", "email_contacted_at", left)
                for i, lid in enumerate(ids):
                    send_one.apply_async(args=[lid, "email"], queue="outreach",
                                         countdown=START_DELAY + i * EMAIL_GAP)
                r["email"] = len(ids)

            report[str(tid)] = r

    logger.info("drip daily dispatch: %s", report)
    return report


@celery_app.task(name="drip.send_one", queue="outreach")
def send_one(lead_id: str, channel: str):
    return run_async(_send_one(lead_id, channel))


async def _send_one(lead_id: str, channel: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Lead
    from app.workers.outreach_tasks import _process_approved_lead

    stamp = "wa_contacted_at" if channel == "whatsapp" else "email_contacted_at"
    async with AsyncSessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead:
            return {"skipped": "not_found"}
        rd = lead.raw_data or {}
        if rd.get(stamp):                      # already sent — re-delivery must be a no-op
            return {"skipped": "already_sent", "channel": channel}
        if getattr(lead.status, "value", lead.status) != "active":
            return {"skipped": f"status_{getattr(lead.status, 'value', lead.status)}"}
        drip = rd.get("drip") or {}
        tpl = drip.get("wa_tpl") if channel == "whatsapp" else drip.get("email_tpl")

    try:
        return await _process_approved_lead(
            lead_id, tpl, None, "email" if channel == "email" else None)
    except Exception as e:   # a cap race or transient send error must not crash the queue
        logger.warning("drip send %s/%s failed: %s", lead_id, channel, e)
        return {"error": str(e)[:200]}
