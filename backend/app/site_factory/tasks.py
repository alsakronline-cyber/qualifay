"""Celery jobs for the Site Factory. Registered in app.workers.celery_app (include + beat)."""
import logging

from app.workers.celery_app import celery_app
from app.workers._loop import run_async

logger = logging.getLogger(__name__)

BUILD_BATCH = 15     # previews rendered per run (each = 1 Place Details call + 1 LLM call)
INTRO_BATCH = 20     # intros attempted per run; per-campaign daily caps still apply


@celery_app.task(name="site_factory.discover")
def discover_all():
    """Daily: run every active campaign's search."""
    async def _run():
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.models import SiteFactoryCampaign
        from app.site_factory import service
        total = 0
        async with AsyncSessionLocal() as db:
            camps = (await db.execute(select(SiteFactoryCampaign).where(SiteFactoryCampaign.active == True))).scalars().all()  # noqa: E712
            for c in camps:
                try:
                    total += await service.discover(db, c)
                except Exception as e:
                    logger.warning("site-factory discovery failed for %s: %s", c.id, e)
        return {"added": total}
    return run_async(_run(), reset_ai=True)


@celery_app.task(name="site_factory.discover_campaign")
def discover_campaign(campaign_id: str):
    """On demand ("Run search now" in the dashboard)."""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.models.models import SiteFactoryCampaign
        from app.site_factory import service
        async with AsyncSessionLocal() as db:
            c = await db.get(SiteFactoryCampaign, campaign_id)
            return {"added": await service.discover(db, c)} if c else {"added": 0}
    return run_async(_run(), reset_ai=True)


@celery_app.task(name="site_factory.build")
def build_pending():
    """Every 10 min: gather facts, write copy and render previews for new prospects."""
    async def _run():
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.models import SiteProspect
        from app.site_factory import service, state as S
        done = 0
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(SiteProspect).where(SiteProspect.status == S.FOUND)
                                     .order_by(SiteProspect.created_at).limit(BUILD_BATCH))).scalars().all()
            for p in rows:
                try:
                    done += 1 if await service.build(db, p) else 0
                except Exception as e:
                    logger.warning("site-factory build failed for %s: %s", p.id, e)
                    await db.rollback()
        return {"built": done}
    return run_async(_run(), reset_ai=True)


@celery_app.task(name="site_factory.send_intros")
def send_approved_intros():
    """Every 15 min (only acts 10:00–19:59 Cairo): send intros a human has approved."""
    async def _run():
        import asyncio, random
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.models import SiteProspect, SiteFactoryCampaign
        from app.site_factory import service, state as S
        sent = 0
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(SiteProspect).where(
                SiteProspect.status == S.AWAITING_APPROVAL, SiteProspect.intro_approved_by.isnot(None),
            ).order_by(SiteProspect.created_at).limit(INTRO_BATCH))).scalars().all()
            for p in rows:
                camp = await db.get(SiteFactoryCampaign, p.campaign_id) if p.campaign_id else None
                if not camp or not camp.active:
                    continue
                if await service.send_intro(db, p, camp):
                    sent += 1
                    await asyncio.sleep(random.uniform(40, 110))   # human-like spacing between first contacts
        return {"sent": sent}
    return run_async(_run())


@celery_app.task(name="site_factory.tick")
def tick_all():
    """Hourly: one follow-up per phase, expiry, and data deletion for silent prospects."""
    async def _run():
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.models import SiteProspect
        from app.site_factory import service, state as S
        acted = {}
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(SiteProspect).where(SiteProspect.status.in_(
                list(S.FOLLOWUP_AFTER) + list(S.GIVE_UP_AFTER) + [S.BUILT, S.AWAITING_APPROVAL]
            )).limit(500))).scalars().all()
            for p in rows:
                try:
                    a = await service.tick(db, p)
                    if a:
                        acted[a] = acted.get(a, 0) + 1
                except Exception as e:
                    logger.warning("site-factory tick failed for %s: %s", p.id, e)
                    await db.rollback()
        return acted
    return run_async(_run())


@celery_app.task(name="site_factory.handle_reply", bind=True, max_retries=2)
def handle_reply(self, prospect_id: str, text: str):
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.models.models import SiteProspect
        from app.site_factory import service
        async with AsyncSessionLocal() as db:
            p = await db.get(SiteProspect, prospect_id)
            if p:
                return await service.handle_reply(db, p, text)
    try:
        return run_async(_run(), reset_ai=True)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
