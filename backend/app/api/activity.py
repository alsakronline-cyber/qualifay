"""
Activity Log API — P5
GET /api/v1/activity — query activity logs per tenant
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.models.models import ActivityLog
from app.api.auth import get_current_user

router = APIRouter()


def _activity_dict(entry: ActivityLog) -> dict:
    return {
        "id": str(entry.id),
        "tenant_id": str(entry.tenant_id),
        "user_id": str(entry.user_id) if entry.user_id else None,
        "activity_type": entry.activity_type.value if entry.activity_type else None,
        "entity_type": entry.entity_type,
        "entity_id": str(entry.entity_id) if entry.entity_id else None,
        "summary": entry.summary,
        "metadata": entry.extra_data,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("/")
async def list_activity(
    entity_id: Optional[str] = Query(default=None),
    entity_type: Optional[str] = Query(default=None),
    activity_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return activity logs for the current tenant, newest first."""
    tenant_id = current_user["tenant_id"]

    filters = [ActivityLog.tenant_id == tenant_id]

    if entity_id:
        filters.append(ActivityLog.entity_id == entity_id)

    if entity_type:
        filters.append(ActivityLog.entity_type == entity_type)

    if activity_type:
        from app.models.models import ActivityType
        try:
            filters.append(ActivityLog.activity_type == ActivityType(activity_type))
        except ValueError:
            pass  # ignore invalid activity_type filter

    result = await db.execute(
        select(ActivityLog)
        .where(*filters)
        .order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    entries = result.scalars().all()

    return [_activity_dict(e) for e in entries]
