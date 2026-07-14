"""Orchestrator — the autonomous 'brain'. Runs per tenant on a schedule, reads the
tenant's state (pipeline, warmup capacity, autonomy), decides what needs to happen, acts
within the autonomy limits, and logs a readable AgentRun so the owner can see exactly
what their AI did. This is the layer that turns a set of tools into a coworker."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

STALE_DAYS = 3          # a 'replied' lead untouched this long is going cold
REVIEW_NUDGE_MIN = 1    # notify once this many leads await review


def run_async(coro):
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro
    return asyncio.run(_wrapped())


@celery_app.task(name="orchestrator.run")
def run_orchestrator():
    """Fan out: assess every active tenant, one AgentRun each."""
    return run_async(_run_all())


async def _run_all():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Tenant
    ran = 0
    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        for t in tenants:
            try:
                await _assess_tenant(t, db)
                ran += 1
            except Exception as e:  # one tenant's failure must not stop the rest
                logger.warning("orchestrator failed for tenant %s: %s", t.id, e)
        await db.commit()
    return {"tenants_assessed": ran}


async def _assess_tenant(t, db):
    from app.models.models import (
        Lead, LeadStage, LeadStatus, Conversation, Message, MessageDirection,
        WaInstance, AgentRun, Notification, NotificationType,
    )
    tid = t.id
    autonomy = (t.autonomy or "copilot")
    now = datetime.utcnow()
    actions = []          # what we DID
    metrics = {}          # state snapshot

    # ── 1) Leads awaiting the owner's review ──────────────────────────────────
    pending = (await db.execute(select(func.count(Lead.id)).where(and_(
        Lead.tenant_id == tid, Lead.stage == LeadStage.pending_review,
        Lead.status == LeadStatus.active,
    )))).scalar() or 0
    metrics["pending_review"] = pending
    if pending >= REVIEW_NUDGE_MIN and autonomy != "full":
        # Full autopilot approves on its own; copilot/manual need the human nudged.
        if not await _recent_notif(db, tid, NotificationType.leads_ready, hours=12):
            db.add(Notification(
                tenant_id=tid, type=NotificationType.leads_ready,
                title="عملاء بانتظار مراجعتك",
                message=f"{pending} عميل مؤهَّل جاهز للموافقة على التواصل.",
                data={"count": pending, "source": "orchestrator"},
            ))
            actions.append({"type": "notify_review", "detail": f"{pending} leads awaiting review"})

    # ── 2) Cold leads going quiet ─────────────────────────────────────────────
    stale_cut = now - timedelta(days=STALE_DAYS)
    cold = (await db.execute(select(func.count(Lead.id)).where(and_(
        Lead.tenant_id == tid, Lead.stage == LeadStage.replied,
        Lead.status == LeadStatus.active, Lead.updated_at < stale_cut,
    )))).scalar() or 0
    metrics["cold_leads"] = cold
    if cold > 0:
        # Hand off to the existing re-engage worker only when the tenant lets the
        # system act (full/copilot). In manual mode we only surface the observation.
        if autonomy in ("full", "copilot"):
            try:
                from app.workers.outreach_tasks import re_engage_stale_leads
                re_engage_stale_leads.apply_async(queue="outreach")
                actions.append({"type": "reengage_cold", "detail": f"{cold} cold leads → re-engage queued"})
            except Exception:
                pass

    # ── 3) WhatsApp capacity / connection health ──────────────────────────────
    instances = (await db.execute(select(WaInstance).where(WaInstance.tenant_id == tid))).scalars().all()
    near_cap = [i for i in instances if (i.daily_wa_cap or 0) and (i.sent_today_wa or 0) >= 0.9 * i.daily_wa_cap]
    disconnected = [i for i in instances if (i.status or "") not in ("connected", "open") and instances]
    metrics["wa_instances"] = len(instances)
    metrics["wa_near_cap"] = len(near_cap)
    if disconnected and not await _recent_notif(db, tid, NotificationType.wa_disconnected, hours=6):
        db.add(Notification(
            tenant_id=tid, type=NotificationType.wa_disconnected,
            title="⚠️ واتساب غير متصل",
            message=f"{len(disconnected)} جهاز واتساب غير متصل — قد يتوقف التواصل.",
            data={"instances": [i.instance_name for i in disconnected], "source": "orchestrator"},
        ))
        actions.append({"type": "alert_wa_disconnected", "detail": f"{len(disconnected)} instances down"})

    # ── 4) Today's throughput (for the digest + the owner's sense of progress) ─
    since = now - timedelta(hours=24)
    metrics["sent_24h"] = (await db.execute(select(func.count(Message.id)).join(
        Conversation, Message.conversation_id == Conversation.id).where(and_(
            Conversation.tenant_id == tid, Message.direction == MessageDirection.outbound,
            Message.created_at >= since,
        )))).scalar() or 0
    metrics["replies_24h"] = (await db.execute(select(func.count(Message.id)).join(
        Conversation, Message.conversation_id == Conversation.id).where(and_(
            Conversation.tenant_id == tid, Message.direction == MessageDirection.inbound,
            Message.created_at >= since,
        )))).scalar() or 0

    # ── Log the decision cycle ────────────────────────────────────────────────
    status = "acted" if any(a["type"].startswith(("reengage", "notify")) for a in actions) else \
             ("alerted" if actions else "idle")
    summary = _summarize(autonomy, metrics, actions)
    db.add(AgentRun(tenant_id=tid, kind="orchestrator", status=status,
                    summary=summary, actions=actions, metrics=metrics))


async def _recent_notif(db, tid, ntype, hours):
    """Debounce — avoid re-notifying about the same thing every cycle."""
    from app.models.models import Notification
    cut = datetime.utcnow() - timedelta(hours=hours)
    n = (await db.execute(select(func.count(Notification.id)).where(and_(
        Notification.tenant_id == tid, Notification.type == ntype, Notification.created_at >= cut,
    )))).scalar() or 0
    return n > 0


def _summarize(autonomy, m, actions):
    bits = [f"راجعتُ الوضع (وضع: {autonomy})."]
    bits.append(f"في آخر 24 ساعة: {m.get('sent_24h',0)} رسالة، {m.get('replies_24h',0)} رد.")
    if m.get("pending_review"):
        bits.append(f"{m['pending_review']} عميل بانتظار المراجعة.")
    if m.get("cold_leads"):
        bits.append(f"{m['cold_leads']} عميل بدأ يبرد.")
    if not actions:
        bits.append("كل شيء يسير بشكل جيد، لا إجراء مطلوب.")
    return " ".join(bits)
