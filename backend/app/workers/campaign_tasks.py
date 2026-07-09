"""Campaign auto-enroll — keeps running campaigns topped up with newly-scraped leads
that match their audience filter, so a campaign is a living thing, not a one-shot blast.
The sequence beat task does the actual sending; this only enrolls."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro
    return asyncio.run(_wrapped())


@celery_app.task(name="campaigns.sync_audiences")
def sync_campaign_audiences():
    return run_async(_sync())


async def _sync():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Campaign, Sequence, SequenceEnrollment, Lead
    from app.api.campaigns import audience_conditions

    total = 0
    async with AsyncSessionLocal() as db:
        campaigns = (await db.execute(select(Campaign).where(and_(
            Campaign.status == "running", Campaign.auto_enroll == True  # noqa: E712
        )))).scalars().all()

        for c in campaigns:
            if not c.sequence_id:
                continue
            seq = (await db.execute(select(Sequence).where(Sequence.id == c.sequence_id))).scalar_one_or_none()
            if not seq or not seq.steps:
                continue

            first_delay = sorted(seq.steps, key=lambda x: x.step_order)[0].delay_hours or 0
            first_run = datetime.utcnow() + timedelta(hours=first_delay)

            already = {e.lead_id for e in (await db.execute(
                select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == seq.id)
            )).scalars().all()}

            leads = (await db.execute(select(Lead.id).where(
                and_(*audience_conditions(c.audience_filter, c.tenant_id))
            ))).scalars().all()

            added = 0
            for lid in leads:
                if lid in already:
                    continue
                db.add(SequenceEnrollment(
                    tenant_id=c.tenant_id, sequence_id=seq.id, lead_id=lid, campaign_id=c.id,
                    current_step=0, status="active", next_run_at=first_run,
                ))
                added += 1
            if added:
                logger.info("campaign %s auto-enrolled %d new leads", c.id, added)
            total += added

        await db.commit()
    return {"enrolled": total}
