"""
Notifications API — List and mark notifications as read
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.models.models import Notification
from app.api.auth import get_current_user

router = APIRouter()


def _notif_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "tenant_id": n.tenant_id,
        "user_id": n.user_id,
        "type": n.type.value if n.type else None,
        "title": n.title,
        "message": n.message,
        "data": n.data,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/")
async def list_notifications(
    unread_only: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List notifications — unread first, then by date desc."""
    tenant_id = current_user["tenant_id"]
    filters = [Notification.tenant_id == tenant_id]

    if unread_only:
        filters.append(Notification.read_at.is_(None))

    result = await db.execute(
        select(Notification)
        .where(and_(*filters))
        .order_by(
            Notification.read_at.is_(None).desc(),
            Notification.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
    )
    notifications = result.scalars().all()

    return [_notif_dict(n) for n in notifications]


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.tenant_id == current_user["tenant_id"],
            )
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notif.read_at:
        notif.read_at = datetime.utcnow()
        await db.commit()

    return {"read": True, "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read for the current tenant."""
    tenant_id = current_user["tenant_id"]
    now = datetime.utcnow()

    await db.execute(
        update(Notification)
        .where(
            and_(
                Notification.tenant_id == tenant_id,
                Notification.read_at.is_(None),
            )
        )
        .values(read_at=now)
    )
    await db.commit()

    return {"read_all": True, "timestamp": now.isoformat()}
