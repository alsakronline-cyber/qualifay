"""Celery scrape tasks — one task per scraper, all share the 'scrape' queue"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Scraper registry — maps LeadSource enum values to classes
# ──────────────────────────────────────────────────────────
def _get_scraper_map():
    """Lazy import to avoid circular deps and heavy Playwright loads at startup."""
    from scrapers.google_maps import GoogleMapsScraper
    from scrapers.websites import WebsiteScraper
    from scrapers.directories import DirectoriesScraper
    from scrapers.tenders import TendersScraper
    from scrapers.osm import OSMScraper
    from scrapers.yellowpages_eg import YellowPagesEgyptScraper
    from scrapers.linkedin_search import LinkedInSearchScraper
    from scrapers.facebook_groups import FacebookGroupsScraper
    from scrapers.enrichment import EnrichmentScraper
    from scrapers.competitor_ads import CompetitorAdsScraper

    return {
        "google_maps": GoogleMapsScraper,
        "web_scrape": WebsiteScraper,
        "directories": DirectoriesScraper,
        "tender": TendersScraper,
        "apollo": OSMScraper,  # free OpenStreetMap business database (replaces Apollo)
        "yellowpages": YellowPagesEgyptScraper,
        "linkedin": LinkedInSearchScraper,  # Google CSE discovery (replaces blocked web scraping)
        "facebook": FacebookGroupsScraper,
        "enrichment": EnrichmentScraper,
        "competitor_ads": CompetitorAdsScraper,
    }


def run_async(coro):
    """Run an async coroutine in a fresh event loop (Celery workers are sync).

    Each task gets a new loop; the shared async DB engine's pooled asyncpg
    connections are bound to whichever loop first opened them, so we dispose the
    pool at the start of every task to avoid "Future attached to a different loop"
    errors. This runs in the Celery process only — the FastAPI engine is untouched.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro

    try:
        return loop.run_until_complete(_wrapped())
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────
# Main scrape task
# ──────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, queue="scrape")
def run_scrape_job(self, job_id: str):
    """
    Execute a ScrapeJob end-to-end:
      1. Load ScrapeJob from DB, set status=running
      2. Instantiate the correct scraper from SCRAPER_MAP
      3. Iterate raw leads, normalize, save, queue qualify_lead
      4. On BlockedError: pause job for 30 min, retry
      5. On completion: set status=done
      6. On failure: set status=error
    """
    try:
        return run_async(_run_scrape_job_async(self, job_id))
    except Exception as exc:
        logger.error(f"Scrape job {job_id} hard failure: {exc}", exc_info=True)
        run_async(_set_job_error(job_id, str(exc)))
        raise


async def _run_scrape_job_async(task, job_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import ScrapeJob, Lead, LeadStage, Notification, NotificationType
    from app.lib.phone import normalize_egyptian_phone
    from scrapers.base import BlockedError
    from sqlalchemy import select

    scraper_map = _get_scraper_map()

    async with AsyncSessionLocal() as db:
        # 1. Load job
        result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.warning(f"ScrapeJob {job_id} not found")
            return {"error": "job_not_found"}

        # Check if job is paused and pause window hasn't expired
        if job.status == "paused" and job.paused_until:
            paused_until = job.paused_until
            if paused_until.tzinfo is None:
                paused_until = paused_until.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if now < paused_until:
                wait_seconds = (paused_until - now).total_seconds()
                logger.info(f"Job {job_id} still paused for {wait_seconds:.0f}s")
                raise task.retry(countdown=int(wait_seconds) + 5)

        # 2. Set running
        job.status = "running"
        job.celery_task_id = task.request.id
        await db.commit()

        # 3. Resolve scraper
        source_value = job.source.value if hasattr(job.source, "value") else str(job.source)
        scraper_cls = scraper_map.get(source_value)
        if not scraper_cls:
            job.status = "error"
            job.error_message = f"Unknown scraper source: {source_value}"
            await db.commit()
            return {"error": "unknown_source"}

        scraper = scraper_cls()

        # 4. Run scraper and save leads
        leads_found = 0
        try:
            async for raw_lead in scraper.scrape(job.config or {}, job.tenant_id):
                # Normalize phone
                phone = raw_lead.phone
                if phone:
                    phone = normalize_egyptian_phone(str(phone)) or phone

                # Deduplicate by phone within this tenant
                if phone:
                    dup_result = await db.execute(
                        select(Lead).where(
                            Lead.tenant_id == job.tenant_id,
                            Lead.phone == phone,
                        )
                    )
                    if dup_result.scalar_one_or_none():
                        logger.debug(f"Skipping duplicate phone {phone}")
                        continue

                # Map source enum value
                from app.models.models import LeadSource
                try:
                    lead_source = LeadSource(source_value)
                except ValueError:
                    lead_source = LeadSource.web_scrape

                # Create Lead record
                lead = Lead(
                    tenant_id=job.tenant_id,
                    source=lead_source,
                    name=raw_lead.name,
                    phone=phone,
                    email=raw_lead.email,
                    company=raw_lead.company,
                    industry=raw_lead.industry,
                    company_size=raw_lead.company_size,
                    city=raw_lead.city,
                    governorate=raw_lead.governorate,
                    website=raw_lead.website,
                    linkedin_url=raw_lead.linkedin_url,
                    stage=LeadStage.new,
                    raw_data=raw_lead.raw_data or {},
                )
                db.add(lead)
                await db.flush()  # Get lead.id before commit

                # Queue BANT qualification
                try:
                    from app.workers.ai_tasks import qualify_lead
                    qualify_lead.delay(lead.id)
                except Exception as e:
                    logger.warning(f"Failed to queue qualify_lead for {lead.id}: {e}")

                # P7: Queue URL enrichment if URLs present
                raw_d = raw_lead.raw_data or {}
                has_urls = any([
                    raw_lead.website,
                    raw_d.get("facebook_url"),
                    raw_d.get("linkedin_url"),
                ])
                if has_urls:
                    try:
                        from app.workers.ai_tasks import enrich_lead_from_urls
                        enrich_lead_from_urls.apply_async(
                            args=[lead.id, job.tenant_id],
                            queue="ai",
                            countdown=5,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to queue enrich_lead_from_urls for {lead.id}: {e}")

                leads_found += 1
                job.leads_found = leads_found

                # Commit in batches of 10 to avoid long transactions
                if leads_found % 10 == 0:
                    await db.commit()
                    logger.info(f"Job {job_id}: {leads_found} leads saved so far")

        except BlockedError as exc:
            # Scraper was blocked — pause job for 30 minutes
            logger.warning(f"Scraper blocked for job {job_id}: {exc}")
            job.status = "paused"
            job.paused_until = datetime.utcnow() + timedelta(minutes=30)
            job.error_message = f"Blocked: {exc}"
            job.leads_found = leads_found
            await db.commit()

            # Create notification for tenant
            notification = Notification(
                tenant_id=job.tenant_id,
                type=NotificationType.system,
                title="Scraper Paused",
                message=(
                    f"The {source_value} scraper was blocked and has been paused. "
                    f"It will auto-resume in 30 minutes."
                ),
                data={"job_id": job_id, "source": source_value},
            )
            db.add(notification)
            await db.commit()

            # Retry after 30 minutes + buffer
            raise task.retry(exc=exc, countdown=31 * 60)

        except Exception as exc:
            # Unexpected failure
            logger.error(f"Scrape job {job_id} unexpected error: {exc}", exc_info=True)
            job.status = "error"
            job.error_message = str(exc)[:500]
            job.leads_found = leads_found
            await db.commit()
            raise

        # 5. Completion
        await db.commit()  # Final commit for remaining leads
        job.status = "done"
        job.completed_at = datetime.utcnow()
        job.leads_found = leads_found

        # If this job came from a daily schedule, count its leads toward the monthly cap.
        sched_id = (job.config or {}).get("_schedule_id")
        if sched_id:
            from app.models.models import ScrapeSchedule
            sched_res = await db.execute(select(ScrapeSchedule).where(ScrapeSchedule.id == sched_id))
            sched = sched_res.scalar_one_or_none()
            if sched:
                sched.monthly_count = (sched.monthly_count or 0) + leads_found

        await db.commit()

        logger.info(f"Scrape job {job_id} completed: {leads_found} leads found")
        return {"job_id": job_id, "status": "done", "leads_found": leads_found}


async def _set_job_error(job_id: str, error_msg: str):
    """Set job status to error — called from sync exception handler."""
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.models import ScrapeJob
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                job.status = "error"
                job.error_message = error_msg[:500]
                await db.commit()
    except Exception as e:
        logger.error(f"Failed to set job error status: {e}")


# ──────────────────────────────────────────────────────────
# Control tasks
# ──────────────────────────────────────────────────────────

@celery_app.task(queue="scrape")
def pause_scrape_job(job_id: str):
    """Pause a running scrape job."""
    return run_async(_update_job_status(job_id, "paused"))


@celery_app.task(queue="scrape")
def cancel_scrape_job(job_id: str):
    """Cancel a running scrape job."""
    return run_async(_update_job_status(job_id, "cancelled"))


async def _update_job_status(job_id: str, status: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import ScrapeJob
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = status
            if status == "cancelled":
                job.completed_at = datetime.utcnow()
            await db.commit()
    return {"job_id": job_id, "status": status}


@celery_app.task(name="run_due_scrape_schedules", queue="scrape")
def run_due_scrape_schedules():
    """Hourly beat task: launch any daily schedules due at the current Cairo hour.

    Enforces a monthly cap per schedule (resets each calendar month) and relies on the
    existing per-tenant phone dedupe inside run_scrape_job so repeated daily runs don't
    create duplicate leads.
    """
    return run_async(_run_due_scrape_schedules_async())


def schedule_due_action(sched, today, month_key) -> str:
    """Decide what to do with a schedule at the current Cairo hour. Pure function so the
    due-logic is unit-testable without a DB. `sched` only needs the attributes
    last_run_at, month_key, monthly_count, monthly_cap.

    Returns one of: "ran_today" (skip), "capped" (skip, but stamp last_run), "run".
    The month-rollover reset is applied to `sched` in-place by the caller based on the
    separate `should_reset_month` check below.
    """
    if sched.last_run_at and sched.last_run_at.date() == today:
        return "ran_today"
    effective_count = 0 if sched.month_key != month_key else (sched.monthly_count or 0)
    if effective_count >= (sched.monthly_cap or 0):
        return "capped"
    return "run"


async def _run_due_scrape_schedules_async():
    from zoneinfo import ZoneInfo
    from app.core.database import AsyncSessionLocal
    from app.models.models import ScrapeSchedule, ScrapeJob
    from sqlalchemy import select

    now_cairo = datetime.now(ZoneInfo("Africa/Cairo"))
    hour = now_cairo.hour
    today = now_cairo.date()
    month_key = now_cairo.strftime("%Y-%m")
    launched = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScrapeSchedule).where(
                ScrapeSchedule.enabled == True,  # noqa: E712
                ScrapeSchedule.hour_cairo == hour,
            )
        )
        schedules = result.scalars().all()

        for sched in schedules:
            action = schedule_due_action(sched, today, month_key)
            # Reset monthly counter at month rollover (regardless of action).
            if sched.month_key != month_key:
                sched.month_key = month_key
                sched.monthly_count = 0
            if action == "ran_today":
                continue
            if action == "capped":
                sched.last_run_at = datetime.utcnow()
                continue

            cfg = dict(sched.config or {})
            # Rotate through AI-expanded concrete queries so each day targets a different
            # niche/city instead of scraping the same broad term forever.
            qs = cfg.get("queries")
            if isinstance(qs, list) and qs:
                cfg["query"] = qs[today.toordinal() % len(qs)]
            cfg["_schedule_id"] = sched.id  # so run_scrape_job can bump the counter
            job = ScrapeJob(
                tenant_id=sched.tenant_id,
                source=sched.source,
                config=cfg,
                status="pending",
                leads_found=0,
                leads_qualified=0,
            )
            db.add(job)
            await db.flush()
            run_scrape_job.delay(job.id)
            sched.last_run_at = datetime.utcnow()
            launched.append(job.id)

        await db.commit()

    return {"launched": launched, "hour_cairo": hour}
