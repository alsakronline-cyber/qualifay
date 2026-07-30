"""Workspace builder — turns the finished onboarding profile into a draft workspace
plan (via the reasoning model) and stashes it on the tenant for the review screen."""
import asyncio
import logging

from sqlalchemy import select

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


from app.workers._loop import run_async


@celery_app.task(name="onboarding.build_workspace_plan")
def build_workspace_plan(tenant_id: str):
    return run_async(_build(tenant_id))


async def _build(tenant_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Tenant
    from app.services.ai_service import ai_service

    async with AsyncSessionLocal() as db:
        t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if not t or not t.tenant_profile:
            return {"ok": False, "error": "no profile"}

        profile = {k: v for k, v in (t.tenant_profile or {}).items() if not k.startswith("_")}
        plan = await ai_service.generate_build_plan(profile)

        merged = dict(t.tenant_profile or {})
        merged["_build_draft"] = plan
        t.tenant_profile = merged
        await db.commit()
        logger.info("workspace plan built for tenant %s (%d templates)", tenant_id, len(plan.get("templates", [])))
        return {"ok": True, "has_plan": bool(plan)}
