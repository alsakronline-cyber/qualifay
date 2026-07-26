"""Scrape API — start, list, inspect, pause, cancel scrape jobs"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import ScrapeJob, LeadSource
from app.api.auth import get_current_user

router = APIRouter()


# ──────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────

class StartScrapeRequest(BaseModel):
    source: LeadSource
    # Flat fields (from UI) — automatically packed into config
    query: Optional[str] = None
    keyword: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    max_results: Optional[int] = Field(None, ge=1, le=500)
    session_cookie: Optional[str] = None  # for LinkedIn (li_at) / Facebook (c_user; xs)
    # Or pass config dict directly
    config: dict = {}

    def build_config(self) -> dict:
        cfg = dict(self.config)
        if self.query:          cfg.setdefault("query", self.query)
        if self.keyword:        cfg.setdefault("query", self.keyword)
        if self.location:       cfg.setdefault("location", self.location)
        if self.industry:       cfg.setdefault("industry", self.industry)
        if self.max_results:    cfg.setdefault("max_results", self.max_results)
        if self.session_cookie: cfg.setdefault("session_cookie", self.session_cookie)
        return cfg


class ScrapeJobResponse(BaseModel):
    id: str
    tenant_id: str
    source: str
    config: dict
    status: str
    leads_found: int
    leads_qualified: int
    error_message: Optional[str]
    paused_until: Optional[datetime]
    celery_task_id: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


def _job_dict(job: ScrapeJob) -> dict:
    return {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "source": job.source.value if job.source else None,
        "config": job.config or {},
        "status": job.status,
        "leads_found": job.leads_found or 0,
        "leads_qualified": job.leads_qualified or 0,
        "error_message": job.error_message,
        "paused_until": job.paused_until.isoformat() if job.paused_until else None,
        "celery_task_id": job.celery_task_id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _require_job(job: Optional[ScrapeJob], job_id: str, tenant_id: str) -> ScrapeJob:
    if not job:
        raise HTTPException(status_code=404, detail=f"ScrapeJob {job_id} not found")
    if job.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return job


# ──────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────

@router.post("/start", summary="Start a new scrape job")
async def start_scrape_job(
    body: StartScrapeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a ScrapeJob and immediately queue it for async execution.

    Returns the new job record. Use GET /scrape/jobs/{id} to poll progress.
    """
    # Validate source has a matching scraper
    valid_sources = {
        LeadSource.google_maps, LeadSource.web_scrape, LeadSource.apollo,
        LeadSource.linkedin, LeadSource.facebook, LeadSource.tender,
    }
    # Allow additional internal source names via config
    # (directories, enrichment, competitor_ads use config["source_type"])

    job = ScrapeJob(
        tenant_id=current_user['tenant_id'],
        source=body.source,
        config=body.build_config(),
        status="pending",
        leads_found=0,
        leads_qualified=0,
    )
    db.add(job)
    await db.flush()  # Get the ID

    # Queue the Celery task
    try:
        from app.workers.scrape_tasks import run_scrape_job
        celery_result = run_scrape_job.delay(job.id)
        job.celery_task_id = celery_result.id
    except Exception as e:
        job.status = "error"
        job.error_message = f"Failed to queue: {e}"

    await db.commit()
    await db.refresh(job)
    return _job_dict(job)


@router.get("/jobs", summary="List all scrape jobs for this tenant")
async def list_scrape_jobs(
    status: Optional[str] = Query(None, description="Filter by status: pending,running,paused,done,error,cancelled"),
    source: Optional[str] = Query(None, description="Filter by source enum value"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List scrape jobs for the current tenant, newest first."""
    q = select(ScrapeJob).where(ScrapeJob.tenant_id == current_user['tenant_id'])

    if status:
        q = q.where(ScrapeJob.status == status)
    if source:
        try:
            source_enum = LeadSource(source)
            q = q.where(ScrapeJob.source == source_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid source: {source}")

    q = q.order_by(ScrapeJob.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    jobs = result.scalars().all()

    # Total count
    count_q = select(func.count(ScrapeJob.id)).where(
        ScrapeJob.tenant_id == current_user['tenant_id']
    )
    if status:
        count_q = count_q.where(ScrapeJob.status == status)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    return {
        "items": [_job_dict(j) for j in jobs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/jobs/{job_id}", summary="Get scrape job status and progress")
async def get_scrape_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get detailed status and progress for a specific scrape job."""
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    job = _require_job(job, job_id, current_user['tenant_id'])

    data = _job_dict(job)

    # If running, try to get live Celery task status
    if job.status == "running" and job.celery_task_id:
        try:
            from celery.result import AsyncResult
            from app.workers.celery_app import celery_app
            celery_result = AsyncResult(job.celery_task_id, app=celery_app)
            data["celery_state"] = celery_result.state
        except Exception:
            pass

    return data


@router.post("/jobs/{job_id}/pause", summary="Pause a running scrape job")
async def pause_scrape_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Pause a running or pending scrape job.
    The job can be resumed by calling /start again with the same config,
    or it will auto-resume if it was paused due to rate limiting.
    """
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    job = _require_job(job, job_id, current_user['tenant_id'])

    if job.status not in ("running", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause job with status '{job.status}'. Only running/pending jobs can be paused."
        )

    # Revoke Celery task if running
    if job.celery_task_id:
        try:
            from celery.result import AsyncResult
            from app.workers.celery_app import celery_app
            AsyncResult(job.celery_task_id, app=celery_app).revoke(terminate=False)
        except Exception as e:
            pass  # Best effort

    job.status = "paused"
    await db.commit()
    return _job_dict(job)


@router.post("/jobs/{job_id}/cancel", summary="Cancel a scrape job")
async def cancel_scrape_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Cancel a scrape job regardless of current status.
    Cancelled jobs cannot be restarted — create a new job instead.
    """
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    job = _require_job(job, job_id, current_user['tenant_id'])

    if job.status == "done":
        raise HTTPException(status_code=400, detail="Job already completed")
    if job.status == "cancelled":
        raise HTTPException(status_code=400, detail="Job already cancelled")

    # Revoke Celery task
    if job.celery_task_id:
        try:
            from celery.result import AsyncResult
            from app.workers.celery_app import celery_app
            AsyncResult(job.celery_task_id, app=celery_app).revoke(terminate=True)
        except Exception:
            pass

    job.status = "cancelled"
    job.completed_at = datetime.utcnow()
    await db.commit()
    return _job_dict(job)


@router.post("/jobs/{job_id}/resume", summary="Resume a paused scrape job")
async def resume_scrape_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Resume a manually-paused or block-paused scrape job."""
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    job = _require_job(job, job_id, current_user['tenant_id'])

    if job.status != "paused":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not paused (current status: {job.status})"
        )

    # Clear pause window and re-queue
    job.status = "pending"
    job.paused_until = None
    job.error_message = None
    await db.flush()

    try:
        from app.workers.scrape_tasks import run_scrape_job
        celery_result = run_scrape_job.delay(job.id)
        job.celery_task_id = celery_result.id
    except Exception as e:
        job.status = "error"
        job.error_message = f"Failed to re-queue: {e}"

    await db.commit()
    return _job_dict(job)


# ──────────────────────────────────────────────────────────
# Daily schedules (automatic recurring search)
# ──────────────────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    source: LeadSource
    query: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    max_results: int = Field(50, ge=1, le=500)
    hour_cairo: int = Field(9, ge=0, le=23)
    monthly_cap: int = Field(1000, ge=1, le=100000)

    def build_config(self) -> dict:
        cfg = {}
        if self.query:    cfg["query"] = self.query
        if self.location: cfg["location"] = self.location
        if self.industry: cfg["industry"] = self.industry
        cfg["max_results"] = self.max_results
        return cfg


def _sched_dict(s) -> dict:
    return {
        "id": s.id,
        "source": s.source.value if s.source else None,
        "config": s.config or {},
        "hour_cairo": s.hour_cairo,
        "enabled": s.enabled,
        "monthly_cap": s.monthly_cap,
        "monthly_count": s.monthly_count or 0,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("/schedule", summary="Create a daily automatic search")
async def create_schedule(
    body: ScheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.models import ScrapeSchedule

    # Cap schedules per tenant so the hourly beat task stays bounded.
    existing = await db.execute(
        select(func.count()).select_from(ScrapeSchedule)
        .where(ScrapeSchedule.tenant_id == current_user["tenant_id"])
    )
    if (existing.scalar() or 0) >= 20:
        raise HTTPException(status_code=400, detail="Schedule limit reached (max 20 per account)")

    sched = ScrapeSchedule(
        tenant_id=current_user["tenant_id"],
        source=body.source,
        config=body.build_config(),
        hour_cairo=body.hour_cairo,
        monthly_cap=body.monthly_cap,
        enabled=True,
        monthly_count=0,
    )
    db.add(sched)
    await db.commit()
    await db.refresh(sched)
    return _sched_dict(sched)


@router.get("/schedules", summary="List daily automatic searches")
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.models import ScrapeSchedule
    res = await db.execute(
        select(ScrapeSchedule).where(ScrapeSchedule.tenant_id == current_user["tenant_id"])
        .order_by(ScrapeSchedule.created_at.desc())
    )
    return [_sched_dict(s) for s in res.scalars().all()]


@router.patch("/schedule/{schedule_id}", summary="Enable/disable a schedule")
async def toggle_schedule(
    schedule_id: str,
    enabled: bool,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.models import ScrapeSchedule
    res = await db.execute(
        select(ScrapeSchedule).where(
            ScrapeSchedule.id == schedule_id,
            ScrapeSchedule.tenant_id == current_user["tenant_id"],
        )
    )
    sched = res.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    sched.enabled = enabled
    await db.commit()
    return _sched_dict(sched)


@router.delete("/schedule/{schedule_id}", summary="Delete a schedule")
async def delete_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.models import ScrapeSchedule
    res = await db.execute(
        select(ScrapeSchedule).where(
            ScrapeSchedule.id == schedule_id,
            ScrapeSchedule.tenant_id == current_user["tenant_id"],
        )
    )
    sched = res.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(sched)
    await db.commit()
    return {"deleted": True}


# ──────────────────────────────────────────────────────────
# Autonomous Growth plan — turn the onboarding profile + plan limit into scheduled,
# multi-source scraping. The user picks which sources are ON; quantity derives from the
# plan's monthly-lead limit, split across the chosen sources.
# ──────────────────────────────────────────────────────────

# The nine scrapeable sources (LeadSource values) offered in the Growth screen.
GROWTH_SOURCES = [
    "google_maps", "web_scrape", "directories", "tender", "apollo",
    "linkedin", "facebook", "enrichment", "competitor_ads",
]


class GrowthSetup(BaseModel):
    sources: List[str]
    hour_cairo: int = Field(9, ge=0, le=23)


async def _growth_summary(db, current_user) -> dict:
    from app.models.models import ScrapeSchedule, Lead, LeadStage, Tenant
    from app.services.platform_config import get_plan_limit
    from datetime import datetime as _dt
    tid = current_user["tenant_id"]
    t = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one_or_none()
    plan = t.plan.value if t and t.plan else "trial"
    monthly_limit = await get_plan_limit(db, plan, "monthly_leads") or 5000
    scheds = {s.source.value: s for s in (await db.execute(
        select(ScrapeSchedule).where(ScrapeSchedule.tenant_id == tid))).scalars().all()}

    async def cnt(*conds):
        from sqlalchemy import and_ as _and
        return (await db.execute(select(func.count(Lead.id)).where(_and(Lead.tenant_id == tid, *conds)))).scalar() or 0

    funnel = {
        "leads_total": await cnt(),
        "pending_review": await cnt(Lead.stage == LeadStage.pending_review),
        "approved": await cnt(Lead.stage.in_([LeadStage.approved, LeadStage.outreach, LeadStage.replied,
                                              LeadStage.meeting, LeadStage.proposal, LeadStage.negotiation,
                                              LeadStage.won])),
        "replied": await cnt(Lead.stage == LeadStage.replied),
        "won": await cnt(Lead.stage == LeadStage.won),
    }
    sources = []
    for src in GROWTH_SOURCES:
        s = scheds.get(src)
        sources.append({
            "source": src,
            "enabled": bool(s and s.enabled),
            "monthly_cap": s.monthly_cap if s else 0,
            "monthly_count": (s.monthly_count or 0) if s else 0,
            "hour_cairo": s.hour_cairo if s else 9,
            "last_run_at": s.last_run_at.isoformat() if (s and s.last_run_at) else None,
        })
    return {
        "plan": plan, "monthly_lead_limit": monthly_limit,
        "autonomy": t.autonomy if t else "copilot",
        "profile": {"industry": (t.tenant_profile or {}).get("industry", "") if t else "",
                    "cities": (t.tenant_profile or {}).get("cities", "") if t else ""},
        "sources": sources, "funnel": funnel,
    }


@router.get("/growth", summary="Get the autonomous growth plan + funnel")
async def get_growth(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    return await _growth_summary(db, current_user)


@router.post("/growth", summary="Set up scheduled scraping from the profile + plan limit")
async def setup_growth(body: GrowthSetup, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    from app.api.auth import require_admin
    from app.models.models import ScrapeSchedule, Tenant, LeadSource
    from app.services.platform_config import get_plan_limit
    require_admin(current_user)
    tid = current_user["tenant_id"]
    t = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one_or_none()
    chosen = [s for s in body.sources if s in GROWTH_SOURCES]
    if not chosen:
        raise HTTPException(status_code=400, detail="اختر مصدراً واحداً على الأقل")

    profile = (t.tenant_profile or {}) if t else {}
    industry = profile.get("industry") or ""
    cities = profile.get("cities") or profile.get("city") or ""
    if isinstance(cities, list):
        cities = cities[0] if cities else ""

    plan = t.plan.value if t and t.plan else "trial"
    monthly_limit = await get_plan_limit(db, plan, "monthly_leads") or 5000
    per_source = max(monthly_limit // len(chosen), 30)   # split the monthly quota
    daily = max(per_source // 26, 5)                     # ~26 active days/mo, min 5/run

    existing = {s.source.value: s for s in (await db.execute(
        select(ScrapeSchedule).where(ScrapeSchedule.tenant_id == tid))).scalars().all()}

    for src in GROWTH_SOURCES:
        s = existing.get(src)
        if src in chosen:
            cfg = {"max_results": int(daily)}
            if industry:
                cfg["industry"] = industry
                cfg["query"] = industry
            if cities:
                cfg["location"] = cities
            if s:
                s.enabled = True; s.config = cfg
                s.hour_cairo = body.hour_cairo; s.monthly_cap = int(per_source)
            else:
                db.add(ScrapeSchedule(
                    tenant_id=tid, source=LeadSource(src), config=cfg,
                    hour_cairo=body.hour_cairo, monthly_cap=int(per_source),
                    enabled=True, monthly_count=0,
                ))
        elif s:
            s.enabled = False   # turning a source off pauses its schedule (kept for history)
    await db.commit()
    return await _growth_summary(db, current_user)
