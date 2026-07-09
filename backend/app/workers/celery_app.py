from celery import Celery
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
        "reset-daily-wa-limits": {
            "task": "app.workers.outreach_tasks.reset_daily_limits",
            "schedule": 86400.0,
        },
        "advance-warmup-days": {
            "task": "app.workers.outreach_tasks.advance_warmup_days",
            "schedule": 86400.0,
        },
        "cleanup-pool-expired": {
            "task": "app.workers.ai_tasks.cleanup_lead_pool",
            "schedule": 86400.0,
        },
        "re-engage-stale-leads": {
            "task": "re_engage_stale_leads",
            "schedule": 86400.0,
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
            "schedule": 86400.0,  # daily pg_dump → /app/backups + MinIO
        },
        "sync-campaign-audiences": {
            "task": "campaigns.sync_audiences",
            "schedule": 600.0,  # every 10 min — enroll new matching leads into running campaigns
        },
    },
)
