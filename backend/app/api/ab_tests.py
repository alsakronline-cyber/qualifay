"""A/B tests for outreach — create a test with 2+ message variants; the outreach path
allocates variants (least-sent) and reply rates are tracked per variant so the tenant
can see which copy wins."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.auth import get_current_user

router = APIRouter()


def _variant(v) -> dict:
    sent = v.sent_count or 0
    replied = v.reply_count or 0
    return {
        "id": v.id, "label": v.label, "subject": v.subject, "body": v.body,
        "sent_count": sent, "reply_count": replied,
        "reply_rate": round(replied / sent * 100, 1) if sent else 0.0,
    }


def _test(t) -> dict:
    variants = [_variant(v) for v in sorted(t.variants, key=lambda x: x.label)]
    winner = max(variants, key=lambda v: v["reply_rate"]) if variants and any(v["sent_count"] for v in variants) else None
    return {
        "id": t.id, "name": t.name, "channel": t.channel, "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "variants": variants,
        "total_sent": sum(v["sent_count"] for v in variants),
        "winner_id": winner["id"] if winner else None,
    }


class VariantIn(BaseModel):
    label: str
    subject: Optional[str] = None
    body: str


class TestIn(BaseModel):
    name: str
    channel: str = "whatsapp"
    variants: List[VariantIn]


class TestUpdate(BaseModel):
    status: Optional[str] = None   # active | paused | done
    name: Optional[str] = None


async def _load(tid, tenant_id, db):
    from app.models.models import ABTest
    t = (await db.execute(select(ABTest).options(selectinload(ABTest.variants)).where(
        and_(ABTest.id == tid, ABTest.tenant_id == tenant_id)))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    return t


@router.get("")
@router.get("/")
async def list_tests(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import ABTest
    rows = (await db.execute(select(ABTest).options(selectinload(ABTest.variants)).where(
        ABTest.tenant_id == current_user["tenant_id"]).order_by(ABTest.created_at.desc())
    )).scalars().all()
    return [_test(t) for t in rows]


@router.post("")
@router.post("/")
async def create_test(body: TestIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import ABTest, ABVariant
    if len(body.variants) < 2:
        raise HTTPException(status_code=400, detail="A test needs at least 2 variants")
    if body.channel not in ("whatsapp", "email"):
        raise HTTPException(status_code=400, detail="channel must be whatsapp or email")
    t = ABTest(tenant_id=current_user["tenant_id"], name=body.name, channel=body.channel, status="active")
    db.add(t)
    await db.flush()
    for v in body.variants:
        db.add(ABVariant(test_id=t.id, label=v.label, subject=v.subject, body=v.body))
    await db.commit()
    t = await _load(t.id, current_user["tenant_id"], db)
    return _test(t)


@router.patch("/{tid}")
async def update_test(tid: str, body: TestUpdate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await _load(tid, current_user["tenant_id"], db)
    if body.status is not None:
        if body.status not in ("active", "paused", "done"):
            raise HTTPException(status_code=400, detail="invalid status")
        t.status = body.status
    if body.name is not None:
        t.name = body.name
    await db.commit()
    t = await _load(tid, current_user["tenant_id"], db)
    return _test(t)


@router.delete("/{tid}")
async def delete_test(tid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await _load(tid, current_user["tenant_id"], db)
    await db.delete(t)
    await db.commit()
    return {"deleted": True}
