"""
Activity Log Service — P5
Logs significant system events per tenant for audit trail and feed.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

logger = logging.getLogger(__name__)


async def log_activity(
    db: AsyncSession,
    tenant_id: str,
    activity_type,  # ActivityType enum value
    summary: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_data: Optional[dict] = None,
):
    """
    Create an ActivityLog entry and add to session.
    Caller is responsible for committing.
    """
    from app.models.models import ActivityLog

    entry = ActivityLog(
        tenant_id=tenant_id,
        user_id=user_id,
        activity_type=activity_type,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        extra_data=extra_data,
    )
    db.add(entry)
    return entry
