"""
Celery Outreach Tasks — WhatsApp message sending, inbound handling, warmup management
"""
import asyncio
import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    # Dispose the shared async DB engine pool first: each Celery task runs in a new
    # event loop, and pooled asyncpg connections bound to a prior (closed) loop cause
    # "Future attached to a different loop" errors. Isolated to the Celery process.
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        # Rebuild AI SDK clients so their httpx pools bind to THIS loop, not a closed one.
        try:
            from app.services.ai_service import ai_service
            ai_service.reset()
        except Exception:
            pass
        return await coro
    return asyncio.run(_wrapped())


@celery_app.task(bind=True, max_retries=2, queue="outreach")
def process_approved_lead(self, lead_id: str, template_id: str = None):
    """Send initial outreach to an approved lead. If template_id is given, the message
    is the rendered template ({{vars}} filled from the lead); otherwise AI writes AIDA copy."""
    try:
        return run_async(_process_approved_lead(lead_id, template_id))
    except Exception as exc:
        logger.error(f"process_approved_lead failed for {lead_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


async def _load_template(db, tenant_id, template_id):
    if not template_id:
        return None
    from app.models.models import MessageTemplate
    from sqlalchemy import select, and_
    return (await db.execute(select(MessageTemplate).where(and_(
        MessageTemplate.id == template_id, MessageTemplate.tenant_id == tenant_id
    )))).scalar_one_or_none()


async def _tenant_ctx(db, tenant_id):
    """Return (brand_context, autonomy) for a tenant — brand context is injected into AI
    copy so it's on-brand; autonomy gates whether the system sends on its own."""
    from app.models.models import Tenant
    from app.services.ai_service import tenant_context_str
    from sqlalchemy import select
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not t:
        return "", "copilot"
    return tenant_context_str(t.tenant_profile or {}), (t.autonomy or "copilot")


async def _process_approved_lead(lead_id: str, template_id: str = None):
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Lead, WaInstance, Conversation, Message,
        Notification, NotificationType, LeadStage, MessageDirection, ConversationStatus
    )
    from app.services.ai_service import ai_service
    from app.services.evolution_service import evolution_service
    from app.services.warmup_service import warmup_service
    from sqlalchemy import select
    from datetime import datetime

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            logger.warning(f"Lead {lead_id} not found")
            return {"error": "lead_not_found"}

        # Step 1a: Hard status gate — block unsubscribed/blocked/invalid before ANY send/AI call
        from app.models.models import LeadStatus as _LS
        if lead.status in (_LS.unsubscribed, _LS.invalid, _LS.duplicate):
            logger.info(f"Outreach blocked for lead {lead_id}: status={lead.status.value}")
            return {"skipped": True, "reason": f"lead_status_{lead.status.value}"}

        template = await _load_template(db, lead.tenant_id, template_id)

        # Channel selection: WhatsApp when there's a phone, else fall back to email
        # (many LinkedIn leads are email-only), else there's no way to reach them.
        if not lead.phone:
            if lead.email:
                return await _send_email_outreach(db, lead, template)
            logger.warning(f"Lead {lead_id} has no phone or email")
            return {"error": "no_contact"}

        # Step 1: Consent compliance check
        lead_dict = {
            "name": lead.name,
            "company": lead.company,
            "source": lead.source.value if lead.source else None,
            "consent_at": lead.consent_at.isoformat() if lead.consent_at else None,
            "consent_method": lead.consent_method,
        }
        consent = await ai_service.check_consent_compliance(lead_dict, lead.consent_method or "unknown")
        if not consent.get("compliant", False):
            notif = Notification(
                tenant_id=lead.tenant_id,
                type=NotificationType.consent_issue,
                title="Consent Issue — Outreach Blocked",
                message=f"Lead '{lead.company or lead.name}': {consent.get('action_needed', 'Manual review required')}",
                data={"lead_id": lead_id, "reason": consent.get("reason")},
            )
            db.add(notif)
            await db.commit()
            logger.warning(f"Lead {lead_id} blocked by consent check: {consent.get('reason')}")
            return {"error": "consent_non_compliant", "reason": consent.get("reason")}

        # Find best WA instance for this tenant
        inst_result = await db.execute(
            select(WaInstance).where(
                WaInstance.tenant_id == lead.tenant_id,
                WaInstance.status == "open",
            ).limit(1)
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            logger.warning(f"No connected WA instance for tenant {lead.tenant_id}")
            return {"error": "no_wa_instance"}

        # Step 2: WA limit check
        allowed, used, cap = await warmup_service.check_wa_limit(instance.id, db)
        if not allowed:
            notif = Notification(
                tenant_id=lead.tenant_id,
                type=NotificationType.wa_limit,
                title="WhatsApp Daily Limit — Outreach Delayed",
                message=f"Lead '{lead.company or lead.name}' outreach delayed: daily cap ({cap}) reached. Will retry tomorrow.",
                data={"lead_id": lead_id, "instance_id": instance.id},
            )
            db.add(notif)
            await db.commit()
            # Retry tomorrow
            raise process_approved_lead.retry(countdown=86400)

        # Step 3: Message — active A/B test variant wins, else template, else AI AIDA copy.
        ab_used = False
        from app.services.ab_service import assign_variant
        ab = await assign_variant(db, lead.tenant_id, "whatsapp", lead)
        if ab:
            _variant, message_text, _subject = ab
            ab_used = True
        elif template:
            from app.services.template_render import render_for_lead
            message_text = render_for_lead(template.body, lead)
        else:
            _brand, _ = await _tenant_ctx(db, lead.tenant_id)
            message_text = await ai_service.write_aida_message({
                "name": lead.name, "company": lead.company, "industry": lead.industry,
                "city": lead.city, "language": lead.language,
            }, context=_brand)

        # Step 4: Translate if Arabic (templates/AB variants are already authored in-language).
        if not template and not ab_used and lead.language == "ar" and message_text:
            # Check if already Arabic
            arabic_chars = sum(1 for c in message_text if "؀" <= c <= "ۿ")
            if arabic_chars < len(message_text) * 0.3:
                message_text = await ai_service.translate_arabic(message_text, direction="en_to_ar")

        # Step 5: Send via Evolution API
        wa_jid = f"{lead.phone.replace('+', '')}@s.whatsapp.net"
        await evolution_service.send_typing(instance.instance_name, wa_jid, duration=2)
        await asyncio.sleep(2)
        await evolution_service.send_text(instance.instance_name, wa_jid, message_text)

        # Step 6: Increment WA sent count
        await warmup_service.increment_wa_sent(instance.id, db)

        # Step 7: Update lead stage
        lead.stage = LeadStage.outreach

        # Find or create conversation
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == lead.tenant_id,
                Conversation.wa_jid == wa_jid,
                Conversation.status != ConversationStatus.resolved,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            conv = Conversation(
                tenant_id=lead.tenant_id,
                lead_id=lead.id,
                wa_instance_id=instance.id,
                instance_name=instance.instance_name,
                wa_jid=wa_jid,
                contact_name=lead.name or lead.company,
                status=ConversationStatus.open,
                ai_enabled=False,
            )
            db.add(conv)
            await db.flush()

        # Save outbound message
        msg = Message(
            conversation_id=conv.id,
            direction=MessageDirection.outbound,
            content=message_text,
            message_type="text",
            is_ai_generated=True,
            ai_confidence=0.9,
        )
        db.add(msg)
        conv.last_message = message_text[:200]

        await db.commit()
        logger.info(f"Lead {lead_id} outreach sent via {instance.instance_name} to {wa_jid}")
        return {"sent": True, "lead_id": lead_id, "conversation_id": conv.id}


async def _send_email_outreach(db, lead, template=None):
    """Email outreach for a lead with no WhatsApp number. Same consent + AIDA copy as
    WhatsApp, capped per-tenant per-day to protect sender reputation."""
    from datetime import date, datetime
    from app.models.models import LeadStage
    from app.services.ai_service import ai_service
    from app.services.email_service import email_service
    from app.core.config import settings

    if not email_service.is_configured():
        logger.warning("Email outreach requested but SMTP is not configured")
        return {"error": "smtp_not_configured"}

    # Consent compliance (Law 151) — identical gate to the WhatsApp path.
    lead_dict = {
        "name": lead.name, "company": lead.company,
        "source": lead.source.value if lead.source else None,
        "consent_at": lead.consent_at.isoformat() if lead.consent_at else None,
        "consent_method": lead.consent_method,
    }
    consent = await ai_service.check_consent_compliance(lead_dict, lead.consent_method or "unknown")
    if not consent.get("compliant", False):
        logger.warning(f"Email outreach blocked by consent for lead {lead.id}")
        return {"error": "consent_non_compliant"}

    # Pick a sending identity: a tenant email account (rotated, own warmup) if any,
    # else the system-level account with its tenant-level ramped/bounce-aware cap.
    from app.services.warmup_service import warmup_service
    from app.services.email_account_service import pick_account, record_account_send
    account = await pick_account(lead.tenant_id, db)
    if not account:
        allowed, used, cap = await warmup_service.check_email_limit(lead.tenant_id, db)
        if not allowed:
            logger.info(f"Email cap/pause hit for tenant {lead.tenant_id} ({used}/{cap})")
            raise process_approved_lead.retry(countdown=86400)

    # Active A/B test variant wins, else template, else AI AIDA copy.
    from app.services.ab_service import assign_variant
    ab = await assign_variant(db, lead.tenant_id, "email", lead)
    _default_subject = "بخصوص التعاون معكم" if lead.language == "ar" else f"Quick note for {lead.company or lead.name or 'you'}"
    if ab:
        _variant, body, ab_subject = ab
        subject = ab_subject or _default_subject
    elif template:
        from app.services.template_render import render_for_lead
        body = render_for_lead(template.body, lead)
        subject = render_for_lead(template.subject or "", lead) or _default_subject
    else:
        _brand, _ = await _tenant_ctx(db, lead.tenant_id)
        body = await ai_service.write_aida_message({
            "name": lead.name, "company": lead.company, "industry": lead.industry,
            "city": lead.city, "language": lead.language,
        }, context=_brand)
        if lead.language == "ar" and body:
            arabic = sum(1 for c in body if "؀" <= c <= "ۿ")
            if arabic < len(body) * 0.3:
                body = await ai_service.translate_arabic(body, direction="en_to_ar")
        subject = "بخصوص التعاون معكم" if lead.language == "ar" else f"Quick note for {lead.company or lead.name or 'you'}"

    try:
        if account:
            await email_service.send_via_account(account, lead.email, subject, body or "")
        else:
            await email_service.send(lead.email, subject, body or "")
    except Exception as e:
        logger.error(f"Email send failed for lead {lead.id}: {e}")
        return {"error": "email_send_failed", "detail": str(e)}

    lead.stage = LeadStage.outreach
    lead.updated_at = datetime.utcnow()
    await db.commit()

    # Count the send against the account used (per-account warmup), or the tenant fallback.
    if account:
        await record_account_send(account, db)
    else:
        await warmup_service.increment_email_sent(lead.tenant_id)
        await warmup_service.mark_email_started(lead.tenant_id, db)

    try:
        from app.services.activity_service import log_activity
        from app.models.models import ActivityType
        await log_activity(
            db=db, tenant_id=str(lead.tenant_id), activity_type=ActivityType.lead_updated,
            summary=f"Email outreach sent to {lead.email}",
            entity_type="lead", entity_id=str(lead.id),
        )
    except Exception as e:
        logger.debug(f"email activity log skipped: {e}")

    logger.info(f"Email outreach sent to {lead.email} for lead {lead.id}")
    return {"sent": True, "channel": "email", "lead_id": lead.id}


@celery_app.task(bind=True, max_retries=3, queue="outreach")
def handle_inbound_message(self, webhook_data: dict):
    """
    Process an inbound WhatsApp message:
    1. Extract event data
    2. Skip own messages
    3. STOP/unsubscribe check
    4. Find/create lead and conversation
    5. Save message
    6. Update conversation
    7. Update lead stage if in outreach
    8. Classify intent
    9. Queue AI reply if enabled
    10. Queue sentiment update
    """
    try:
        return run_async(_handle_inbound_message(webhook_data))
    except Exception as exc:
        logger.error(f"handle_inbound_message failed: {exc}")
        raise self.retry(exc=exc, countdown=5)


async def _handle_inbound_message(webhook_data: dict):
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Lead, Conversation, Message, MessageDirection,
        ConversationStatus, LeadStage, LeadStatus, WaInstance
    )
    from app.services.ai_service import ai_service
    from sqlalchemy import select, and_
    from datetime import datetime

    event = webhook_data.get("event", "")
    instance_name = webhook_data.get("instance", "")
    data = webhook_data.get("data", {})

    if event != "messages.upsert":
        return {"skipped": True, "reason": "not_message_event"}

    msg_data = data.get("message", {})
    key = data.get("key", {})
    from_me = key.get("fromMe", False)

    # Step 1: Skip own messages
    if from_me:
        return {"skipped": True, "reason": "own_message"}

    wa_jid = key.get("remoteJid", "")
    wa_msg_id = key.get("id", "")
    push_name = data.get("pushName", "")

    # Skip groups, channels, device IDs, and non-numeric JIDs — only 1:1 lead chats
    jid_user = wa_jid.split("@")[0] if wa_jid else ""
    if (not wa_jid or wa_jid.endswith("@g.us") or wa_jid.endswith("@lid")
            or wa_jid.startswith("cmr") or "newsletter" in wa_jid or not jid_user.isdigit()):
        return {"skipped": True, "reason": "non_direct_chat", "jid": wa_jid}

    content = (
        msg_data.get("conversation")
        or msg_data.get("extendedTextMessage", {}).get("text")
        or "[media]"
    )

    # Step 2: STOP/unsubscribe check
    content_lower = content.lower().strip()
    stop_keywords = ["إيقاف", "stop", "unsubscribe", "إلغاء", "لا أريد", "remove me", "opt out"]
    if any(kw in content_lower for kw in stop_keywords):
        async with AsyncSessionLocal() as db:
            # Find lead by phone from JID
            phone = _jid_to_e164(wa_jid)
            if phone:
                lead_result = await db.execute(
                    select(Lead).where(Lead.phone == phone)
                )
                lead = lead_result.scalar_one_or_none()
                if lead:
                    lead.status = LeadStatus.unsubscribed
                    await db.commit()
                    logger.info(f"Lead {lead.id} unsubscribed via STOP keyword")
        return {"skipped": True, "reason": "stop_keyword", "jid": wa_jid}

    async with AsyncSessionLocal() as db:
        # Find WA instance record
        inst_result = await db.execute(
            select(WaInstance).where(WaInstance.instance_name == instance_name)
        )
        instance = inst_result.scalar_one_or_none()
        tenant_id = instance.tenant_id if instance else None

        # Step 3: Find lead by phone
        phone = _jid_to_e164(wa_jid)
        lead = None
        if phone:
            lead_result = await db.execute(
                select(Lead).where(
                    and_(Lead.phone == phone, Lead.tenant_id == tenant_id) if tenant_id
                    else Lead.phone == phone
                )
            )
            lead = lead_result.scalar_one_or_none()

        # A WhatsApp reply stops the lead's active cadences (no more follow-ups).
        if lead:
            try:
                from app.workers.sequence_tasks import stop_enrollments_for_lead
                await stop_enrollments_for_lead(db, lead.id)
            except Exception:
                pass
            try:
                from app.services.ab_service import mark_replied
                await mark_replied(db, lead.id)
            except Exception:
                pass

        # Step 4: Find or create conversation
        query = select(Conversation).where(
            and_(
                Conversation.wa_jid == wa_jid,
                Conversation.instance_name == instance_name,
                Conversation.status != ConversationStatus.resolved,
            )
        )
        if tenant_id:
            query = query.where(Conversation.tenant_id == tenant_id)

        conv_result = await db.execute(query)
        conv = conv_result.scalar_one_or_none()

        if not conv:
            conv = Conversation(
                tenant_id=tenant_id or "",
                lead_id=lead.id if lead else None,
                wa_instance_id=instance.id if instance else None,
                instance_name=instance_name,
                wa_jid=wa_jid,
                contact_name=push_name or phone,
                status=ConversationStatus.open,
                ai_enabled=False,
            )
            db.add(conv)
            await db.flush()

        # Step 5: Save inbound message. Skip if webhook.py already persisted it (dedupe by
        # wa_message_id) so we don't create duplicate rows or clobber the properly-typed
        # media message from the webhook.
        already_saved = False
        if wa_msg_id:
            existing = await db.execute(
                select(Message).where(Message.wa_message_id == wa_msg_id)
            )
            already_saved = existing.scalar_one_or_none() is not None
        if not already_saved:
            db.add(Message(
                conversation_id=conv.id,
                wa_message_id=wa_msg_id,
                direction=MessageDirection.inbound,
                content=content,
                message_type="text" if content != "[media]" else "media",
            ))

        # Step 6: Update conversation
        conv.unread_count = (conv.unread_count or 0) + 1
        conv.last_message = content[:200]

        # Step 7: Update lead stage if was outreach
        if lead and lead.stage == LeadStage.outreach:
            lead.stage = LeadStage.replied

        await db.commit()

        # Step 8: Classify intent
        intent_data = await ai_service.classify_intent(content, push_name or "")
        logger.info(f"Inbound intent: {intent_data}")

        # Step 9: Queue AI reply if enabled — but never auto-reply in 'manual' autonomy
        # (the owner handles all conversations themselves).
        _, _autonomy = await _tenant_ctx(db, conv.tenant_id)
        if conv.ai_enabled and _autonomy != "manual" and not intent_data.get("requires_human", True):
            send_ai_reply.apply_async(
                args=[
                    conv.id,
                    content,
                    push_name or "Customer",
                    wa_jid,
                    instance_name,
                    intent_data.get("language", "auto"),
                ],
                queue="outreach",
            )

        # Step 10: Update sentiment
        from app.workers.ai_tasks import update_sentiment
        update_sentiment.apply_async(args=[conv.id], queue="ai")

        return {
            "conversation_id": conv.id,
            "lead_id": lead.id if lead else None,
            "intent": intent_data.get("intent"),
        }


def _jid_to_e164(jid: str) -> str | None:
    """Convert WhatsApp JID to E.164 phone format."""
    if not jid:
        return None
    phone = jid.replace("@s.whatsapp.net", "").replace("@g.us", "").replace("@c.us", "")
    if phone.startswith("0"):
        phone = "+2" + phone
    elif not phone.startswith("+"):
        phone = "+" + phone
    return phone if len(phone) >= 10 else None


@celery_app.task(queue="outreach")
def send_ai_reply(
    conversation_id: str,
    message: str,
    contact_name: str,
    wa_jid: str,
    instance_name: str,
    language: str,
):
    """Generate AI reply and send via Evolution API."""
    return run_async(_send_ai_reply(conversation_id, message, contact_name, wa_jid, instance_name, language))


async def _send_ai_reply(
    conversation_id: str,
    message: str,
    contact_name: str,
    wa_jid: str,
    instance_name: str,
    language: str,
):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Message, Conversation, MessageDirection
    from app.services.ai_service import ai_service
    from app.services.evolution_service import evolution_service
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Get recent history
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(15)
        )
        msgs = result.scalars().all()
        history = [{"direction": m.direction.value, "content": m.content or ""} for m in reversed(msgs)]

        # Brand context so the reply sounds like this business (on-brand).
        conv = (await db.execute(select(Conversation).where(Conversation.id == conversation_id))).scalar_one_or_none()
        _brand = ""
        if conv:
            _brand, _ = await _tenant_ctx(db, conv.tenant_id)

        # Generate reply
        reply = await ai_service.generate_wa_reply(message, contact_name, history, language, tenant_context=_brand)
        if not reply:
            logger.warning(f"AI returned empty reply for conversation {conversation_id}")
            return {"sent": False, "reason": "empty_reply"}

        # Show typing
        await evolution_service.send_typing(instance_name, wa_jid, duration=2)
        await asyncio.sleep(2)

        # Send message
        await evolution_service.send_text(instance_name, wa_jid, reply)

        # Save outbound message
        out_msg = Message(
            conversation_id=conversation_id,
            direction=MessageDirection.outbound,
            content=reply,
            is_ai_generated=True,
            ai_confidence=0.85,
        )
        db.add(out_msg)

        conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.last_message = reply[:200]

        await db.commit()
        logger.info(f"AI reply sent to {wa_jid}")
        return {"sent": True, "reply": reply[:100]}


@celery_app.task(queue="outreach")
def reset_daily_limits():
    """Reset daily WA send counts for all instances. Called by Celery beat."""
    return run_async(_reset_daily_limits())


async def _reset_daily_limits():
    from app.core.database import AsyncSessionLocal
    from app.services.warmup_service import warmup_service

    async with AsyncSessionLocal() as db:
        await warmup_service.reset_all_daily_counts(db)
        from app.services.email_account_service import reset_all_accounts
        await reset_all_accounts(db)
    return {"done": True}


@celery_app.task(queue="outreach")
def advance_warmup_days():
    """Advance warmup day counter for all WA instances. Called by Celery beat."""
    return run_async(_advance_warmup_days())


async def _advance_warmup_days():
    from app.core.database import AsyncSessionLocal
    from app.services.warmup_service import warmup_service

    async with AsyncSessionLocal() as db:
        await warmup_service.advance_all_warmup_days(db)
    return {"done": True}


# ── P8: Re-engage stale leads ────────────────────────────────

@celery_app.task(name="re_engage_stale_leads", queue="outreach")
def re_engage_stale_leads():
    """Find leads not contacted in 20+ days and create re-engagement suggestions."""
    return run_async(_async_re_engage_stale())


async def _async_re_engage_stale():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Lead, LeadStage, LeadStatus, Notification, NotificationType
    from sqlalchemy import select, and_
    from datetime import datetime, timezone, timedelta
    from app.core.config import settings
    import httpx

    cutoff = datetime.now(timezone.utc) - timedelta(days=20)

    # Step 1: load stale leads then CLOSE the DB session before HTTP calls
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.last_contacted_at < cutoff,
                    Lead.last_contacted_at.isnot(None),
                    Lead.stage.in_([LeadStage.outreach, LeadStage.replied]),
                    Lead.status == LeadStatus.active,
                )
            ).limit(100)  # cap to prevent runaway queries on large tenants
        )
        stale_leads = result.scalars().all()
        # Snapshot data before session closes
        lead_snapshots = [
            (str(l.id), str(l.tenant_id), l.company, l.industry, l.language, l.name)
            for l in stale_leads
        ]
    logger.info(f"re_engage_stale_leads: found {len(lead_snapshots)} stale leads")

    # Step 2: make all HTTP calls with DB session closed
    notifications = []
    for lead_id, tenant_id, company, industry, language, name in lead_snapshots:
        lang = "Arabic" if language == "ar" else "English"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                    json={
                        "model": "meta-llama/llama-3.3-70b-instruct",
                        "messages": [{
                            "role": "user",
                            "content": (
                                f"Write a short, warm re-engagement WhatsApp message (max 50 words) "
                                f"for a B2B lead. Company: {company or 'unknown'}. "
                                f"Industry: {industry or 'unknown'}. "
                                f"Last contact was 20+ days ago. Language: {lang}. "
                                f"Be genuine, not pushy."
                            )
                        }]
                    }
                )
                if r.status_code != 200:
                    logger.warning(f"OpenRouter {r.status_code} for re-engage lead {lead_id}")
                    continue
                choices = r.json().get("choices", [])
                if not choices:
                    continue
                suggested_msg = choices[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"OpenRouter re-engage failed for lead {lead_id}: {e}")
            continue
        notifications.append((tenant_id, lead_id, company or name or "Lead", suggested_msg))

    # Step 3: write all notifications in a fresh DB session
    async with AsyncSessionLocal() as db:
        for tenant_id, lead_id, label, suggested_msg in notifications:
            notif = Notification(
                tenant_id=tenant_id,
                type=NotificationType.re_engage_suggestion,
                title=f"Re-engage: {label}",
                message=suggested_msg,
                data={"lead_id": lead_id, "action": "re_engage"},
            )
            db.add(notif)
        await db.commit()
    logger.info(f"re_engage_stale_leads: queued {len(notifications)} re-engagement suggestions")
