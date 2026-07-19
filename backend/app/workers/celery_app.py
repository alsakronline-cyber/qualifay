from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "qualifay",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.ai_tasks",
        "app.workers.outreach_tasks",
        "app.workers.scrape_tasks",
        "app.workers.email_tasks",
        "app.workers.sequence_tasks",
        "app.workers.webhook_tasks",
        "app.workers.backup_tasks",
        "app.workers.campaign_tasks",
        "app.workers.onboarding_tasks",
        "app.workers.orchestrator_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Africa/Cairo",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_routes={
        "app.workers.scrape_tasks.*": {"queue": "scrape"},
        "app.workers.ai_tasks.*": {"queue": "ai"},
        "app.workers.outreach_tasks.*": {"queue": "outreach"},
    },
    beat_schedule={
        # Daily jobs use fixed cron times, NOT plain intervals: a 86400s interval restarts
        # its countdown on every beat recreate, so frequent redeploys can silently defer a
        # daily job forever (this is why nightly backups never ran for 10 days). Resetting
        # the WhatsApp daily counters is the critical one — without it, instances stay stuck
        # at their cap and no outreach (or compose) can send.
        "reset-daily-wa-limits": {
            "task": "app.workers.outreach_tasks.reset_daily_limits",
            "schedule": crontab(hour=0, minute=1),   # 00:01 Cairo — start of day
        },
        "advance-warmup-days": {
            "task": "app.workers.outreach_tasks.advance_warmup_days",
            "schedule": crontab(hour=0, minute=5),
        },
        "cleanup-pool-expired": {
            "task": "app.workers.ai_tasks.cleanup_lead_pool",
            "schedule": crontab(hour=4, minute=0),
        },
        "re-engage-stale-leads": {
            "task": "re_engage_stale_leads",
            "schedule": crontab(hour=10, minute=0),  # daytime, within outreach hours
        },
        "run-due-scrape-schedules": {
            "task": "run_due_scrape_schedules",
            "schedule": 3600.0,  # hourly — launches daily searches at their chosen Cairo hour
        },
        "poll-inbound-email": {
            "task": "poll_inbound_email",
            "schedule": 180.0,  # every 3 min — fetch email replies into the inbox
        },
        "run-due-sequence-steps": {
            "task": "run_due_sequence_steps",
            "schedule": 300.0,  # every 5 min — advance enrolled leads through cadences
        },
        "nightly-db-backup": {
            "task": "backups.run",
            # Fixed 03:00 Africa/Cairo — a plain 86400s interval restarts its countdown
            # every time the beat container is recreated, so frequent redeploys can defer
            # it indefinitely (it silently never ran for 10 days). A cron time always fires.
            "schedule": crontab(hour=3, minute=0),
        },
        "sync-campaign-audiences": {
            "task": "campaigns.sync_audiences",
            "schedule": 600.0,  # every 10 min — enroll new matching leads into running campaigns
        },
        "orchestrator-run": {
            "task": "orchestrator.run",
            "schedule": 900.0,  # every 15 min — the autonomous brain assesses each tenant
        },
        "daily-digest": {
            "task": "orchestrator.daily_digest",
            "schedule": crontab(hour=20, minute=0),  # 20:00 Africa/Cairo — owner's end-of-day report
        },
        "alert-missed-followups": {
            "task": "orchestrator.alert_missed_followups",
            "schedule": crontab(hour="9,15", minute=30),  # 09:30 & 15:30 Cairo — flag 2-day-stale replies
        },
        "harvest-learnings": {
            "task": "orchestrator.harvest_learnings",
            "schedule": 14400.0,  # every 4h — distill won/lost leads into tenant memory
        },
        "optimize-ab-tests": {
            "task": "orchestrator.optimize_ab_tests",
            "schedule": 21600.0,  # every 6h — auto-promote a clear A/B winner to a template
        },
    },
)
