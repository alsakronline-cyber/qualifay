"""Campaign auto-enroll — keeps running campaigns topped up with newly-scraped leads
that match their audience filter, so a campaign is a living thing, not a one-shot blast.
The sequence beat task does the actual sending; this only enrolls."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


from app.workers._loop import run_async


@celery_app.task(name="campaigns.sync_audiences")
def sync_campaign_audiences():
    return run_async(_sync())


async def _sync():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Campaign, Sequence
    from app.api.campaigns import _enroll_audience  # shared with the launch path

    total = 0
    async with AsyncSessionLocal() as db:
        campaigns = (await db.execute(select(Campaign).where(and_(
            Campaign.status == "running", Campaign.auto_enroll == True  # noqa: E712
        )))).scalars().all()

        for c in campaigns:
            if not c.sequence_id:
                continue
            seq = (await db.execute(select(Sequence).options(selectinload(Sequence.steps)).where(
                Sequence.id == c.sequence_id))).scalar_one_or_none()
            if not seq or not seq.steps:
                continue

            added = await _enroll_audience(c, seq, c.tenant_id, db)
            if added:
                logger.info("campaign %s auto-enrolled %d new leads", c.id, added)
            total += added

        await db.commit()
    return {"enrolled": total}
