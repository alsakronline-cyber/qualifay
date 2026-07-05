"""
Celery Tasks — AI Processing Pipeline
"""
import asyncio
import logging
import time
from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async coroutine in Celery sync context (fresh loop + engine dispose)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro
    try:
        return loop.run_until_complete(_wrapped())
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, queue="messages")
def process_incoming_message(self, webhook_data: dict):
    """
    Main pipeline for incoming WhatsApp message:
    1. Parse & save to DB
    2. Classify intent via AI (fast model)
    3. If AI auto-reply enabled → trigger ai_reply task
    4. Notify connected WebSocket clients
    """
    try:
        return run_async(_process_message(webhook_data))
    except Exception as exc:
        logger.error(f"Message processing failed: {exc}")
        raise self.retry(exc=exc, countdown=5)


async def _process_message(webhook_data: dict):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Contact, Conversation, Message, MessageDirection, ConversationStatus
    from app.services.ai_service import ai_service
    from app.services.evolution_service import evolution_service
    from sqlalchemy import select

    # Extract WA event fields
    event = webhook_data.get("event", "")
    instance = webhook_data.get("instance", "")
    data = webhook_data.get("data", {})

    if event != "messages.upsert":
        return {"skipped": True, "reason": "not a message event"}

    msg_data = data.get("message", {})
    key = data.get("key", {})
    from_me = key.get("fromMe", False)

    if from_me:
        return {"skipped": True, "reason": "own message"}

    wa_jid = key.get("remoteJid", "")
    wa_msg_id = key.get("id", "")
    content = (
        msg_data.get("conversation") or
        msg_data.get("extendedTextMessage", {}).get("text") or
        "[media]"
    )

    async with AsyncSessionLocal() as db:
        # Find or create contact
        result = await db.execute(select(Contact).where(Contact.wa_jid == wa_jid))
        contact = result.scalar_one_or_none()

        if not contact:
            phone = wa_jid.replace("@s.whatsapp.net", "").replace("@g.us", "")
            contact = Contact(
                wa_jid=wa_jid,
                phone=phone,
                name=data.get("pushName", phone),
            )
            db.add(contact)
            await db.flush()

        # Find or create conversation
        result = await db.execute(
            select(Conversation)
            .where(Conversation.contact_id == contact.id)
            .where(Conversation.instance_name == instance)
            .where(Conversation.status != ConversationStatus.resolved)
        )
        conv = result.scalar_one_or_none()

        if not conv:
            conv = Conversation(
                contact_id=contact.id,
                instance_name=instance,
                status=ConversationStatus.open,
                ai_enabled=settings.AI_AUTO_REPLY_ENABLED,
            )
            db.add(conv)
            await db.flush()

        # Save message
        msg = Message(
            conversation_id=conv.id,
            wa_message_id=wa_msg_id,
            direction=MessageDirection.inbound,
            content=content,
        )
        db.add(msg)

        # Update conversation
        conv.last_message = content[:200]
        conv.unread_count = (conv.unread_count or 0) + 1

        await db.commit()

        # Classify intent (fast)
        intent_data = await ai_service.classify_intent(content, contact.name or "")
        logger.info(f"Intent: {intent_data}")

        # Queue AI reply if enabled
        if conv.ai_enabled and not intent_data.get("requires_human", False):
            delay = settings.AI_AUTO_REPLY_DELAY_SECONDS
            run_ai_reply.apply_async(
                kwargs={
                    "conversation_id": conv.id,
                    "contact_id": contact.id,
                    "instance_name": instance,
                    "message": content,
                    "contact_name": contact.name or "Customer",
                    "wa_jid": wa_jid,
                    "intent": intent_data.get("intent", "other"),
                    "language": intent_data.get("language", "auto"),
                },
                countdown=delay,
                queue="ai",
            )

        return {"conversation_id": conv.id, "contact_id": contact.id, "intent": intent_data}


@celery_app.task(bind=True, max_retries=2, queue="ai")
def run_ai_reply(self, conversation_id: str, contact_id: str, instance_name: str,
                 message: str, contact_name: str, wa_jid: str,
                 intent: str, language: str = "auto"):
    """Generate and send an AI reply via Evolution API."""
    try:
        return run_async(_run_ai_reply(
            conversation_id, contact_id, instance_name,
            message, contact_name, wa_jid, intent, language
        ))
    except Exception as exc:
        logger.error(f"AI reply failed: {exc}")
        raise self.retry(exc=exc, countdown=10)


async def _run_ai_reply(conversation_id, contact_id, instance_name,
                        message, contact_name, wa_jid, intent, language):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Conversation, Message, MessageDirection
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
        history = [{"direction": m.direction.value, "content": m.content} for m in reversed(msgs)]

        # Generate reply
        reply = await ai_service.generate_reply(
            message=message,
            contact_name=contact_name,
            conversation_history=history,
            language=language,
        )

        if not reply:
            logger.warning("AI returned empty reply — skipping")
            return {"sent": False, "reason": "empty_reply"}

        # Show typing indicator
        await evolution_service.send_typing(instance_name, wa_jid)
        await asyncio.sleep(1.5)

        # Send via Evolution API
        result_wa = await evolution_service.send_text(instance_name, wa_jid, reply)

        # Save to DB
        out_msg = Message(
            conversation_id=conversation_id,
            direction=MessageDirection.outbound,
            content=reply,
            is_ai_generated=True,
            ai_confidence=0.85,
        )
        db.add(out_msg)
        await db.commit()

        logger.info(f"AI reply sent to {wa_jid}: {reply[:60]}...")
        return {"sent": True, "reply": reply[:100]}


@celery_app.task(queue="ai")
def update_contact_ai_summary(contact_id: str):
    """Regenerate AI summary for a contact (called periodically)."""
    return run_async(_update_summary(contact_id))


async def _update_summary(contact_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Contact, Message, Conversation
    from app.services.ai_service import ai_service
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Contact).where(Contact.id == contact_id))
        contact = result.scalar_one_or_none()
        if not contact:
            return

        result = await db.execute(
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.contact_id == contact_id)
            .order_by(Message.created_at.desc())
            .limit(50)
        )
        msgs = result.scalars().all()

        if not msgs:
            return

        msg_list = [{"direction": m.direction.value, "content": m.content} for m in msgs]
        summary = await ai_service.summarize_contact(contact.name or "Unknown", msg_list)

        contact.ai_summary = summary
        await db.commit()
        return {"updated": True}


@celery_app.task(queue="ai")
def score_lead_task(contact_id: str):
    """Update lead score for a contact."""
    return run_async(_score_lead(contact_id))


async def _score_lead(contact_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Contact, Message, Conversation
    from app.services.ai_service import ai_service
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Contact).where(Contact.id == contact_id))
        contact = result.scalar_one_or_none()
        if not contact:
            return

        result = await db.execute(
            select(Message)
            .join(Conversation)
            .where(Conversation.contact_id == contact_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        msgs = [{"content": m.content} for m in result.scalars().all()]

        score = await ai_service.score_lead(
            {"name": contact.name, "phone": contact.phone},
            msgs
        )
        contact.lead_score = score
        await db.commit()
        return {"score": score}
