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
        from app.services.notification_service import notify
        await notify(
            db, tid, NotificationType.wa_disconnected,
            title="⚠️ واتساب غير متصل",
            message=f"{len(disconnected)} جهاز واتساب غير متصل — قد يتوقف التواصل.",
            data={"instances": [i.instance_name for i in disconnected], "source": "orchestrator"},
            urgent=True,  # revenue-critical — reach the owner on their WhatsApp too
        )
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


AB_MIN_SENT = 15        # min sends per variant before we trust the signal
AB_MIN_LIFT = 5.0       # winner must beat the runner-up by this many points


@celery_app.task(name="orchestrator.optimize_ab_tests")
def optimize_ab_tests():
    """Auto-promote the winning A/B variant once there's a clear, well-powered winner —
    turn it into a reusable template, close the test, and tell the owner."""
    return run_async(_optimize_ab())


async def _optimize_ab():
    from app.core.database import AsyncSessionLocal
    from app.models.models import ABTest, ABVariant, MessageTemplate, NotificationType
    from app.services.notification_service import notify
    from sqlalchemy.orm import selectinload

    promoted = 0
    async with AsyncSessionLocal() as db:
        tests = (await db.execute(select(ABTest).options(selectinload(ABTest.variants)).where(
            ABTest.status == "active"))).scalars().all()
        for t in tests:
            vs = [v for v in t.variants if (v.sent_count or 0) >= AB_MIN_SENT]
            if len(vs) < 2:
                continue  # not enough data on at least two arms yet
            def rate(v):
                return (v.reply_count or 0) / (v.sent_count or 1) * 100
            vs.sort(key=rate, reverse=True)
            winner, runner = vs[0], vs[1]
            if rate(winner) - rate(runner) < AB_MIN_LIFT:
                continue  # no clear winner — keep testing

            db.add(MessageTemplate(
                tenant_id=t.tenant_id, name=f"{t.name} — الفائزة", channel=t.channel or "whatsapp",
                category="outreach", subject=winner.subject, body=winner.body))
            t.status = "done"
            await notify(
                db, t.tenant_id, NotificationType.system,
                title="🏆 فاز اختبار A/B",
                message=f"في اختبار «{t.name}» تفوّقت النسخة {winner.label} بمعدل رد {rate(winner):.0f}% "
                        f"(مقابل {rate(runner):.0f}%). اعتمدناها كقالب جاهز.",
                data={"test_id": t.id, "winner": winner.label, "source": "ab_optimizer"})
            promoted += 1
        await db.commit()
    return {"promoted": promoted}


@celery_app.task(name="orchestrator.harvest_learnings")
def harvest_learnings():
    """Turn recently closed (won/lost) leads into reusable tenant memory."""
    return run_async(_harvest())


async def _harvest():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Lead, LeadStage, TenantMemory, Conversation, Message
    from app.services.ai_service import ai_service
    from app.services.memory_service import remember, prune

    learned = 0
    async with AsyncSessionLocal() as db:
        cut = datetime.utcnow() - timedelta(days=7)
        closed = (await db.execute(select(Lead).where(and_(
            Lead.stage.in_([LeadStage.won, LeadStage.lost]), Lead.updated_at >= cut,
        )).limit(50))).scalars().all()

        for lead in closed:
            # Skip leads we've already learned from.
            done = (await db.execute(select(func.count(TenantMemory.id)).where(
                TenantMemory.source_lead_id == lead.id))).scalar() or 0
            if done:
                continue

            conv = (await db.execute(select(Conversation).where(
                Conversation.lead_id == lead.id))).scalars().first()
            history = []
            if conv:
                msgs = (await db.execute(select(Message).where(
                    Message.conversation_id == conv.id).order_by(Message.created_at).limit(30))).scalars().all()
                history = [{"direction": m.direction.value, "content": m.content or ""} for m in msgs]

            outcome = "won" if lead.stage == LeadStage.won else "lost"
            lesson = await ai_service.extract_learning(
                {"company": lead.company, "industry": lead.industry, "city": lead.city}, outcome, history)
            if lesson:
                await remember(db, lead.tenant_id, lesson["kind"], lesson["content"], source_lead_id=lead.id)
                learned += 1
            else:
                # Mark as processed even with no lesson (a zero-weight marker) to avoid re-querying.
                db.add(TenantMemory(tenant_id=lead.tenant_id, kind="insight",
                                    content=f"(لا درس من {lead.company or lead.id})", weight=0, source_lead_id=lead.id))

        # Prune per tenant so memory stays sharp.
        for tid in {l.tenant_id for l in closed}:
            await prune(db, tid)
        await db.commit()
    return {"learned": learned}


@celery_app.task(name="orchestrator.daily_digest")
def send_daily_digest():
    """Once a day: send each tenant owner a plain-language end-of-day report."""
    return run_async(_digest_all())


async def _digest_all():
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Tenant, Lead, LeadStage, Conversation, Message, MessageDirection,
        NotificationType,
    )
    from app.services.notification_service import notify
    sent = 0
    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant).where(Tenant.onboarding_done == True))).scalars().all()  # noqa: E712
        since = datetime.utcnow() - timedelta(hours=24)
        for t in tenants:
            tid = t.id
            new_leads = (await db.execute(select(func.count(Lead.id)).where(and_(
                Lead.tenant_id == tid, Lead.created_at >= since)))).scalar() or 0
            pending = (await db.execute(select(func.count(Lead.id)).where(and_(
                Lead.tenant_id == tid, Lead.stage == LeadStage.pending_review)))).scalar() or 0
            won = (await db.execute(select(func.count(Lead.id)).where(and_(
                Lead.tenant_id == tid, Lead.stage == LeadStage.won, Lead.updated_at >= since)))).scalar() or 0
            sent_msgs = (await db.execute(select(func.count(Message.id)).join(
                Conversation, Message.conversation_id == Conversation.id).where(and_(
                    Conversation.tenant_id == tid, Message.direction == MessageDirection.outbound,
                    Message.created_at >= since)))).scalar() or 0
            replies = (await db.execute(select(func.count(Message.id)).join(
                Conversation, Message.conversation_id == Conversation.id).where(and_(
                    Conversation.tenant_id == tid, Message.direction == MessageDirection.inbound,
                    Message.created_at >= since)))).scalar() or 0

            if not any([new_leads, sent_msgs, replies, pending]):
                continue  # nothing happened — don't spam a quiet day

            msg = (f"ملخص اليوم 📊\n"
                   f"• عملاء جدد: {new_leads}\n"
                   f"• رسائل مُرسلة: {sent_msgs}\n"
                   f"• ردود: {replies}\n"
                   f"• بانتظار مراجعتك: {pending}\n"
                   f"• صفقات مربوحة: {won}")
            await notify(db, tid, NotificationType.system, title="ملخص اليوم من مساعدك الذكي",
                         message=msg, data={"source": "daily_digest"}, urgent=True)
            sent += 1
        await db.commit()
    return {"digests_sent": sent}


MISSED_MIN_DAYS = 2     # an unanswered inbound older than this is a missed follow-up
MISSED_MAX_DAYS = 14    # …but ignore ancient threads (and the year of imported cold email)


@celery_app.task(name="orchestrator.alert_missed_followups")
def alert_missed_followups():
    """Alert each tenant about contacts who reached out and got no reply for 2+ days —
    on WhatsApp OR email — while confirming the owner hasn't already answered them by
    some other channel. This is the 'you're about to drop a warm lead' safety net."""
    return run_async(_alert_missed_all())


async def _alert_missed_all():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Tenant
    total = 0
    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        for t in tenants:
            try:
                total += await _alert_missed_tenant(db, t.id)
            except Exception as e:  # one tenant must not stop the rest
                logger.warning("missed-followup scan failed for tenant %s: %s", t.id, e)
        await db.commit()
    return {"tenants_alerted": total}


# Last message per conversation is inbound and 2–14 days stale, the contact is worth
# chasing (a WhatsApp thread, or an email tied to a live lead — never the bulk-imported
# cold email with no lead), and the owner hasn't replied to that lead on ANY channel since.
_MISSED_SQL = """
SELECT c.id,
       COALESCE(NULLIF(c.contact_name, ''), c.wa_jid) AS name,
       c.channel,
       lm.created_at AS last_at
FROM conversations c
JOIN LATERAL (
    SELECT direction, created_at FROM messages m
    WHERE m.conversation_id = c.id
    ORDER BY m.created_at DESC
    LIMIT 1
) lm ON TRUE
LEFT JOIN leads l ON l.id = c.lead_id
WHERE c.tenant_id = :tid
  AND lm.direction = 'inbound'
  AND lm.created_at <= :old_cut
  AND lm.created_at >= :recent_cut
  AND (c.channel = 'whatsapp' OR c.lead_id IS NOT NULL)
  AND (l.id IS NULL OR (l.status = 'active' AND l.stage NOT IN ('won', 'lost', 'archived')))
  AND NOT EXISTS (
      SELECT 1 FROM messages mo
      JOIN conversations c2 ON mo.conversation_id = c2.id
      WHERE c.lead_id IS NOT NULL
        AND c2.lead_id = c.lead_id
        AND mo.direction = 'outbound'
        AND mo.created_at > lm.created_at
  )
ORDER BY lm.created_at ASC
"""


MISSED_MAX_PER_RUN = 25     # cap the burst if a big backlog surfaces at once
MISSED_RENOTIFY_DAYS = 3    # don't re-notify the SAME conversation more often than this


async def _alert_missed_tenant(db, tid) -> int:
    from sqlalchemy import text
    from app.models.models import Notification, NotificationType

    now = datetime.utcnow()
    # Has the owner already had a WhatsApp ping about this recently? (check before we add today's)
    owner_pinged_recently = await _recent_notif(db, tid, NotificationType.missed_followup, hours=20)

    rows = (await db.execute(text(_MISSED_SQL), {
        "tid": tid,
        "old_cut": now - timedelta(days=MISSED_MIN_DAYS),
        "recent_cut": now - timedelta(days=MISSED_MAX_DAYS),
    })).mappings().all()
    if not rows:
        return 0

    # One notification PER contact, each deep-linking straight to its chat/email — so the
    # owner clicks and lands in the exact thread. Debounced per conversation so an
    # unanswered contact resurfaces at most every few days, not every scan.
    created = 0
    for r in rows:
        if created >= MISSED_MAX_PER_RUN:
            break
        if await _missed_notif_exists(db, tid, r["id"], MISSED_RENOTIFY_DAYS):
            continue
        name = r["name"] or ("جهة اتصال" if r["channel"] == "whatsapp" else "مُرسِل")
        ch_ar = "واتساب" if r["channel"] == "whatsapp" else "البريد الإلكتروني"
        days = max((now - r["last_at"]).days, MISSED_MIN_DAYS)
        db.add(Notification(
            tenant_id=tid, type=NotificationType.missed_followup,
            title=f"⏰ رد متأخر: {name}",
            message=f"{name} تواصل معك عبر {ch_ar} منذ {days} يوم/أيام ولم تردّ عليه بأي وسيلة. "
                    f"اضغط لفتح المحادثة والرد.",
            data={
                "conversation_id": r["id"], "channel": r["channel"],
                "link": f"/inbox?conversation={r['id']}", "days": days,
                "source": "missed_followup",
            },
        ))
        created += 1

    # A single owner WhatsApp nudge summarising the backlog (not once per contact), throttled.
    if rows and not owner_pinged_recently:
        try:
            from app.services.notification_service import _whatsapp_owner
            await _whatsapp_owner(
                db, tid,
                f"*⏰ متابعات فائتة*\nلديك {len(rows)} جهة تواصلت معك ولم تردّ عليها منذ يومين أو أكثر. "
                f"افتح صندوق الوارد — كل إشعار يفتح المحادثة مباشرة.",
            )
        except Exception as e:
            logger.warning("missed-followup owner ping failed for tenant %s: %s", tid, e)
    return created


async def _missed_notif_exists(db, tid, conv_id, days) -> bool:
    """True if we already raised a missed-followup for this exact conversation recently —
    so an unanswered contact isn't re-notified on every single scan. Raw SQL because the
    generic JSON column has no `.astext`; PG's ->> does the job."""
    from sqlalchemy import text
    cut = datetime.utcnow() - timedelta(days=days)
    row = (await db.execute(text(
        "SELECT 1 FROM notifications WHERE tenant_id = :tid AND type = 'missed_followup' "
        "AND created_at >= :cut AND data->>'conversation_id' = :cid LIMIT 1"
    ), {"tid": tid, "cut": cut, "cid": str(conv_id)})).first()
    return row is not None


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
