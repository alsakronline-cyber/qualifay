"""Conversion flows — sector-agnostic actions (booking / order / quote / callback)."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.core.database import get_db
from app.api.auth import get_current_user

router = APIRouter()

DEFAULT_FLOWS = [
    {"name": "حجز موعد", "type": "booking", "config": {}},
    {"name": "طلب / أوردر", "type": "order", "config": {}},
    {"name": "طلب اتصال", "type": "callback", "config": {}},
    {"name": "عرض سعر", "type": "quote", "config": {}},
]

# Which pipeline stage a completed action moves the lead to.
STAGE_MAP = {"booking": "meeting", "order": "won", "quote": "proposal", "callback": "meeting", "custom": "negotiation"}


def _confirmation(ftype: str, data: dict) -> str:
    if ftype == "booking":
        return f"تم تأكيد موعدك: {data.get('datetime', '')} ✅\nبانتظارك، وسنذكّرك قبل الموعد."
    if ftype == "order":
        items = data.get("items", [])
        lines = "\n".join(f"• {i.get('name', '')} ×{i.get('qty', 1)}" for i in items) or "—"
        total = data.get("total")
        return f"تم استلام طلبك ✅\n{lines}" + (f"\nالإجمالي: {total}" if total else "") + "\nسنتواصل معك لتأكيد التوصيل."
    if ftype == "quote":
        return "تم استلام طلب عرض السعر ✅ سنرسله لك في أقرب وقت."
    if ftype == "callback":
        return f"تم تسجيل طلب الاتصال ✅ سنتصل بك: {data.get('preferred_time', 'قريباً')}."
    return "تم استلام طلبك ✅"


def _flow_dict(f) -> dict:
    return {"id": f.id, "name": f.name, "type": f.type, "active": f.active, "config": f.config or {}}


def _sub_dict(s) -> dict:
    return {
        "id": s.id, "flow_id": s.flow_id, "lead_id": s.lead_id, "type": s.type,
        "data": s.data or {}, "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _seed(tenant_id, db):
    from app.models.models import ConversionFlow
    if (await db.execute(select(ConversionFlow).where(ConversionFlow.tenant_id == tenant_id).limit(1))).scalar_one_or_none():
        return
    for fl in DEFAULT_FLOWS:
        db.add(ConversionFlow(tenant_id=tenant_id, **fl))
    await db.commit()


class FlowIn(BaseModel):
    name: str
    type: str = "booking"
    active: bool = True
    config: dict = {}


class SubmitIn(BaseModel):
    flow_id: str
    conversation_id: Optional[str] = None
    lead_id: Optional[str] = None
    data: dict = {}
    send_confirmation: bool = True


@router.get("")
@router.get("/")
async def list_flows(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import ConversionFlow
    tid = current_user["tenant_id"]
    await _seed(tid, db)
    rows = (await db.execute(select(ConversionFlow).where(ConversionFlow.tenant_id == tid))).scalars().all()
    return [_flow_dict(f) for f in rows]


@router.post("")
@router.post("/")
async def create_flow(body: FlowIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import ConversionFlow
    f = ConversionFlow(tenant_id=current_user["tenant_id"], **body.dict())
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return _flow_dict(f)


@router.get("/submissions")
async def list_submissions(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import FlowSubmission
    rows = (await db.execute(
        select(FlowSubmission).where(FlowSubmission.tenant_id == current_user["tenant_id"])
        .order_by(desc(FlowSubmission.created_at)).limit(200)
    )).scalars().all()
    return [_sub_dict(s) for s in rows]


@router.post("/submit")
async def submit_flow(body: SubmitIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import (
        ConversionFlow, FlowSubmission, Conversation, Lead, LeadStage, Message, MessageDirection,
    )
    tid = current_user["tenant_id"]
    flow = (await db.execute(select(ConversionFlow).where(and_(
        ConversionFlow.id == body.flow_id, ConversionFlow.tenant_id == tid
    )))).scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    conv = None
    lead_id = body.lead_id
    if body.conversation_id:
        conv = (await db.execute(select(Conversation).where(and_(
            Conversation.id == body.conversation_id, Conversation.tenant_id == tid
        )))).scalar_one_or_none()
        if conv and not lead_id:
            lead_id = conv.lead_id

    sub = FlowSubmission(tenant_id=tid, flow_id=flow.id, lead_id=lead_id,
                         conversation_id=body.conversation_id, type=flow.type, data=body.data, status="confirmed")
    db.add(sub)

    # Advance the lead to the mapped stage.
    if lead_id:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if lead:
            try:
                lead.stage = LeadStage(STAGE_MAP.get(flow.type, "negotiation"))
            except ValueError:
                pass

    # Send a confirmation on the conversation's channel.
    confirmation = _confirmation(flow.type, body.data)
    sent = False
    if body.send_confirmation and conv:
        try:
            if (getattr(conv, "channel", "whatsapp") or "whatsapp") == "email":
                from app.services.email_service import email_service
                if email_service.is_configured():
                    await email_service.send(conv.wa_jid, "تأكيد", confirmation)
                    sent = True
            else:
                from app.services.evolution_service import evolution_service
                await evolution_service.send_text(conv.instance_name, conv.wa_jid, confirmation)
                sent = True
            db.add(Message(conversation_id=conv.id, direction=MessageDirection.outbound,
                           content=confirmation, message_type="text"))
            conv.last_message = confirmation[:200]
        except Exception:
            sent = False

    await db.commit()
    await db.refresh(sub)

    # Fan out to tenant webhooks (n8n/Zapier/custom).
    try:
        from app.workers.webhook_tasks import emit
        payload = {"submission_id": sub.id, "type": flow.type, "lead_id": lead_id, "data": body.data}
        emit(tid, "flow.submitted", payload)
        if flow.type == "booking":
            emit(tid, "booking.created", payload)
    except Exception:
        pass

    return {**_sub_dict(sub), "confirmation_sent": sent}
