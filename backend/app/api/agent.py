"""Agent API — browser-extension automation (Option A): LinkedIn + Facebook sourcing.

The Chrome extension's background worker polls GET /tasks/next on its own schedule
(chrome.alarms) — no human clicks required after one-time setup. It scrapes in a
background tab and POSTs results to /ingest, which hands off to a Celery task for AI
qualification (fire-and-forget, so this endpoint never blocks on an AI call).

Authenticated by a per-tenant agent key (X-Agent-Key header) — separate from the login
JWT, so the extension never touches a user's real session token. Daily caps and minimum
polling intervals are enforced server-side in /tasks/next, so a misbehaving or tampered
client can't exceed the configured pace no matter what it asks for.
"""
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.models import AgentPlatform, AgentTask, Tenant

router = APIRouter()

STALE_AFTER = timedelta(minutes=15)  # an in_progress task with no result this long is retried


async def get_tenant_by_agent_key(
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.agent_key == x_agent_key))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid agent key")
    return tenant


# ─── Schemas ────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    platform: AgentPlatform
    type: str  # "linkedin_search" | "linkedin_profile_visit" | "facebook_group_watch" | "facebook_page_watch"
    query: Optional[str] = None
    location: Optional[str] = None
    group_id: Optional[str] = None
    page_id: Optional[str] = None
    profile_url: Optional[str] = None  # for linkedin_profile_visit — visits one profile to pull contact info
    max_results: int = Field(30, ge=1, le=200)
    recurring: bool = False
    interval_minutes: int = Field(120, ge=15, le=1440)

    def build_params(self) -> dict:
        p = {"max_results": self.max_results}
        if self.query:
            p["query"] = self.query
        if self.location:
            p["location"] = self.location
        if self.group_id:
            p["group_id"] = self.group_id
        if self.page_id:
            p["page_id"] = self.page_id
        if self.profile_url:
            p["profile_url"] = self.profile_url
        return p


class IngestItem(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    url: Optional[str] = None   # profile_url (LinkedIn) or post_url (Facebook)
    text: Optional[str] = None  # post text (Facebook) — used for AI intent classification
    location: Optional[str] = None


class IngestRequest(BaseModel):
    task_id: str
    platform: AgentPlatform
    items: List[IngestItem] = Field(default_factory=list, max_length=200)


def _task_dict(t: AgentTask) -> dict:
    return {
        "id": t.id,
        "platform": t.platform.value if t.platform else None,
        "type": t.type,
        "params": t.params or {},
        "status": t.status,
        "recurring": t.recurring,
        "interval_minutes": t.interval_minutes,
        "result_count": t.result_count or 0,
        "total_results": t.total_results or 0,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


# ─── Setup (dashboard side — normal JWT auth) ──────────────

@router.get("/setup", summary="Get (or generate) this tenant's agent key for the extension")
async def get_agent_setup(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user["tenant_id"]))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.agent_key:
        tenant.agent_key = secrets.token_urlsafe(32)
        await db.commit()
    return {
        "agent_key": tenant.agent_key,
        "daily_cap_linkedin": tenant.agent_daily_cap_linkedin,
        "daily_cap_facebook": tenant.agent_daily_cap_facebook,
        "min_interval_seconds": tenant.agent_min_interval_seconds,
    }


@router.post("/regenerate-key", summary="Rotate the agent key (invalidates the old one)")
async def regenerate_agent_key(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user["tenant_id"]))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.agent_key = secrets.token_urlsafe(32)
    await db.commit()
    return {"agent_key": tenant.agent_key}


@router.post("/tasks", summary="Queue a LinkedIn/Facebook automation task (from the wizard)")
async def create_task(
    body: CreateTaskRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = AgentTask(
        tenant_id=current_user["tenant_id"],
        platform=body.platform,
        type=body.type,
        params=body.build_params(),
        recurring=body.recurring,
        interval_minutes=body.interval_minutes,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_dict(task)


@router.get("/tasks", summary="List this tenant's automation tasks")
async def list_tasks(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.tenant_id == current_user["tenant_id"])
        .order_by(AgentTask.created_at.desc())
        .limit(100)
    )
    return [_task_dict(t) for t in result.scalars().all()]


@router.delete("/tasks/{task_id}", summary="Cancel/delete an automation task")
async def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentTask).where(
            AgentTask.id == task_id, AgentTask.tenant_id == current_user["tenant_id"]
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await db.commit()
    return {"deleted": True}


# ─── Extension side (agent-key auth) ───────────────────────

@router.get("/tasks/next", summary="[Extension] Poll for the next task to run")
async def get_next_task(
    platforms: str = "linkedin,facebook",
    tenant: Tenant = Depends(get_tenant_by_agent_key),
    db: AsyncSession = Depends(get_db),
):
    wanted = [p.strip() for p in platforms.split(",") if p.strip()]
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)

    for platform in wanted:
        try:
            plat_enum = AgentPlatform(platform)
        except ValueError:
            continue

        cap = (
            tenant.agent_daily_cap_linkedin
            if plat_enum == AgentPlatform.linkedin
            else tenant.agent_daily_cap_facebook
        )
        used_result = await db.execute(
            select(func.coalesce(func.sum(AgentTask.result_count), 0)).where(
                AgentTask.tenant_id == tenant.id,
                AgentTask.platform == plat_enum,
                AgentTask.completed_at >= today_start,
            )
        )
        if (used_result.scalar() or 0) >= cap:
            continue  # daily cap reached for this platform — skip to the next one

        last_result = await db.execute(
            select(AgentTask.started_at)
            .where(
                AgentTask.tenant_id == tenant.id,
                AgentTask.platform == plat_enum,
                AgentTask.started_at.isnot(None),
            )
            .order_by(AgentTask.started_at.desc())
            .limit(1)
        )
        last_started = last_result.scalar_one_or_none()
        if last_started and (now - last_started).total_seconds() < tenant.agent_min_interval_seconds:
            continue  # too soon since the last poll for this platform

        task_result = await db.execute(
            select(AgentTask)
            .where(
                AgentTask.tenant_id == tenant.id,
                AgentTask.platform == plat_enum,
                or_(
                    and_(
                        AgentTask.status == "pending",
                        or_(AgentTask.next_eligible_at.is_(None), AgentTask.next_eligible_at <= now),
                    ),
                    and_(AgentTask.status == "in_progress", AgentTask.started_at < now - STALE_AFTER),
                ),
            )
            .order_by(AgentTask.created_at.asc())
            .limit(1)
        )
        task = task_result.scalar_one_or_none()
        if not task:
            continue

        task.status = "in_progress"
        task.started_at = now
        await db.commit()
        await db.refresh(task)
        return {"task": _task_dict(task)}

    return {"task": None}


@router.post("/ingest", status_code=202, summary="[Extension] Submit scraped results")
async def ingest_agent_results(
    body: IngestRequest,
    tenant: Tenant = Depends(get_tenant_by_agent_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentTask).where(AgentTask.id == body.task_id, AgentTask.tenant_id == tenant.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from app.workers.ai_tasks import ingest_agent_leads

    ingest_agent_leads.delay(
        tenant.id, task.id, body.platform.value, [item.model_dump() for item in body.items]
    )
    return {"status": "accepted", "items": len(body.items)}
