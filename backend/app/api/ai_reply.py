"""
AI Reply API — P4: Human Control Toggle for AI Replies
- suggest-reply: Generate AI reply suggestion (no auto-send)
- send-approved: Send a human-approved message via Evolution API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import httpx
import logging

from app.core.database import get_db
from app.core.config import settings
from app.models.models import Conversation, Message, MessageDirection
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

AI_SYSTEM_PROMPT = """You are a professional B2B sales assistant for an Egyptian company.
Always reply in Arabic (العربية) by default, unless the customer writes in English.
Keep replies concise, warm, and professional. Guide the conversation toward booking a meeting.
Never claim to be AI. Never make promises about pricing."""


class SuggestReplyRequest(BaseModel):
    context: Optional[str] = None


class SendApprovedRequest(BaseModel):
    message: str
    wa_jid: str
    instance_name: str


@router.post("/{conv_id}/suggest-reply")
async def suggest_reply(
    conv_id: str,
    req: Optional[SuggestReplyRequest] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI reply suggestion for a conversation. Does NOT send — human approval required."""
    if req is None:
        req = SuggestReplyRequest()
    tenant_id = current_user["tenant_id"]

    # Load conversation + verify ownership
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Load last 10 messages for context
    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    messages = list(reversed(msgs_result.scalars().all()))

    # Build message history for Groq
    chat_history = []
    for msg in messages:
        role = "assistant" if msg.direction == MessageDirection.outbound else "user"
        if msg.content:
            chat_history.append({"role": role, "content": msg.content})

    if req.context:
        safe_context = req.context[:200].replace("<", "").replace(">", "")
        chat_history.insert(0, {"role": "system", "content": f"Additional context from agent: {safe_context}"})

    if not chat_history:
        chat_history.append({
            "role": "user",
            "content": "Hello, I'm interested in your services."
        })

    # Call Groq API
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": AI_SYSTEM_PROMPT}] + chat_history,
        "max_tokens": 500,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Groq API error: {e.response.text}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Groq request failed: {e}")
        raise HTTPException(status_code=502, detail="AI service unavailable")

    choices = data.get("choices", [])
    if not choices:
        raise HTTPException(status_code=502, detail="AI returned empty response")
    suggestion = choices[0].get("message", {}).get("content", "").strip()
    if not suggestion:
        raise HTTPException(status_code=502, detail="AI returned empty suggestion")
    tokens_used = data.get("usage", {}).get("total_tokens", 0)

    # Log ai_suggested activity (import here to avoid circular)
    try:
        from app.services.activity_service import log_activity
        from app.models.models import ActivityType
        entry = await log_activity(
            db=db,
            tenant_id=tenant_id,
            activity_type=ActivityType.ai_suggested,
            summary=f"AI reply suggested for conversation {conv_id[:8]}...",
            entity_type="conversation",
            entity_id=conv_id,
            user_id=current_user.get("user_id"),
            extra_data={"tokens_used": tokens_used, "model": GROQ_MODEL},
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"Could not log ai_suggested activity: {e}")

    return {
        "suggestion": suggestion,
        "model": GROQ_MODEL,
        "tokens_used": tokens_used,
    }


@router.post("/{conv_id}/send-approved")
async def send_approved(
    conv_id: str,
    req: SendApprovedRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a human-approved message via Evolution API and record it in DB."""
    tenant_id = current_user["tenant_id"]

    # Verify conversation ownership
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Normalise phone: strip @s.whatsapp.net if present
    phone = req.wa_jid.split("@")[0] if "@" in req.wa_jid else req.wa_jid

    # Use instance_name from DB (not from request) to prevent cross-tenant sends
    safe_instance_name = conv.instance_name or req.instance_name
    evo_url = f"{settings.EVOLUTION_API_URL}/message/sendText/{safe_instance_name}"
    evo_headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    evo_payload = {
        "number": phone,
        "text": req.message,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(evo_url, json=evo_payload, headers=evo_headers)
            resp.raise_for_status()
            evo_data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Evolution API send error: {e.response.text}")
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Evolution API request failed: {e}")
        raise HTTPException(status_code=502, detail="WhatsApp service unavailable")

    # Extract message ID from Evolution response
    wa_message_id = (
        evo_data.get("key", {}).get("id")
        or evo_data.get("id")
        or evo_data.get("messageId")
    )

    # Save outbound message to DB
    msg = Message(
        conversation_id=conv_id,
        wa_message_id=wa_message_id,
        direction=MessageDirection.outbound,
        content=req.message,
        message_type="text",
        is_ai_generated=False,
    )
    db.add(msg)

    # Update conversation last_message
    from datetime import datetime, timezone
    conv.last_message = req.message
    conv.updated_at = datetime.now(timezone.utc)

    # Log message_sent activity
    try:
        from app.services.activity_service import log_activity
        from app.models.models import ActivityType
        await log_activity(
            db=db,
            tenant_id=tenant_id,
            activity_type=ActivityType.message_sent,
            summary=f"Message sent to {conv.contact_name or phone}",
            entity_type="conversation",
            entity_id=conv_id,
            user_id=current_user.get("user_id"),
            extra_data={"wa_jid": req.wa_jid, "instance_name": safe_instance_name, "wa_message_id": wa_message_id},
        )
    except Exception as e:
        logger.warning(f"Could not log message_sent activity: {e}")

    await db.commit()

    return {
        "sent": True,
        "message_id": wa_message_id,
    }
