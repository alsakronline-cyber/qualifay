"""Sequences API — build multi-step cadences and enroll leads."""
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.database import get_db
from app.api.auth import get_current_user

router = APIRouter()


class StepIn(BaseModel):
    delay_hours: int = 0
    channel: str = "auto"           # auto | whatsapp | email
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class SequenceIn(BaseModel):
    name: str
    active: bool = True
    steps: List[StepIn] = []


class EnrollIn(BaseModel):
    lead_ids: List[str]


def _seq_dict(s, counts: dict = None) -> dict:
    return {
        "id": s.id, "name": s.name, "active": s.active,
        "steps": [
            {"id": st.id, "step_order": st.step_order, "delay_hours": st.delay_hours,
             "channel": st.channel, "template_id": st.template_id, "subject": st.subject, "body": st.body}
            for st in sorted(s.steps, key=lambda x: x.step_order)
        ],
        "stats": counts or {},
    }


async def _enrollment_counts(seq_id, db) -> dict:
    from app.models.models import SequenceEnrollment
    rows = (await db.execute(
        select(SequenceEnrollment.status, func.count(SequenceEnrollment.id))
        .where(SequenceEnrollment.sequence_id == seq_id)
        .group_by(SequenceEnrollment.status)
    )).all()
    return {status: n for status, n in rows}


@router.get("")
@router.get("/")
async def list_sequences(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import Sequence
    from sqlalchemy.orm import selectinload
    rows = (await db.execute(
        select(Sequence).where(Sequence.tenant_id == current_user["tenant_id"])
        .options(selectinload(Sequence.steps)).order_by(Sequence.created_at.desc())
    )).scalars().all()
    out = []
    for s in rows:
        out.append(_seq_dict(s, await _enrollment_counts(s.id, db)))
    return out


@router.post("")
@router.post("/")
async def create_sequence(body: SequenceIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import Sequence, SequenceStep
    seq = Sequence(tenant_id=current_user["tenant_id"], name=body.name, active=body.active)
    db.add(seq)
    await db.flush()
    for i, st in enumerate(body.steps):
        db.add(SequenceStep(sequence_id=seq.id, step_order=i, delay_hours=st.delay_hours,
                            channel=st.channel, template_id=st.template_id, subject=st.subject, body=st.body))
    await db.commit()
    await db.refresh(seq, ["steps"])
    return _seq_dict(seq, {})


async def _get_seq(seq_id, tenant_id, db):
    from app.models.models import Sequence
    from sqlalchemy.orm import selectinload
    s = (await db.execute(select(Sequence).where(and_(
        Sequence.id == seq_id, Sequence.tenant_id == tenant_id
    )).options(selectinload(Sequence.steps)))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return s


@router.patch("/{seq_id}")
async def update_sequence(seq_id: str, body: SequenceIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import SequenceStep
    seq = await _get_seq(seq_id, current_user["tenant_id"], db)
    seq.name = body.name
    seq.active = body.active
    # Replace steps wholesale (simplest correct edit for a small step list).
    for st in list(seq.steps):
        await db.delete(st)
    await db.flush()
    for i, st in enumerate(body.steps):
        db.add(SequenceStep(sequence_id=seq.id, step_order=i, delay_hours=st.delay_hours,
                            channel=st.channel, template_id=st.template_id, subject=st.subject, body=st.body))
    await db.commit()
    await db.refresh(seq, ["steps"])
    return _seq_dict(seq, await _enrollment_counts(seq.id, db))


@router.delete("/{seq_id}")
async def delete_sequence(seq_id: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    seq = await _get_seq(seq_id, current_user["tenant_id"], db)
    await db.delete(seq)
    await db.commit()
    return {"deleted": True}


@router.post("/{seq_id}/enroll")
async def enroll_leads(seq_id: str, body: EnrollIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import Sequence, SequenceEnrollment
    seq = await _get_seq(seq_id, current_user["tenant_id"], db)
    if not seq.steps:
        raise HTTPException(status_code=400, detail="Sequence has no steps")

    first_delay = sorted(seq.steps, key=lambda x: x.step_order)[0].delay_hours or 0
    first_run = datetime.utcnow() + timedelta(hours=first_delay)

    existing = {e.lead_id for e in (await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == seq_id)
    )).scalars().all()}

    enrolled = 0
    for lid in body.lead_ids:
        if lid in existing:
            continue
        db.add(SequenceEnrollment(
            tenant_id=current_user["tenant_id"], sequence_id=seq_id, lead_id=lid,
            current_step=0, status="active", next_run_at=first_run,
        ))
        enrolled += 1
    await db.commit()
    return {"enrolled": enrolled}
