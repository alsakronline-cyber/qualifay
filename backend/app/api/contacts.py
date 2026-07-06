"""Contacts API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional
from app.core.database import get_db
from app.models.models import Contact
from app.workers.tasks import update_contact_ai_summary, score_lead_task
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    tags: Optional[list] = None
    notes: Optional[str] = None
    custom_fields: Optional[dict] = None
    status: Optional[str] = None


@router.get("", include_in_schema=False)
@router.get("/")
async def list_contacts(
    search: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Contact).order_by(Contact.updated_at.desc())

    if search:
        query = query.where(
            or_(
                Contact.name.ilike(f"%{search}%"),
                Contact.phone.ilike(f"%{search}%"),
                Contact.email.ilike(f"%{search}%"),
                Contact.company.ilike(f"%{search}%"),
            )
        )
    if status:
        query = query.where(Contact.status == status)

    total = await db.execute(select(func.count()).select_from(query.subquery()))
    total_count = total.scalar()

    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    contacts = result.scalars().all()

    return {
        "total": total_count,
        "page": page,
        "limit": limit,
        "data": [_contact_dict(c) for c in contacts],
    }


@router.get("/{contact_id}")
async def get_contact(contact_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_dict(contact)


@router.patch("/{contact_id}")
async def update_contact(contact_id: str, data: ContactUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in data.dict(exclude_none=True).items():
        setattr(contact, field, value)

    await db.commit()
    return _contact_dict(contact)


@router.post("/{contact_id}/refresh-ai")
async def refresh_ai_summary(contact_id: str):
    """Trigger background AI summary regeneration."""
    update_contact_ai_summary.apply_async(kwargs={"contact_id": contact_id}, queue="ai")
    score_lead_task.apply_async(kwargs={"contact_id": contact_id}, queue="ai")
    return {"status": "queued"}


def _contact_dict(c: Contact) -> dict:
    return {
        "id": c.id,
        "phone": c.phone,
        "wa_jid": c.wa_jid,
        "name": c.name,
        "email": c.email,
        "company": c.company,
        "avatar_url": c.avatar_url,
        "status": c.status.value if c.status else "new",
        "tags": c.tags or [],
        "notes": c.notes,
        "ai_summary": c.ai_summary,
        "lead_score": c.lead_score or 0,
        "sentiment_score": c.sentiment_score,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
