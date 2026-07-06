"""
Leads API — B2B lead management with BANT scoring and pool integration
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import Optional, List
from pydantic import BaseModel, Field
import re as _re
from app.core.database import get_db
from app.models.models import Lead, LeadStage, LeadStatus, LeadSource
from app.api.auth import get_current_user

router = APIRouter()


class LeadUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    city: Optional[str] = None
    governorate: Optional[str] = None
    website: Optional[str] = None
    stage: Optional[str] = None
    language: Optional[str] = None
    ai_notes: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str = ""


class PoolSearchParams(BaseModel):
    industry: Optional[str] = None
    city: Optional[str] = None
    min_score: int = 0
    limit: int = 20


def _reach_of(lead: Lead) -> str:
    """How this lead can be contacted, from what we know:
      whatsapp    — phone confirmed on WhatsApp
      phone_no_wa — has a phone but it's NOT on WhatsApp (e.g. a landline)
      email       — no usable phone, but has an email
      phone       — has a phone, WhatsApp status not checked yet
      none        — no phone and no email (needs enrichment)
    """
    has_phone = bool(lead.phone)
    has_email = bool(lead.email)
    wa = getattr(lead, "wa_reachable", None)
    if has_phone and wa is True:
        return "whatsapp"
    if has_phone and wa is False:
        return "email" if has_email else "phone_no_wa"
    if has_phone:
        return "phone"          # unchecked — assume WhatsApp-capable until verified
    if has_email:
        return "email"
    return "none"


def _lead_dict(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "tenant_id": lead.tenant_id,
        "source": lead.source.value if lead.source else None,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "wa_reachable": getattr(lead, "wa_reachable", None),
        "reach": _reach_of(lead),
        "company": lead.company,
        "industry": lead.industry,
        "company_size": lead.company_size,
        "city": lead.city,
        "governorate": lead.governorate,
        "website": lead.website,
        "linkedin_url": lead.linkedin_url,
        "bant_score": lead.bant_score,
        "bant_budget": lead.bant_budget,
        "bant_authority": lead.bant_authority,
        "bant_need": lead.bant_need,
        "bant_timeline": lead.bant_timeline,
        "bant_reason": lead.bant_reason,
        "stage": lead.stage.value if lead.stage else None,
        "status": lead.status.value if lead.status else None,
        "language": lead.language,
        "pool_contributed": lead.pool_contributed,
        "assigned_to": lead.assigned_to,
        "ai_notes": lead.ai_notes,
        "notes": (lead.raw_data or {}).get("notes") if lead.raw_data else None,
        "last_contacted_at": lead.last_contacted_at.isoformat() if getattr(lead, "last_contacted_at", None) else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }


@router.get("/stats")
async def leads_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lead counts by stage for dashboard."""
    tenant_id = current_user["tenant_id"]
    result = await db.execute(
        select(Lead.stage, func.count(Lead.id))
        .where(Lead.tenant_id == tenant_id)
        .where(Lead.status == LeadStatus.active)
        .group_by(Lead.stage)
    )
    rows = result.all()
    stage_counts = {r[0].value if r[0] else "unknown": r[1] for r in rows}

    total = sum(stage_counts.values())
    return {
        "total": total,
        "by_stage": stage_counts,
        "pending_review": stage_counts.get("pending_review", 0),
        "approved": stage_counts.get("approved", 0),
        "outreach": stage_counts.get("outreach", 0),
        "replied": stage_counts.get("replied", 0),
        "won": stage_counts.get("won", 0),
    }


@router.get("/review-queue")
async def review_queue(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Leads pending human review with BANT breakdown."""
    tenant_id = current_user["tenant_id"]

    count_result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(
                Lead.tenant_id == tenant_id,
                Lead.stage == LeadStage.pending_review,
                Lead.status == LeadStatus.active,
            )
        )
    )
    count = count_result.scalar()

    result = await db.execute(
        select(Lead)
        .where(
            and_(
                Lead.tenant_id == tenant_id,
                Lead.stage == LeadStage.pending_review,
                Lead.status == LeadStatus.active,
            )
        )
        .order_by(Lead.bant_score.desc())
        .limit(100)
    )
    leads = result.scalars().all()

    return {
        "count": count,
        "leads": [_lead_dict(l) for l in leads],
    }


@router.get("/pool/search")
async def search_pool(
    industry: Optional[str] = None,
    city: Optional[str] = None,
    min_score: int = 0,
    limit: int = Query(default=20, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the shared lead pool."""
    from app.services.lead_pool_service import lead_pool_service
    results = await lead_pool_service.search(
        db=db,
        industry=industry,
        city=city,
        min_score=min_score,
        limit=limit,
        claiming_tenant_id=current_user["tenant_id"],
    )
    return {"results": results, "count": len(results)}


@router.post("/pool/{pool_id}/claim")
async def claim_from_pool(
    pool_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim a lead from the shared pool."""
    from app.services.lead_pool_service import lead_pool_service
    result = await lead_pool_service.claim(pool_id, current_user["tenant_id"], db)
    if not result:
        raise HTTPException(status_code=400, detail="Pool entry not available or already claimed")
    return result


@router.get("", include_in_schema=False)
@router.get("/")
async def list_leads(
    stage: Optional[str] = None,
    source: Optional[str] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    # The frontend sends page/per_page; accept them as aliases so callers that use
    # those names (e.g. the pipeline board) aren't silently capped at the default.
    page: Optional[int] = Query(default=None, ge=1),
    per_page: Optional[int] = Query(default=None, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List leads with filters and pagination."""
    if per_page is not None:
        limit = per_page
    if page is not None:
        skip = (page - 1) * limit

    tenant_id = current_user["tenant_id"]
    filters = [Lead.tenant_id == tenant_id]

    if stage:
        try:
            filters.append(Lead.stage == LeadStage(stage))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")

    if source:
        try:
            filters.append(Lead.source == LeadSource(source))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid source: {source}")

    if score_min is not None:
        filters.append(Lead.bant_score >= score_min)
    if score_max is not None:
        filters.append(Lead.bant_score <= score_max)

    if status:
        try:
            filters.append(Lead.status == LeadStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if search:
        term = f"%{search}%"
        filters.append(
            or_(
                Lead.name.ilike(term),
                Lead.company.ilike(term),
                Lead.phone.ilike(term),
                Lead.email.ilike(term),
            )
        )

    total_result = await db.execute(
        select(func.count(Lead.id)).where(and_(*filters))
    )
    total = total_result.scalar()

    result = await db.execute(
        select(Lead)
        .where(and_(*filters))
        .order_by(Lead.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    leads = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "leads": [_lead_dict(l) for l in leads],
    }


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single lead by ID."""
    result = await db.execute(
        select(Lead).where(
            and_(Lead.id == lead_id, Lead.tenant_id == current_user["tenant_id"])
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_dict(lead)


@router.post("/{lead_id}/approve")
async def approve_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a lead and queue outreach."""
    result = await db.execute(
        select(Lead).where(
            and_(Lead.id == lead_id, Lead.tenant_id == current_user["tenant_id"])
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.stage = LeadStage.approved
    await db.commit()

    from app.workers.outreach_tasks import process_approved_lead
    task = process_approved_lead.apply_async(args=[lead_id], queue="outreach")

    return {"approved": True, "lead_id": lead_id, "task_id": task.id}


class BulkApproveRequest(BaseModel):
    ids: List[str]


@router.post("/bulk-approve")
async def bulk_approve_leads(
    body: BulkApproveRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve many leads at once and queue outreach for each. The warmup daily caps
    pace the actual sends (WhatsApp or email), so over-cap leads retry the next day."""
    from app.workers.outreach_tasks import process_approved_lead

    tenant_id = current_user["tenant_id"]
    if not body.ids:
        return {"approved": 0, "queued": 0}

    result = await db.execute(
        select(Lead).where(and_(Lead.id.in_(body.ids), Lead.tenant_id == tenant_id))
    )
    leads = result.scalars().all()
    for lead in leads:
        lead.stage = LeadStage.approved
    await db.commit()

    for lead in leads:
        process_approved_lead.apply_async(args=[lead.id], queue="outreach")

    return {"approved": len(leads), "queued": len(leads)}


class CheckReachabilityRequest(BaseModel):
    ids: Optional[List[str]] = None   # omit to check all not-yet-checked phone leads


@router.post("/check-reachability")
async def check_reachability(
    body: CheckReachabilityRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify which leads' phone numbers are actually on WhatsApp, so you know who's
    reachable there (vs a landline) before approving. One Evolution call per ~50 numbers."""
    from app.services.evolution_service import evolution_service
    from app.models.models import WaInstance

    tenant_id = current_user["tenant_id"]
    inst = (await db.execute(
        select(WaInstance).where(
            WaInstance.tenant_id == tenant_id,
            WaInstance.status.in_(["open", "connected"]),
        ).limit(1)
    )).scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=400, detail="No connected WhatsApp instance to check numbers with")

    filters = [Lead.tenant_id == tenant_id, Lead.phone.isnot(None), Lead.phone != ""]
    if body.ids:
        filters.append(Lead.id.in_(body.ids))
    else:
        filters.append(Lead.wa_reachable.is_(None))
    leads = (await db.execute(select(Lead).where(and_(*filters)).limit(500))).scalars().all()
    if not leads:
        return {"checked": 0, "reachable": 0, "not_reachable": 0}

    phones = list({l.phone for l in leads if l.phone})
    result_map: dict = {}
    for i in range(0, len(phones), 50):
        chunk = phones[i:i + 50]
        try:
            result_map.update(await evolution_service.check_numbers(inst.instance_name, chunk))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"WhatsApp number check failed: {e}")

    reachable = not_reachable = 0
    for lead in leads:
        val = result_map.get(lead.phone)
        if val is None:
            continue
        lead.wa_reachable = bool(val)
        if val:
            reachable += 1
        else:
            not_reachable += 1
    await db.commit()
    return {"checked": reachable + not_reachable, "reachable": reachable, "not_reachable": not_reachable}


@router.post("/{lead_id}/reject")
async def reject_lead(
    lead_id: str,
    body: RejectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a lead with a reason."""
    result = await db.execute(
        select(Lead).where(
            and_(Lead.id == lead_id, Lead.tenant_id == current_user["tenant_id"])
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.stage = LeadStage.archived
    if body.reason:
        lead.ai_notes = (lead.ai_notes or "") + f"\n[Rejected by user: {body.reason}]"
    await db.commit()
    return {"rejected": True, "lead_id": lead_id}


@router.post("/{lead_id}/take-manually")
async def take_manually(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign lead to current user for manual handling."""
    result = await db.execute(
        select(Lead).where(
            and_(Lead.id == lead_id, Lead.tenant_id == current_user["tenant_id"])
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.stage = LeadStage.manual
    lead.assigned_to = current_user["user_id"]
    await db.commit()
    return {"stage": "manual", "assigned_to": current_user["user_id"], "lead_id": lead_id}


def _normalize_phone(phone: str) -> str:
    """Normalize Egyptian phone numbers to E.164 (+201XXXXXXXXX). Delegates to shared lib."""
    from app.lib.phone import normalize_egyptian_phone
    return normalize_egyptian_phone(phone) or phone


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    body: LeadUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partial update of lead fields with phone normalization and activity log."""
    from datetime import datetime, timezone
    result = await db.execute(
        select(Lead).where(
            and_(Lead.id == lead_id, Lead.tenant_id == current_user["tenant_id"])
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = body.model_dump(exclude_none=True)
    changed_fields = []

    for field, value in update_data.items():
        if field == "stage":
            try:
                new_val = LeadStage(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid stage: {value}")
            if getattr(lead, field) != new_val:
                changed_fields.append(field)
                setattr(lead, field, new_val)
        elif field == "bant_score":
            if not (0 <= value <= 100):
                raise HTTPException(status_code=400, detail="bant_score must be 0-100")
            if getattr(lead, field) != value:
                changed_fields.append(field)
                setattr(lead, field, value)
        elif field == "phone" and value:
            normalized = _normalize_phone(value)
            if getattr(lead, field) != normalized:
                changed_fields.append(field)
                setattr(lead, field, normalized)
        elif field == "notes":
            raw = lead.raw_data or {}
            raw["notes"] = value
            lead.raw_data = raw
            changed_fields.append("notes")
        else:
            if getattr(lead, field, None) != value:
                changed_fields.append(field)
                setattr(lead, field, value)

    lead.updated_at = datetime.utcnow()  # naive UTC to match the column type

    # Log activity if fields changed
    if changed_fields:
        try:
            from app.services.activity_service import log_activity
            from app.models.models import ActivityType
            await log_activity(
                db=db,
                tenant_id=str(lead.tenant_id),
                activity_type=ActivityType.lead_updated,
                summary=f"Fields updated: {', '.join(changed_fields)}",
                entity_type="lead",
                entity_id=str(lead.id),
                user_id=current_user.get("user_id"),
                extra_data={"changed_fields": changed_fields},
            )
        except Exception as e:
            logger.warning(f"Could not log lead_updated activity: {e}")

    await db.commit()
    await db.refresh(lead)
    return _lead_dict(lead)


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a lead by setting status=invalid."""
    result = await db.execute(
        select(Lead).where(
            and_(Lead.id == lead_id, Lead.tenant_id == current_user["tenant_id"])
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = LeadStatus.invalid
    await db.commit()
    return {"deleted": True, "lead_id": lead_id}
