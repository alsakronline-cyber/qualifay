"""
Messages API — Send and retrieve WhatsApp messages
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.models.models import Conversation, Message, MessageDirection, ConversationStatus
from app.services.evolution_service import evolution_service
from app.api.auth import get_current_user

router = APIRouter()


class SendMessageRequest(BaseModel):
    content: str
    message_type: str = "text"
    media_url: Optional[str] = None


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "wa_message_id": m.wa_message_id,
        "direction": m.direction.value if m.direction else None,
        "content": m.content,
        "message_type": m.message_type or "text",
        "media_url": m.media_url,
        "is_ai_generated": m.is_ai_generated,
        "ai_confidence": m.ai_confidence,
        "transcription": m.transcription,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/{conversation_id}")
async def get_messages(
    conversation_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated messages for a conversation."""
    # Verify conversation belongs to tenant
    conv_result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == current_user["tenant_id"],
            )
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    msgs = result.scalars().all()

    # Mark conversation unread_count as 0 when messages are fetched
    if conv.unread_count and conv.unread_count > 0:
        conv.unread_count = 0
        await db.commit()

    return [_msg_dict(m) for m in msgs]


@router.post("/{conversation_id}/send")
async def send_message(
    conversation_id: str,
    req: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a manual message via Evolution API and save to DB."""
    # Verify conversation belongs to tenant
    conv_result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == current_user["tenant_id"],
            )
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not conv.wa_jid:
        raise HTTPException(status_code=400, detail="Conversation has no WhatsApp JID")

    if not conv.instance_name:
        raise HTTPException(status_code=400, detail="Conversation has no WhatsApp instance")

    # Send via Evolution API
    try:
        if req.message_type == "image" and req.media_url:
            await evolution_service.send_image(conv.instance_name, conv.wa_jid, req.media_url, req.content)
        else:
            await evolution_service.send_text(conv.instance_name, conv.wa_jid, req.content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send message: {e}")

    # Save to DB
    msg = Message(
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        content=req.content,
        message_type=req.message_type,
        media_url=req.media_url,
        is_ai_generated=False,
    )
    db.add(msg)

    conv.last_message = req.content[:200]
    conv.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(msg)

    return _msg_dict(msg)
