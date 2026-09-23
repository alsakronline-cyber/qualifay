"""Trial enforcement and backup health.

Two guardrails that were missing in production:

1. Nothing ever acted on `tenant.trial_ends_at`. Three trials sat expired for 14-28 days
   with full access, so on a paid plan nobody would ever have had to pay.

2. Nightly backups failed silently for ~2 months and no one noticed, because a backup that
   doesn't run produces no error — only an absence. Absence has to be checked for explicitly.
"""
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.workers._loop import run_async as _run_async

logger = logging.getLogger(__name__)

# Days past trial_ends_at before access is cut. A few days of grace avoids locking someone
# out over a weekend while an invoice is in flight; it is a business courtesy, not a bug.
TRIAL_GRACE_DAYS = 3

# Backups run nightly, so anything older than this means at least one night was missed.
BACKUP_STALE_HOURS = 48


def run_async(coro):
    return _run_async(coro)


@celery_app.task(name="billing.enforce_trials")
def enforce_trials(dry_run: bool = False):
    """dry_run reports who WOULD be suspended without touching anything — suspending a live
    tenant cuts off their WhatsApp and inbox, so it's worth being able to look first."""
    return run_async(_enforce_trials(dry_run=dry_run))


async def _enforce_trials(dry_run: bool = False):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Tenant, Plan, Subscription, NotificationType
    from app.services.notification_service import notify

    now = datetime.utcnow()
    warned, suspended = [], []

    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant).where(
            Tenant.plan == Plan.trial,
            Tenant.trial_ends_at.isnot(None),
        ))).scalars().all()

        for t in tenants:
            # A tenant who has actually paid must never be locked out by the trial clock,
            # whatever the stale trial date says.
            sub = (await db.execute(select(Subscription).where(
                Subscription.tenant_id == t.id))).scalars().first()
            if sub and (sub.status or "").lower() in ("active", "paid"):
                continue

            days_over = (now - t.trial_ends_at).days

            if days_over >= TRIAL_GRACE_DAYS:
                if (t.status or "active") != "suspended":
                    suspended.append(t.name)
                    if dry_run:
                        continue
                    t.status = "suspended"
                    try:
                        await notify(db, t.id, NotificationType.system,
                                     title="انتهت الفترة التجريبية",
                                     message=("انتهت فترتك التجريبية. رقِّ خطتك لاستعادة الوصول "
                                              "إلى الحساب. بياناتك محفوظة ولم يتم حذف أي شيء."),
                                     data={"reason": "trial_expired", "days_over": days_over})
                    except Exception as e:
                        logger.warning("trial notify failed for %s: %s", t.id, e)
            elif days_over >= 0:
                warned.append(t.name)
                if dry_run:
                    continue
                try:
                    await notify(db, t.id, NotificationType.system,
                                 title="فترتك التجريبية انتهت",
                                 message=(f"انتهت الفترة التجريبية. لديك "
                                          f"{TRIAL_GRACE_DAYS - days_over} يوم قبل إيقاف الوصول."),
                                 data={"reason": "trial_grace", "days_left": TRIAL_GRACE_DAYS - days_over})
                except Exception as e:
                    logger.warning("trial notify failed for %s: %s", t.id, e)

        if not dry_run:
            await db.commit()

    logger.info("trial enforcement (dry_run=%s): suspended=%s warned=%s",
                dry_run, suspended, warned)
    return {"dry_run": dry_run, "suspended": suspended, "warned": warned}


@celery_app.task(name="billing.backup_healthcheck")
def backup_healthcheck():
    return run_async(_backup_healthcheck())


async def _backup_healthcheck():
    """Alert the platform owner if no recent backup exists. A missing backup is invisible
    until you need it, which is exactly the wrong moment to find out."""
    from app.core.database import AsyncSessionLocal
    from app.models.models import Tenant, NotificationType
    from app.services.notification_service import notify
    from app.workers.backup_tasks import BACKUP_DIR

    newest, source = None, "none"

    # local dumps
    try:
        for f in os.listdir(BACKUP_DIR):
            if f.endswith(".sql.gz"):
                ts = datetime.utcfromtimestamp(os.path.getmtime(os.path.join(BACKUP_DIR, f)))
                if newest is None or ts > newest:
                    newest, source = ts, "local"
    except Exception as e:
        logger.warning("backup dir unreadable: %s", e)

    # MinIO copies
    try:
        from minio import Minio
        from app.core.config import settings
        ep = settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        c = Minio(ep, settings.MINIO_USER, settings.MINIO_PASSWORD, secure=False)
        if c.bucket_exists("backups"):
            for o in c.list_objects("backups", recursive=True):
                ts = o.last_modified.replace(tzinfo=None)
                if newest is None or ts > newest:
                    newest, source = ts, "minio"
    except Exception as e:
        logger.warning("minio backup check failed: %s", e)

    age_h = None if newest is None else round((datetime.utcnow() - newest).total_seconds() / 3600, 1)
    stale = newest is None or age_h > BACKUP_STALE_HOURS

    if stale:
        msg = ("لا توجد نسخة احتياطية حديثة لقاعدة البيانات"
               if newest is None else
               f"أحدث نسخة احتياطية عمرها {age_h} ساعة (الحد {BACKUP_STALE_HOURS}).")
        logger.error("BACKUP STALE: %s", msg)
        async with AsyncSessionLocal() as db:
            owner = (await db.execute(select(Tenant).where(
                Tenant.plan == "agency"))).scalars().first()
            if owner:
                try:
                    await notify(db, owner.id, NotificationType.system,
                                 title="⚠️ النسخ الاحتياطي متوقف",
                                 message=msg, data={"age_hours": age_h}, urgent=True)
                    await db.commit()
                except Exception as e:
                    logger.warning("backup alert notify failed: %s", e)

    return {"newest": str(newest), "age_hours": age_h, "source": source, "stale": stale}
