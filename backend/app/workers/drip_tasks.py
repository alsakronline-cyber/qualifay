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

# New numbers get banned fast when they open with cold messages (masoud: linked Oct 6, 403 on
# Oct 10). A number sends no drip messages for its first QUIET_DAYS, then NEW_CAP a day for a
# week, then whatever the normal warmup cap allows.
QUIET_DAYS = 14
NEW_CAP = 5
NEW_CAP_DAYS = 7


def _cold_room(day_of_life, room):
    """How many cold (drip) messages a number of this age may send today, given `room`."""
    day = day_of_life or 0
    if day < QUIET_DAYS:
        return 0
    if day < QUIET_DAYS + NEW_CAP_DAYS:
        return min(room, NEW_CAP)
    return room


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


def _split(total, room):
    """Divide `total` sends across numbers: even shares capped by each number's `room`,
    with leftover redistributed to numbers that still have room. Returns {id: count}."""
    plan = {k: 0 for k in room}
    left = total
    while left > 0:
        open_ = [k for k in room if plan[k] < room[k]]
        if not open_:
            break
        share = max(left // len(open_), 1)
        for k in open_:
            give = min(share, room[k] - plan[k], left)
            plan[k] += give
            left -= give
            if left == 0:
                break
    return plan


async def _refresh_instance_status(db, tenant_id):
    """Sync each of the tenant's WhatsApp numbers with Evolution's live connection state."""
    from app.models.models import WaInstance
    from app.services.evolution_service import evolution_service
    for inst in (await db.execute(select(WaInstance).where(
            WaInstance.tenant_id == tenant_id))).scalars().all():
        try:
            data = await evolution_service.connect_status(inst.instance_name)
            state = (data.get("instance") or {}).get("state") or data.get("state")
        except Exception:
            continue                       # can't reach Evolution: keep the stored value
        mapped = {"open": "connected", "close": "disconnected", "closed": "disconnected"}.get(state, state)
        if mapped and mapped != inst.status:
            logger.info("drip: %s status %s -> %s (live)", inst.instance_name, inst.status, mapped)
            inst.status = mapped
    await db.commit()


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
            # The stored status goes stale when a connection webhook is missed (a number can
            # read "connecting" while it's actually open), and both this query and the sender
            # trust it — so a connected number would silently send nothing. Refresh from the
            # live connection state first.
            await _refresh_instance_status(db, tid)
            from app.core.config import settings
            insts = [i for i in (await db.execute(select(WaInstance).where(
                WaInstance.tenant_id == tid,
                WaInstance.status.in_(["open", "connected"]),
            ).order_by(WaInstance.instance_name))).scalars().all()
                if not getattr(i, "paused", False)]
            # Split the campaign's daily total across every connected number: an even share
            # each, never above a number's own remaining warmup cap. Any share a young number
            # can't use goes to the others, so the day's total still lands.
            room = {}
            for i in insts:
                allowed, used, cap = await warmup_service.check_wa_limit(i.id, db)
                room[i.id] = _cold_room(i.day_of_life, max(cap - used, 0) if allowed else 0)
            plan = _split(settings.DRIP_WA_DAILY_MAX, room)
            ids = await _pending(db, tid, "phone", "wa_contacted_at", sum(plan.values()))
            # Each number keeps its own 1-3 min spacing, so they send in parallel lanes.
            lanes = [(iid, n) for iid, n in plan.items() if n > 0]
            r["per_number"] = {}
            pos = 0
            for iid, n in lanes:
                delay = START_DELAY
                for lid in ids[pos:pos + n]:
                    send_one.apply_async(args=[lid, "whatsapp", iid], queue="outreach", countdown=delay)
                    delay += random.randint(*WA_GAP)
                name = next(i.instance_name for i in insts if i.id == iid)
                r["per_number"][name] = len(ids[pos:pos + n])
                pos += n
            r["whatsapp"] = min(pos, len(ids))

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
def send_one(lead_id: str, channel: str, instance_id: str = None):
    return run_async(_send_one(lead_id, channel, instance_id))


async def _send_one(lead_id: str, channel: str, instance_id: str = None):
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
        if not tpl:                            # channel switched off for this campaign
            return {"skipped": "channel_disabled", "channel": channel}

    try:
        result = await _process_approved_lead(
            lead_id, tpl, None, "email" if channel == "email" else None,
            instance_id if channel == "whatsapp" else None)
    except Exception as e:   # a cap race or transient send error must not crash the queue
        logger.warning("drip send %s/%s failed: %s", lead_id, channel, e)
        # Fall through (no early return): send failures arrive HERE as exceptions, and the
        # not-on-WhatsApp check below must see them — returning early skipped it entirely.
        result = {"error": str(e)[:300]}

    # Evolution answers 400 when the number isn't on WhatsApp. That never fixes itself, so
    # stamp it as a permanent failure — otherwise the lead is retried every morning forever
    # and keeps eating a slot of the daily budget. Transient errors are left to retry.
    err = str((result or {}).get("error", ""))
    if channel == "whatsapp" and "400 Bad Request" in err:
        async with AsyncSessionLocal() as db:
            lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
            if lead:
                lead.raw_data = {**(lead.raw_data or {}), "wa_contacted_at": "failed:not_on_whatsapp"}
                await db.commit()
        result = {**result, "marked": "not_on_whatsapp"}
    return result
