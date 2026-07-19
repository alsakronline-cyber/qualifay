"""
Conversations API — WhatsApp conversation management
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.models import Conversation, ConversationStatus
from app.api.auth import get_current_user
from app.services.evolution_service import EvolutionService
import datetime
import logging
import re

logger = logging.getLogger(__name__)
router = APIRouter()

# MIME types a browser will execute as markup/script if rendered inline. Files arrive
# from external senders (email attachments, WhatsApp docs), so treat these as downloads
# of inert bytes rather than trusting the sender's declared type.
_ACTIVE_CONTENT_TYPES = {
    "text/html", "application/xhtml+xml", "image/svg+xml",
    "text/xml", "application/xml", "application/javascript", "text/javascript",
}


def _safe_download_headers(filename: str, content_type: str) -> tuple[str, dict]:
    """(media_type, headers) for serving a sender-supplied file safely: the filename is
    stripped of header-breaking characters (CR/LF/quotes — header injection), and
    browser-executable types are forced to a plain attachment download."""
    fname = re.sub(r'[\x00-\x1f"\\;]', "_", filename or "attachment")[:150] or "attachment"
    ct = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    disposition = "inline"
    if ct in _ACTIVE_CONTENT_TYPES:
        ct = "application/octet-stream"
        disposition = "attachment"
    return ct, {
        "Content-Disposition": f'{disposition}; filename="{fname}"',
        "X-Content-Type-Options": "nosniff",
    }


class UpdateConversationRequest(BaseModel):
    status: Optional[str] = None
    ai_enabled: Optional[bool] = None
    contact_name: Optional[str] = None


class AssignRequest(BaseModel):
    user_id: str


def _conv_dict(c: Conversation, lead_stage: Optional[str] = None) -> dict:
    channel = getattr(c, "channel", None) or "whatsapp"
    if channel == "email":
        # For email, wa_jid holds the address — show it as the contact identifier.
        contact_phone = c.wa_jid or ""
    else:
        # Derive phone from JID (format: 201234567890@s.whatsapp.net)
        contact_phone = c.wa_jid.split("@")[0] if c.wa_jid else ""
        if contact_phone and not contact_phone.startswith("+"):
            contact_phone = "+" + contact_phone
    # Prefer the real WhatsApp message time; fall back to row timestamps for old rows.
    last_msg_at = c.last_message_at or c.updated_at or c.created_at
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "lead_id": c.lead_id,
        "stage": lead_stage,
        "channel": channel,
        "wa_instance_id": c.wa_instance_id,
        "instance_name": c.instance_name,
        "wa_jid": c.wa_jid,
        "contact_name": c.contact_name,
        "contact_phone": contact_phone,
        "status": c.status.value if c.status else "open",
        "ai_enabled": c.ai_enabled,
        "last_message": c.last_message,
        "last_message_at": last_msg_at.isoformat() if last_msg_at else None,
        "unread_count": c.unread_count or 0,
        "sentiment": c.sentiment or "neutral",
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("", include_in_schema=False)
@router.get("/")
async def list_conversations(
    status: Optional[str] = None,
    instance_name: Optional[str] = None,
    channel: Optional[str] = None,
    ai_enabled: Optional[bool] = None,
    search: Optional[str] = None,
    lead_id: Optional[str] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tenant conversations with optional filters."""
    tenant_id = current_user["tenant_id"]
    filters = [Conversation.tenant_id == tenant_id]

    if status:
        try:
            filters.append(Conversation.status == ConversationStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if channel in ("whatsapp", "email"):
        filters.append(Conversation.channel == channel)

    if instance_name:
        filters.append(Conversation.instance_name == instance_name)

    if lead_id:
        filters.append(Conversation.lead_id == lead_id)

    if search:
        # Search by contact name or phone/JID — powers the inbox number search.
        term = f"%{search.strip()}%"
        filters.append(or_(
            Conversation.contact_name.ilike(term),
            Conversation.wa_jid.ilike(term),
        ))

    if ai_enabled is not None:
        filters.append(Conversation.ai_enabled == ai_enabled)

    # The inbox is a list of real chats — hide message-less conversations (synced contact
    # cards from an instance's phonebook, which carry no content and only add noise). When
    # deep-linking to a specific lead we skip this filter so its thread always resolves.
    if not lead_id:
        from app.models.models import Message
        filters.append(
            select(Message.id).where(Message.conversation_id == Conversation.id).exists()
        )

    result = await db.execute(
        select(Conversation)
        .where(and_(*filters))
        # Order by the real last-message time; fall back to creation, never updated_at
        # (which gets bumped by non-message events like lead-linking and would wrongly
        # float stale threads to the top).
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    convs = result.scalars().all()

    # Batch-load the stage of each linked lead so the inbox can show/set pipeline phase
    # without an N+1 query per conversation.
    from app.models.models import Lead
    lead_ids = [c.lead_id for c in convs if c.lead_id]
    stage_by_lead: dict = {}
    if lead_ids:
        rows = await db.execute(select(Lead.id, Lead.stage).where(Lead.id.in_(lead_ids)))
        stage_by_lead = {lid: (st.value if st else None) for lid, st in rows.all()}

    return [_conv_dict(c, stage_by_lead.get(c.lead_id)) for c in convs]


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single conversation."""
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == current_user["tenant_id"],
            )
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    lead_stage = None
    if conv.lead_id:
        from app.models.models import Lead
        row = (await db.execute(select(Lead.stage).where(Lead.id == conv.lead_id))).first()
        lead_stage = row[0].value if row and row[0] else None
    return _conv_dict(conv, lead_stage)


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update conversation status, ai_enabled, or contact_name."""
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == current_user["tenant_id"],
            )
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if body.status is not None:
        try:
            conv.status = ConversationStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")

    if body.ai_enabled is not None:
        conv.ai_enabled = body.ai_enabled

    if body.contact_name is not None:
        conv.contact_name = body.contact_name

    conv.updated_at = datetime.datetime.utcnow()
    await db.commit()
    await db.refresh(conv)
    return _conv_dict(conv)


@router.post("/{conversation_id}/assign")
async def assign_conversation(
    conversation_id: str,
    body: AssignRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a conversation to a user (note: stored as metadata, conversations don't have assigned_user_id column directly)."""
    from app.models.models import User

    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == current_user["tenant_id"],
            )
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify the target user belongs to same tenant
    user_result = await db.execute(
        select(User).where(
            and_(User.id == body.user_id, User.tenant_id == current_user["tenant_id"])
        )
    )
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    # If lead exists, assign it to the user
    if conv.lead_id:
        from app.models.models import Lead
        lead_result = await db.execute(select(Lead).where(Lead.id == conv.lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead:
            lead.assigned_to = body.user_id

    await db.commit()
    return {
        "assigned": True,
        "conversation_id": conversation_id,
        "assigned_to": body.user_id,
        "assigned_to_name": target_user.full_name,
    }



class SetStageRequest(BaseModel):
    stage: str


@router.patch("/{conversation_id}/stage")
async def set_conversation_stage(
    conversation_id: str,
    body: SetStageRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually place a conversation's lead into a pipeline phase.

    If the conversation has no linked lead yet, one is created from the WhatsApp contact
    (phone + name) so the chat immediately appears on the pipeline board.
    """
    from app.models.models import Lead, LeadStage, LeadStatus, LeadSource
    from app.lib.phone import normalize_egyptian_phone

    tenant_id = current_user["tenant_id"]
    try:
        stage = LeadStage(body.stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {body.stage}")

    conv = (await db.execute(
        select(Conversation).where(
            and_(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    lead = None
    if conv.lead_id:
        lead = (await db.execute(select(Lead).where(Lead.id == conv.lead_id))).scalar_one_or_none()

    if lead:
        lead.stage = stage
    else:
        raw_phone = conv.wa_jid.split("@")[0] if conv.wa_jid else ""
        phone = normalize_egyptian_phone(raw_phone) or ("+" + raw_phone if raw_phone else None)
        lead = Lead(
            tenant_id=tenant_id, source=LeadSource.inbound_wa,
            name=conv.contact_name, company=conv.contact_name, phone=phone,
            stage=stage, status=LeadStatus.active,
        )
        db.add(lead)
        await db.flush()
        conv.lead_id = lead.id

    await db.commit()
    return {"conversation_id": conversation_id, "lead_id": lead.id, "stage": stage.value}


@router.post("/{conversation_id}/lead")
async def ensure_conversation_lead(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the lead linked to this conversation, creating one from the WhatsApp
    contact if none exists yet. Lets the inbox open a lead profile for any chat."""
    from app.models.models import Lead, LeadStatus, LeadSource
    from app.lib.phone import normalize_egyptian_phone

    tenant_id = current_user["tenant_id"]
    conv = (await db.execute(
        select(Conversation).where(
            and_(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    lead = None
    if conv.lead_id:
        lead = (await db.execute(select(Lead).where(Lead.id == conv.lead_id))).scalar_one_or_none()

    created = False
    if not lead:
        raw_phone = conv.wa_jid.split("@")[0] if conv.wa_jid else ""
        phone = normalize_egyptian_phone(raw_phone) or ("+" + raw_phone if raw_phone else None)
        lead = Lead(
            tenant_id=tenant_id, source=LeadSource.inbound_wa,
            name=conv.contact_name, company=conv.contact_name, phone=phone,
            status=LeadStatus.active,
        )
        db.add(lead)
        await db.flush()
        conv.lead_id = lead.id
        created = True
        await db.commit()

    return {"lead_id": lead.id, "created": created}


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import Message
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == current_user["tenant_id"],
            )
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    msgs = msgs_result.scalars().all()
    return [
        {
            "id": m.id,
            "direction": m.direction.value if hasattr(m.direction, "value") else str(m.direction),
            "content": m.content or "",
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "status": "",
            "push_name": None,
            "is_ai_generated": m.is_ai_generated,
            "message_type": m.message_type or "text",
            "has_media": m.message_type in ("image", "video", "audio", "document", "sticker", "media") and bool(m.wa_message_id),
            # Attachment metadata (email PDFs, images…) — data is streamed separately.
            "attachments": [
                {"filename": a.get("filename"), "content_type": a.get("content_type"), "size": a.get("size")}
                for a in (m.attachments or [])
            ],
        }
        for m in msgs
    ]


@router.get("/messages/{message_id}/attachment/{idx}")
async def download_attachment(
    message_id: str,
    idx: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream an email/message attachment (by index) from object storage, tenant-scoped."""
    from app.models.models import Message
    from app.services.storage_service import get_attachment
    msg = (await db.execute(
        select(Message).join(Conversation, Message.conversation_id == Conversation.id)
        .where(and_(Message.id == message_id, Conversation.tenant_id == current_user["tenant_id"]))
    )).scalar_one_or_none()
    if not msg or not msg.attachments or idx < 0 or idx >= len(msg.attachments):
        raise HTTPException(status_code=404, detail="Attachment not found")
    att = msg.attachments[idx]
    data, ct = get_attachment(att.get("key", ""))
    if not data:
        raise HTTPException(status_code=404, detail="Attachment unavailable")
    media_type, headers = _safe_download_headers(
        att.get("filename", "attachment"), att.get("content_type") or ct or "")
    return Response(content=data, media_type=media_type, headers=headers)


@router.get("/{conversation_id}/messages/{message_id}/media")
async def get_message_media(
    conversation_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch media (image/video/audio/document) for a message from Evolution API on demand."""
    import base64 as b64
    import httpx
    from fastapi.responses import Response
    from app.models.models import Message
    from app.core.config import settings

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

    msg_result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
        )
    )
    msg = msg_result.scalar_one_or_none()
    if not msg or not msg.wa_message_id:
        raise HTTPException(status_code=404, detail="Media not found")

    from_me = msg.direction.value == "outbound" if hasattr(msg.direction, "value") else str(msg.direction) == "outbound"

    try:
        base_url = settings.EVOLUTION_API_URL
        headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{base_url}/chat/getBase64FromMediaMessage/{conv.instance_name}",
                headers=headers,
                json={"message": {"key": {"id": msg.wa_message_id, "remoteJid": conv.wa_jid, "fromMe": from_me}}},
            )
            if r.status_code >= 300:
                raise HTTPException(status_code=502, detail="Media fetch failed")
            data = r.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Media service unavailable")

    b64_data = data.get("base64")
    mimetype = data.get("mimetype", "application/octet-stream")
    filename = data.get("fileName") or message_id
    if not b64_data:
        raise HTTPException(status_code=404, detail="Media not available")

    file_bytes = b64.b64decode(b64_data)
    media_type, safe_headers = _safe_download_headers(filename, mimetype)
    return Response(content=file_bytes, media_type=media_type, headers=safe_headers)



class SendMessageRequest(BaseModel):
    content: str


class ComposeRequest(BaseModel):
    channel: str            # 'whatsapp' | 'email'
    to: str                 # phone (any Egyptian format) or email address
    subject: Optional[str] = None
    content: str


@router.post("/compose")
async def compose_message(
    body: ComposeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a brand-new conversation with someone not yet on the list: normalize the
    recipient, create the lead + conversation if needed, send the first WhatsApp/email,
    and return the conversation id so the UI can open the thread."""
    tenant_id = current_user["tenant_id"]
    channel = (body.channel or "whatsapp").lower()
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="الرسالة فارغة")

    from app.models.models import (
        Lead, LeadSource, LeadStage, LeadStatus, Message, MessageDirection, WaInstance,
    )

    instance_name = "email"
    if channel == "email":
        addr = (body.to or "").strip().lower()
        if "@" not in addr:
            raise HTTPException(status_code=400, detail="بريد إلكتروني غير صالح")
        wa_jid = addr
    else:
        channel = "whatsapp"
        from app.lib.phone import normalize_egyptian_phone
        phone = normalize_egyptian_phone(body.to)
        if not phone:
            raise HTTPException(status_code=400, detail="رقم هاتف غير صالح")
        wa_jid = phone.lstrip("+") + "@s.whatsapp.net"
        inst = (await db.execute(select(WaInstance).where(and_(
            WaInstance.tenant_id == tenant_id, WaInstance.status.in_(["connected", "open"])
        )))).scalars().first()
        if not inst:
            raise HTTPException(status_code=400, detail="لا يوجد جهاز واتساب متصل")
        instance_name = inst.instance_name
        # Compose is a cold first-contact send, so it respects the WhatsApp warmup/daily
        # cap (anti-ban). Replies to existing threads are NOT capped — answering someone
        # who messaged you is warm and safe. Only the cold outbound path is gated here.
        from app.services.warmup_service import warmup_service
        allowed, used, cap = await warmup_service.check_wa_limit(inst.id, db)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"تم بلوغ الحد اليومي لواتساب ({used}/{cap}). حاول غداً.",
            )

    # Find or create the lead (dedupe by email/phone within the tenant).
    if channel == "email":
        lead = (await db.execute(select(Lead).where(and_(
            Lead.tenant_id == tenant_id, Lead.email.ilike(wa_jid)
        )).order_by(Lead.created_at.desc()))).scalars().first()
    else:
        lead = (await db.execute(select(Lead).where(and_(
            Lead.tenant_id == tenant_id, Lead.phone == phone
        )).order_by(Lead.created_at.desc()))).scalars().first()
    if not lead:
        lead = Lead(
            tenant_id=tenant_id, source=LeadSource.manual, name=None,
            phone=(None if channel == "email" else phone),
            email=(wa_jid if channel == "email" else None),
            stage=LeadStage.new, status=LeadStatus.active,
        )
        db.add(lead)
        await db.flush()

    # Find or create the conversation.
    conv = (await db.execute(select(Conversation).where(and_(
        Conversation.tenant_id == tenant_id, Conversation.channel == channel,
        Conversation.wa_jid == wa_jid,
    )))).scalar_one_or_none()
    if not conv:
        conv = Conversation(
            tenant_id=tenant_id, lead_id=lead.id, instance_name=instance_name,
            wa_jid=wa_jid, channel=channel, contact_name=lead.name,
            status=ConversationStatus.open, ai_enabled=False,
        )
        db.add(conv)
        await db.flush()
    elif not conv.lead_id:
        conv.lead_id = lead.id

    # Send the first message.
    if channel == "email":
        from app.services.email_service import send_for_tenant
        subject = (body.subject or "").strip() or "رسالة من Qualifay"
        try:
            await send_for_tenant(db, tenant_id, wa_jid, subject, content)
        except RuntimeError:
            raise HTTPException(status_code=502, detail="SMTP غير مهيأ")
        except Exception as e:
            logger.error(f"compose email error: {e}")
            raise HTTPException(status_code=502, detail=f"فشل إرسال البريد: {e}")
        msg_type = "email"
    else:
        try:
            await EvolutionService().send_text(instance_name, wa_jid, content)
        except Exception as e:
            logger.error(f"compose whatsapp error: {e}")
            raise HTTPException(status_code=502, detail=f"فشل إرسال واتساب: {e}")
        # Count this cold send against the instance's daily warmup cap.
        await warmup_service.increment_wa_sent(inst.id, db)
        msg_type = "text"

    now = datetime.datetime.utcnow()
    db.add(Message(
        conversation_id=conv.id, direction=MessageDirection.outbound,
        content=content, message_type=msg_type,
    ))
    conv.last_message = content
    conv.last_message_at = now
    conv.updated_at = now
    await db.commit()
    return {"sent": True, "conversation_id": conv.id}


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a WhatsApp message in a conversation."""
    tenant_id = current_user["tenant_id"]
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from app.models.models import Message, MessageDirection

    channel = getattr(conv, "channel", None) or "whatsapp"
    if channel == "email":
        # Reply by email — wa_jid holds the address.
        from app.services.email_service import send_for_tenant
        subject = f"رد: {(conv.contact_name or conv.wa_jid)}"
        try:
            await send_for_tenant(db, tenant_id, conv.wa_jid, subject, body.content)
        except RuntimeError:
            raise HTTPException(status_code=502, detail="SMTP not configured")
        except Exception as e:
            logger.error(f"send_message email error: {e}")
            raise HTTPException(status_code=502, detail=f"Email send failed: {e}")
        msg_type = "email"
    else:
        evo = EvolutionService()
        try:
            await evo.send_text(conv.instance_name, conv.wa_jid, body.content)
        except Exception as e:
            logger.error(f"send_message evo error: {e}")
            raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {e}")
        msg_type = "text"

    new_msg = Message(
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        content=body.content,
        message_type=msg_type,
    )
    db.add(new_msg)
    conv.last_message = body.content
    conv.updated_at = datetime.datetime.utcnow()
    await db.commit()
    return {"sent": True}


@router.post("/{conversation_id}/media")
async def send_media_message(
    conversation_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file and send it into the conversation as a WhatsApp media message."""
    import base64 as b64
    from app.models.models import Message, MessageDirection

    tenant_id = current_user["tenant_id"]
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > 16 * 1024 * 1024:  # WhatsApp media cap
        raise HTTPException(status_code=413, detail="File too large (max 16MB)")

    mimetype = file.content_type or "application/octet-stream"
    if mimetype.startswith("image/"):
        mediatype = "image"
    elif mimetype.startswith("video/"):
        mediatype = "video"
    elif mimetype.startswith("audio/"):
        mediatype = "audio"
    else:
        mediatype = "document"

    media_b64 = b64.b64encode(raw).decode()
    evo = EvolutionService()
    try:
        await evo.send_media(
            conv.instance_name, conv.wa_jid, media_b64,
            mediatype, mimetype, file.filename or "file", caption,
        )
    except Exception as e:
        logger.error(f"send_media evo error: {e}")
        raise HTTPException(status_code=502, detail=f"WhatsApp media send failed: {e}")

    new_msg = Message(
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        content=caption or file.filename or "[ملف]",
        message_type=mediatype,
    )
    db.add(new_msg)
    conv.last_message = caption or f"[{mediatype}]"
    conv.updated_at = datetime.datetime.utcnow()
    await db.commit()
    return {"sent": True, "mediatype": mediatype}


@router.post("/{conversation_id}/voice")
async def send_voice_message(
    conversation_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record → send as a WhatsApp voice note (PTT).

    Browsers record webm/opus; WhatsApp needs ogg/opus to render the mic bubble, so we
    transcode with ffmpeg before handing it to Evolution's sendWhatsAppAudio.
    """
    import base64 as b64, asyncio, tempfile, os
    from app.models.models import Message, MessageDirection

    tenant_id = current_user["tenant_id"]
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty recording")
    if len(raw) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Recording too large")

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in")
        dst = os.path.join(tmp, "out.ogg")
        with open(src, "wb") as f:
            f.write(raw)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", src,
            "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", dst,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0 or not os.path.exists(dst):
            logger.error(f"voice transcode failed: {err.decode()[:500] if err else ''}")
            raise HTTPException(status_code=502, detail="Voice transcode failed")
        with open(dst, "rb") as f:
            ogg = f.read()

    audio_b64 = b64.b64encode(ogg).decode()
    evo = EvolutionService()
    try:
        await evo.send_audio(conv.instance_name, conv.wa_jid, audio_b64)
    except Exception as e:
        logger.error(f"send_voice evo error: {e}")
        raise HTTPException(status_code=502, detail=f"WhatsApp voice send failed: {e}")

    new_msg = Message(
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        content="[رسالة صوتية]",
        message_type="audio",
    )
    db.add(new_msg)
    conv.last_message = "[رسالة صوتية]"
    conv.updated_at = datetime.datetime.utcnow()
    await db.commit()
    return {"sent": True}


@router.delete("/{conversation_id}/messages/{message_id}")
async def delete_message(
    conversation_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message: revoke on WhatsApp (deleteForEveryone) then remove locally.

    WhatsApp revoke only works within its time window and mainly for our own outbound
    messages; if it fails we still remove the message from the Qualifay inbox.
    """
    from app.models.models import Message

    tenant_id = current_user["tenant_id"]
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = (await db.execute(
        select(Message).where(
            Message.id == message_id, Message.conversation_id == conversation_id
        )
    )).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    revoked = False
    if msg.wa_message_id:
        from_me = (msg.direction.value if hasattr(msg.direction, "value") else str(msg.direction)) == "outbound"
        try:
            evo = EvolutionService()
            await evo.delete_message(conv.instance_name, {
                "id": msg.wa_message_id,
                "remoteJid": conv.wa_jid,
                "fromMe": from_me,
            })
            revoked = True
        except Exception as e:
            logger.warning(f"deleteForEveryone failed (still removing locally): {e}")

    await db.delete(msg)
    await db.commit()
    return {"deleted": True, "revoked_on_whatsapp": revoked}


@router.post("/sync-to-pipeline", status_code=202)
async def sync_conversations_to_pipeline(
    current_user: dict = Depends(get_current_user),
):
    """Kick off (in the background) an analysis of this tenant's WhatsApp chats, turning
    the ones with real buying intent into CRM leads placed in the correct pipeline stage.

    Runs as a Celery task because it makes one AI call per conversation — too slow and
    costly to block an HTTP request on. Progress lands as a notification when it finishes.
    """
    from app.workers.ai_tasks import sync_wa_to_pipeline
    sync_wa_to_pipeline.delay(current_user["tenant_id"])
    return {"status": "started"}
