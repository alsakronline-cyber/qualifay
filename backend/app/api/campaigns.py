"""Campaigns — the orchestration layer. A campaign binds an AUDIENCE (a saved filter
over leads) to a SEQUENCE (the multi-step send engine). Launching enrolls the matching
leads into the sequence; the existing sequence beat task does the actual sending, so
warmup caps, STOP handling and reply-stops all apply for free. Stats are derived live
from enrollments, so a lead's state (replied, stopped) is a single source of truth."""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import get_current_user

router = APIRouter()


# ── Audience filter → lead query ────────────────────────────────────────────────
def audience_conditions(af: Optional[Dict[str, Any]], tenant_id: str) -> list:
    """Translate a stored audience_filter dict into SQLAlchemy conditions. Mirrors the
    Leads page filters so 'who's in this campaign' matches what the user sees there."""
    from app.models.models import Lead, LeadStage, LeadSource, LeadStatus
    conds = [Lead.tenant_id == tenant_id]
    # Only ever target contactable, opted-in leads.
    conds.append(Lead.status == LeadStatus.active)
    af = af or {}
    if af.get("stage"):
        try:
            conds.append(Lead.stage == LeadStage(af["stage"]))
        except ValueError:
            pass
    if af.get("source"):
        try:
            conds.append(Lead.source == LeadSource(af["source"]))
        except ValueError:
            pass
    if af.get("min_score") not in (None, ""):
        try:
            conds.append(Lead.bant_score >= int(af["min_score"]))
        except (ValueError, TypeError):
            pass  # ignore a non-numeric filter value rather than 500 the whole campaign
    if af.get("city"):
        conds.append(Lead.city.ilike(f"%{af['city']}%"))
    if af.get("industry"):
        conds.append(Lead.industry.ilike(f"%{af['industry']}%"))
    if af.get("search"):
        s = f"%{af['search']}%"
        conds.append(Lead.company.ilike(s) | Lead.name.ilike(s))
    return conds


async def _stats(campaign_id: str, db: AsyncSession) -> dict:
    """Live counts derived from enrollments — the campaign's real numbers."""
    from app.models.models import SequenceEnrollment as E
    rows = (await db.execute(
        select(E.status, func.count(E.id)).where(E.campaign_id == campaign_id).group_by(E.status)
    )).all()
    by = {status: n for status, n in rows}
    total = sum(by.values())
    replied = by.get("replied", 0)
    return {
        "enrolled": total,
        "active": by.get("active", 0),
        "paused": by.get("paused", 0),
        "completed": by.get("completed", 0),
        "stopped": by.get("stopped", 0),
        "replied": replied,
        "reply_rate": round(replied / total * 100, 1) if total else 0.0,
    }


def _c(c, stats: dict) -> dict:
    return {
        "id": c.id, "name": c.name, "status": c.status, "channel": c.channel,
        "sequence_id": c.sequence_id, "audience_filter": c.audience_filter or {},
        "instance_ids": c.instance_ids or [], "auto_enroll": bool(c.auto_enroll),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "stats": stats,
    }


class CampaignIn(BaseModel):
    name: str
    sequence_id: Optional[str] = None
    channel: str = "whatsapp"
    audience_filter: Dict[str, Any] = {}
    instance_ids: List[str] = []
    auto_enroll: bool = False


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    sequence_id: Optional[str] = None
    audience_filter: Optional[Dict[str, Any]] = None
    instance_ids: Optional[List[str]] = None
    auto_enroll: Optional[bool] = None


async def _get(cid: str, tenant_id: str, db: AsyncSession):
    from app.models.models import Campaign
    c = (await db.execute(select(Campaign).where(and_(
        Campaign.id == cid, Campaign.tenant_id == tenant_id)))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


@router.get("")
@router.get("/")
async def list_campaigns(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import Campaign
    rows = (await db.execute(select(Campaign).where(
        Campaign.tenant_id == current_user["tenant_id"]).order_by(Campaign.created_at.desc())
    )).scalars().all()
    return {"items": [_c(c, await _stats(c.id, db)) for c in rows]}


@router.get("/{cid}")
async def get_campaign(cid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _get(cid, current_user["tenant_id"], db)
    return _c(c, await _stats(c.id, db))


@router.get("/{cid}/audience-preview")
async def audience_preview(cid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """How many leads the current filter matches — shown before launch."""
    from app.models.models import Lead
    c = await _get(cid, current_user["tenant_id"], db)
    n = (await db.execute(select(func.count(Lead.id)).where(
        and_(*audience_conditions(c.audience_filter, current_user["tenant_id"]))
    ))).scalar() or 0
    return {"matching_leads": n}


@router.post("")
@router.post("/")
async def create_campaign(body: CampaignIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import Campaign
    c = Campaign(
        tenant_id=current_user["tenant_id"], name=body.name, channel=body.channel,
        sequence_id=body.sequence_id, audience_filter=body.audience_filter,
        instance_ids=body.instance_ids, auto_enroll=body.auto_enroll, status="draft",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _c(c, await _stats(c.id, db))


@router.patch("/{cid}")
async def update_campaign(cid: str, body: CampaignUpdate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _get(cid, current_user["tenant_id"], db)
    for field in ("name", "sequence_id", "audience_filter", "instance_ids", "auto_enroll"):
        val = getattr(body, field)
        if val is not None:
            setattr(c, field, val)
    await db.commit()
    return _c(c, await _stats(c.id, db))


@router.post("/{cid}/launch")
async def launch_campaign(cid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Enroll every matching lead into the campaign's sequence and start running."""
    from app.models.models import Campaign, Sequence, SequenceEnrollment
    c = await _get(cid, current_user["tenant_id"], db)
    if not c.sequence_id:
        raise HTTPException(status_code=400, detail="Campaign has no sequence")
    seq = (await db.execute(select(Sequence).options(selectinload(Sequence.steps)).where(
        Sequence.id == c.sequence_id))).scalar_one_or_none()
    if not seq or not seq.steps:
        raise HTTPException(status_code=400, detail="Sequence missing or has no steps")

    enrolled = await _enroll_audience(c, seq, current_user["tenant_id"], db)
    c.status = "running"
    await db.commit()
    return {"launched": True, "enrolled": enrolled, "stats": await _stats(c.id, db)}


async def _enroll_audience(campaign, seq, tenant_id: str, db: AsyncSession) -> int:
    """Enroll matching leads not already enrolled in this campaign's sequence.
    Shared by launch and the auto-enroll sync task."""
    from app.models.models import Lead, SequenceEnrollment
    first_delay = sorted(seq.steps, key=lambda x: x.step_order)[0].delay_hours or 0
    first_run = datetime.utcnow() + timedelta(hours=first_delay)

    already = {e.lead_id for e in (await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == seq.id)
    )).scalars().all()}

    leads = (await db.execute(select(Lead.id).where(
        and_(*audience_conditions(campaign.audience_filter, tenant_id))
    ))).scalars().all()

    enrolled = 0
    for lid in leads:
        if lid in already:
            continue
        db.add(SequenceEnrollment(
            tenant_id=tenant_id, sequence_id=seq.id, lead_id=lid, campaign_id=campaign.id,
            current_step=0, status="active", next_run_at=first_run,
        ))
        enrolled += 1
    return enrolled


async def _set_enrollment_status(cid: str, frm: str, to: str, db: AsyncSession) -> int:
    from app.models.models import SequenceEnrollment as E
    rows = (await db.execute(select(E).where(and_(
        E.campaign_id == cid, E.status == frm)))).scalars().all()
    for e in rows:
        e.status = to
    return len(rows)


@router.post("/{cid}/pause")
async def pause_campaign(cid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _get(cid, current_user["tenant_id"], db)
    n = await _set_enrollment_status(cid, "active", "paused", db)  # beat skips non-active
    c.status = "paused"
    await db.commit()
    return {"paused": True, "halted": n}


@router.post("/{cid}/resume")
async def resume_campaign(cid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await _get(cid, current_user["tenant_id"], db)
    n = await _set_enrollment_status(cid, "paused", "active", db)
    c.status = "running"
    await db.commit()
    return {"resumed": True, "reactivated": n}


@router.delete("/{cid}")
async def delete_campaign(cid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import SequenceEnrollment as E
    c = await _get(cid, current_user["tenant_id"], db)
    # Stop this campaign's active/paused enrollments so nothing keeps sending.
    for st in ("active", "paused"):
        await _set_enrollment_status(cid, st, "stopped", db)
    await db.delete(c)
    await db.commit()
    return {"deleted": True}
