"""
Dashboard API — Stats, activity feed, notifications
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime, date

from app.core.database import get_db
from app.models.models import (
    Lead, WaInstance, Campaign, Notification, Message,
    Conversation, LeadStage, LeadStatus, MessageDirection, NotificationType
)
from app.api.auth import get_current_user

router = APIRouter()


@router.get("/analytics")
async def get_analytics(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Funnel + per-channel reply rates + sequence stats — the feedback loop."""
    tenant_id = current_user["tenant_id"]

    # ── Funnel: active leads by stage ──
    stage_rows = (await db.execute(
        select(Lead.stage, func.count(Lead.id))
        .where(and_(Lead.tenant_id == tenant_id, Lead.status == LeadStatus.active))
        .group_by(Lead.stage)
    )).all()
    by_stage = {(s.value if s else "unknown"): n for s, n in stage_rows}

    def stage_sum(*stages):
        return sum(by_stage.get(s, 0) for s in stages)

    funnel = {
        "total": sum(by_stage.values()),
        "new": stage_sum("new", "qualifying", "pending_review"),
        "approved": stage_sum("approved"),
        "contacted": stage_sum("outreach", "replied", "meeting", "proposal", "negotiation", "won", "lost"),
        "replied": stage_sum("replied", "meeting", "proposal", "negotiation", "won"),
        "booked": stage_sum("meeting", "proposal", "negotiation", "won"),
        "won": stage_sum("won"),
    }

    # ── Per-channel: conversations + reply rate ──
    channels = {}
    for ch in ("whatsapp", "email"):
        convs = (await db.execute(
            select(func.count(Conversation.id)).where(and_(
                Conversation.tenant_id == tenant_id, Conversation.channel == ch
            ))
        )).scalar() or 0
        replied_convs = (await db.execute(
            select(func.count(func.distinct(Message.conversation_id)))
            .select_from(Message).join(Conversation, Message.conversation_id == Conversation.id)
            .where(and_(
                Conversation.tenant_id == tenant_id,
                Conversation.channel == ch,
                Message.direction == MessageDirection.inbound,
            ))
        )).scalar() or 0
        channels[ch] = {
            "conversations": convs,
            "replied": replied_convs,
            "reply_rate": round(replied_convs / convs * 100, 1) if convs else 0.0,
        }

    # ── Sequences by enrollment status ──
    seq_stats = {}
    try:
        from app.models.models import SequenceEnrollment
        rows = (await db.execute(
            select(SequenceEnrollment.status, func.count(SequenceEnrollment.id))
            .where(SequenceEnrollment.tenant_id == tenant_id)
            .group_by(SequenceEnrollment.status)
        )).all()
        seq_stats = {s: n for s, n in rows}
    except Exception:
        seq_stats = {}

    # ── Reachability ──
    reach_rows = (await db.execute(
        select(Lead.wa_reachable, func.count(Lead.id))
        .where(Lead.tenant_id == tenant_id).group_by(Lead.wa_reachable)
    )).all()
    reach = {"on_whatsapp": 0, "not_on_whatsapp": 0, "unchecked": 0}
    for val, n in reach_rows:
        reach["on_whatsapp" if val is True else "not_on_whatsapp" if val is False else "unchecked"] += n

    return {"funnel": funnel, "channels": channels, "sequences": seq_stats, "reachability": reach}



@router.get("/stats")
async def get_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard KPIs: total leads, pending review, WA sent today, active campaigns, pool contributions."""
    tenant_id = current_user["tenant_id"]

    # Total active leads
    total_leads = (
        await db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.tenant_id == tenant_id, Lead.status == LeadStatus.active)
            )
        )
    ).scalar() or 0

    # Pending review
    pending_review = (
        await db.execute(
            select(func.count(Lead.id)).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.stage == LeadStage.pending_review,
                    Lead.status == LeadStatus.active,
                )
            )
        )
    ).scalar() or 0

    # WA messages sent today (sum across all instances)
    sent_today_wa = (
        await db.execute(
            select(func.sum(WaInstance.sent_today_wa)).where(
                WaInstance.tenant_id == tenant_id
            )
        )
    ).scalar() or 0

    # Active campaigns
    active_campaigns = (
        await db.execute(
            select(func.count(Campaign.id)).where(
                and_(Campaign.tenant_id == tenant_id, Campaign.status == "running")
            )
        )
    ).scalar() or 0

    # Pool contributions (leads contributed to shared pool)
    pool_contributions = (
        await db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.tenant_id == tenant_id, Lead.pool_contributed == True)
            )
        )
    ).scalar() or 0

    # Won leads this month
    today = date.today()
    first_of_month = datetime(today.year, today.month, 1)
    won_this_month = (
        await db.execute(
            select(func.count(Lead.id)).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.stage == LeadStage.won,
                    Lead.updated_at >= first_of_month,
                )
            )
        )
    ).scalar() or 0

    # Open conversations
    open_conversations = (
        await db.execute(
            select(func.count(Conversation.id)).where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.status.in_(["open", "ai_handling"]),
                )
            )
        )
    ).scalar() or 0

    # Unread notifications count
    unread_notifications = (
        await db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.tenant_id == tenant_id,
                    Notification.read_at.is_(None),
                )
            )
        )
    ).scalar() or 0

    return {
        "total_leads": total_leads,
        "pending_review": pending_review,
        "sent_today_wa": int(sent_today_wa),
        "active_campaigns": active_campaigns,
        "pool_contributions": pool_contributions,
        "won_this_month": won_this_month,
        "open_conversations": open_conversations,
        "unread_notifications": unread_notifications,
    }


@router.get("/recent-activity")
async def get_recent_activity(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent leads and messages for activity feed."""
    tenant_id = current_user["tenant_id"]

    # Recent leads (last 10)
    recent_leads_result = await db.execute(
        select(Lead)
        .where(and_(Lead.tenant_id == tenant_id, Lead.status == LeadStatus.active))
        .order_by(Lead.created_at.desc())
        .limit(10)
    )
    recent_leads = recent_leads_result.scalars().all()

    # Recent outbound messages (last 10)
    recent_msgs_result = await db.execute(
        select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            and_(
                Conversation.tenant_id == tenant_id,
                Message.direction == MessageDirection.outbound,
            )
        )
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    recent_msgs = recent_msgs_result.all()

    return {
        "recent_leads": [
            {
                "id": l.id,
                "company": l.company,
                "name": l.name,
                "bant_score": l.bant_score,
                "stage": l.stage.value if l.stage else None,
                "source": l.source.value if l.source else None,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in recent_leads
        ],
        "recent_messages": [
            {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "contact_name": conv.contact_name,
                "content": (msg.content or "")[:100],
                "is_ai_generated": msg.is_ai_generated,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg, conv in recent_msgs
        ],
    }


@router.get("/notifications")
async def get_notifications(
    unread: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List notifications — unread first, max 50. `unread=true` returns only unread."""
    tenant_id = current_user["tenant_id"]

    conds = [Notification.tenant_id == tenant_id]
    if unread:
        conds.append(Notification.read_at.is_(None))
    result = await db.execute(
        select(Notification)
        .where(and_(*conds))
        .order_by(
            Notification.read_at.is_(None).desc(),
            Notification.created_at.desc(),
        )
        .limit(50)
    )
    notifications = result.scalars().all()

    return [
        {
            "id": n.id,
            "type": n.type.value if n.type else None,
            "title": n.title,
            "message": n.message,
            "data": n.data,
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    from fastapi import HTTPException

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

    notif.read_at = datetime.utcnow()
    await db.commit()
    return {"read": True, "notification_id": notification_id}
