"""Sequence engine — steps enrolled leads through a cadence, sending each step on the
right channel, and stops a lead's cadence the moment they reply."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro
    return asyncio.run(_wrapped())


async def _resolve_channel(lead, channel: str):
    if channel == "whatsapp":
        return "whatsapp" if lead.phone else None
    if channel == "email":
        return "email" if lead.email else None
    # auto: WhatsApp if we have a (not-known-bad) number, else email
    if lead.phone and getattr(lead, "wa_reachable", None) is not False:
        return "whatsapp"
    if lead.email:
        return "email"
    return None


async def _render_step(db, step, lead):
    from app.services.template_render import render_for_lead
    if step.template_id:
        from app.models.models import MessageTemplate
        t = (await db.execute(select(MessageTemplate).where(MessageTemplate.id == step.template_id))).scalar_one_or_none()
        if t:
            return render_for_lead(t.subject or "", lead), render_for_lead(t.body, lead)
    return render_for_lead(step.subject or "", lead), render_for_lead(step.body or "", lead)


async def _send_wa(db, lead, text) -> bool:
    from app.models.models import WaInstance, Conversation, Message, MessageDirection, ConversationStatus
    from app.services.evolution_service import evolution_service
    from app.services.warmup_service import warmup_service
    inst = (await db.execute(select(WaInstance).where(
        WaInstance.tenant_id == lead.tenant_id,
        WaInstance.status.in_(["open", "connected"]),
        WaInstance.paused == False,  # noqa: E712
    ).limit(1))).scalar_one_or_none()
    if not inst:
        return False
    allowed, _, _ = await warmup_service.check_wa_limit(inst.id, db)
    if not allowed:
        return False
    jid = f"{lead.phone.replace('+', '')}@s.whatsapp.net"
    try:
        await evolution_service.send_text(inst.instance_name, jid, text)
    except Exception as e:
        logger.warning(f"sequence WA send failed for lead {lead.id}: {e}")
        return False
    await warmup_service.increment_wa_sent(inst.id, db)
    conv = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == lead.tenant_id,
        Conversation.instance_name == inst.instance_name,
        Conversation.wa_jid == jid,
    ))).scalar_one_or_none()
    if not conv:
        conv = Conversation(tenant_id=lead.tenant_id, lead_id=lead.id, wa_instance_id=inst.id,
                            instance_name=inst.instance_name, wa_jid=jid, channel="whatsapp",
                            contact_name=lead.name, status=ConversationStatus.open)
        db.add(conv)
        await db.flush()
    db.add(Message(conversation_id=conv.id, direction=MessageDirection.outbound, content=text, message_type="text"))
    conv.last_message = text[:200]
    return True


async def _send_email(db, lead, subject, body) -> bool:
    from app.services.email_account_service import pick_account, record_account_send
    from app.services.email_service import email_service
    from app.services.warmup_service import warmup_service
    subject = subject or ("متابعة" if lead.language == "ar" else "Following up")
    account = await pick_account(lead.tenant_id, db)
    try:
        if account:
            await email_service.send_via_account(account, lead.email, subject, body)
            await record_account_send(account, db)
        else:
            allowed, _, _ = await warmup_service.check_email_limit(lead.tenant_id, db)
            if not allowed:
                return False
            await email_service.send(lead.email, subject, body)
            await warmup_service.increment_email_sent(lead.tenant_id)
            await warmup_service.mark_email_started(lead.tenant_id, db)
    except Exception as e:
        logger.warning(f"sequence email send failed for lead {lead.id}: {e}")
        return False
    return True


@celery_app.task(name="run_due_sequence_steps", queue="outreach")
def run_due_sequence_steps():
    return run_async(_run_due())


async def _run_due():
    from app.core.database import AsyncSessionLocal
    from app.models.models import SequenceEnrollment, SequenceStep, Lead, LeadStatus

    from app.models.models import Tenant
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        enrolls = (await db.execute(select(SequenceEnrollment).where(
            SequenceEnrollment.status == "active",
            SequenceEnrollment.next_run_at <= now,
        ).limit(200))).scalars().all()

        # Batch-load everything the loop needs (avoids an N+1 per enrollment): tenant
        # autonomy, sequence steps, and leads — three queries instead of 3×N.
        seq_ids = {en.sequence_id for en in enrolls}
        lead_ids = {en.lead_id for en in enrolls}
        tenant_ids = {en.tenant_id for en in enrolls}

        manual_tenants = set()
        if tenant_ids:
            for tid, autonomy in (await db.execute(
                select(Tenant.id, Tenant.autonomy).where(Tenant.id.in_(tenant_ids))
            )).all():
                if (autonomy or "copilot") == "manual":
                    manual_tenants.add(tid)

        steps_by_seq: dict = {}
        if seq_ids:
            for st in (await db.execute(select(SequenceStep).where(
                SequenceStep.sequence_id.in_(seq_ids)).order_by(SequenceStep.step_order)
            )).scalars().all():
                steps_by_seq.setdefault(st.sequence_id, []).append(st)

        leads_by_id = {}
        if lead_ids:
            leads_by_id = {l.id: l for l in (await db.execute(
                select(Lead).where(Lead.id.in_(lead_ids))
            )).scalars().all()}

        sent = 0
        for en in enrolls:
            # In 'manual' autonomy the system never sends on its own — pause the cadence
            # (the owner can flip back to copilot/full to resume).
            if en.tenant_id in manual_tenants:
                en.status = "paused"
                continue
            steps = steps_by_seq.get(en.sequence_id, [])
            if en.current_step >= len(steps):
                en.status = "completed"
                continue

            lead = leads_by_id.get(en.lead_id)
            if not lead or lead.status in (LeadStatus.unsubscribed, LeadStatus.invalid, LeadStatus.duplicate):
                en.status = "stopped"
                continue

            step = steps[en.current_step]
            ch = await _resolve_channel(lead, step.channel)
            if not ch:
                en.status = "stopped"   # no reachable channel
                continue

            subject, body = await _render_step(db, step, lead)
            ok = await _send_wa(db, lead, body) if ch == "whatsapp" else await _send_email(db, lead, subject, body)
            if ok:
                sent += 1
                en.current_step += 1
                if en.current_step >= len(steps):
                    en.status = "completed"
                else:
                    nxt = steps[en.current_step]
                    en.next_run_at = now + timedelta(hours=nxt.delay_hours or 0)
            else:
                en.next_run_at = now + timedelta(hours=1)  # cap/blip — retry soon
        await db.commit()
    return {"processed": len(enrolls), "sent": sent}


async def stop_enrollments_for_lead(db, lead_id: str):
    """Auto-stop a lead's active cadences when they reply/book."""
    from app.models.models import SequenceEnrollment
    await db.execute(update(SequenceEnrollment).where(
        SequenceEnrollment.lead_id == lead_id,
        SequenceEnrollment.status == "active",
    ).values(status="replied"))
    await db.commit()
