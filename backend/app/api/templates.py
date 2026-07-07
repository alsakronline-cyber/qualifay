"""Message templates — reusable WhatsApp/email copy with {{placeholders}}."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.api.auth import get_current_user

router = APIRouter()

# Ready-to-use professional starters, seeded once per tenant so there's something to
# edit from day one rather than a blank page.
STARTERS = [
    {"name": "تعريف أولي — واتساب", "channel": "whatsapp", "category": "outreach", "subject": None,
     "body": "مرحباً {{name}} 👋\nأتواصل معك بخصوص {{company}}. نحن نساعد شركات {{industry}} في {{city}} على تحقيق نتائج أفضل بأقل جهد.\nهل يناسبك أن نتحدث بإيجاز هذا الأسبوع؟"},
    {"name": "تعريف أولي — بريد", "channel": "email", "category": "outreach", "subject": "بخصوص {{company}}",
     "body": "مرحباً {{name}}،\n\nلاحظت أن {{company}} تعمل في مجال {{industry}}، ونحن نساعد شركات مشابهة في {{city}} على النمو.\n\nهل يمكن تحديد ١٥ دقيقة هذا الأسبوع لأشرح كيف؟\n\nمع خالص التقدير،"},
    {"name": "متابعة لطيفة", "channel": "both", "category": "follow_up", "subject": "متابعة — {{company}}",
     "body": "مرحباً {{name}}، أتابع رسالتي السابقة فقط. هل أتيحت لك فرصة للاطلاع؟ يسعدني الإجابة على أي استفسار."},
    {"name": "طلب اجتماع", "channel": "both", "category": "meeting", "subject": "اقتراح موعد قصير",
     "body": "مرحباً {{name}}، يسعدني ترتيب مكالمة قصيرة لأعرض كيف يمكننا مساعدة {{company}}. هل يناسبك غداً؟ اقترح وقتاً مناسباً وسأتكيّف معه."},
    {"name": "شكر بعد الرد", "channel": "both", "category": "reply", "subject": None,
     "body": "شكراً لردك {{name}}! سأرسل لك التفاصيل الكاملة حالاً. وإن كان لديك أي سؤال، أنا في الخدمة."},
    {"name": "Intro — English", "channel": "email", "category": "outreach", "subject": "Quick note for {{company}}",
     "body": "Hi {{name}},\n\nI noticed {{company}} works in {{industry}} — we help similar teams in {{city}} grow with less effort.\n\nWould 15 minutes this week be useful?\n\nBest regards,"},
]


def _dict(t) -> dict:
    return {
        "id": t.id, "name": t.name, "channel": t.channel, "category": t.category,
        "subject": t.subject, "body": t.body,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


async def _seed_if_empty(tenant_id: str, db: AsyncSession):
    from app.models.models import MessageTemplate
    count = (await db.execute(
        select(MessageTemplate).where(MessageTemplate.tenant_id == tenant_id).limit(1)
    )).scalar_one_or_none()
    if count:
        return
    for s in STARTERS:
        db.add(MessageTemplate(tenant_id=tenant_id, **s))
    await db.commit()


class TemplateBody(BaseModel):
    name: str
    channel: str = "both"
    category: Optional[str] = None
    subject: Optional[str] = None
    body: str


@router.get("")
@router.get("/")
async def list_templates(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import MessageTemplate
    tenant_id = current_user["tenant_id"]
    await _seed_if_empty(tenant_id, db)
    rows = (await db.execute(
        select(MessageTemplate).where(MessageTemplate.tenant_id == tenant_id)
        .order_by(MessageTemplate.updated_at.desc())
    )).scalars().all()
    return [_dict(t) for t in rows]


@router.post("")
@router.post("/")
async def create_template(body: TemplateBody, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import MessageTemplate
    t = MessageTemplate(tenant_id=current_user["tenant_id"], **body.dict())
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _dict(t)


async def _get(tid, tenant_id, db):
    from app.models.models import MessageTemplate
    t = (await db.execute(select(MessageTemplate).where(and_(
        MessageTemplate.id == tid, MessageTemplate.tenant_id == tenant_id
    )))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.patch("/{tid}")
async def update_template(tid: str, body: TemplateBody, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await _get(tid, current_user["tenant_id"], db)
    for k, v in body.dict().items():
        setattr(t, k, v)
    await db.commit()
    return _dict(t)


@router.delete("/{tid}")
async def delete_template(tid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await _get(tid, current_user["tenant_id"], db)
    await db.delete(t)
    await db.commit()
    return {"deleted": True}
