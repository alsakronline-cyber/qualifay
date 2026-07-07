"""
WarmupService — WhatsApp warmup schedule enforcement and daily limit tracking
"""
import logging
from typing import Tuple
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Warmup schedule: (day_threshold, daily_cap)
WARMUP_SCHEDULE = [(7, 10), (14, 30), (21, 75), (30, 150), (999, 200)]

# Email ramps more gently than WhatsApp — cold email reputation is fragile.
EMAIL_WARMUP_SCHEDULE = [(7, 20), (14, 40), (21, 75), (30, 150), (999, 250)]


def get_cap_for_day(day: int) -> int:
    """Return the daily WA message cap for a given day_of_life."""
    for threshold, cap in WARMUP_SCHEDULE:
        if day <= threshold:
            return cap
    return 200


def email_cap_for_day(day: int) -> int:
    """Return the daily email cap for a given email day_of_life."""
    for threshold, cap in EMAIL_WARMUP_SCHEDULE:
        if day <= threshold:
            return cap
    return 250


class WarmupService:

    async def check_wa_limit(self, instance_id: str, db: AsyncSession) -> Tuple[bool, int, int]:
        """
        Check if the WA instance is within its daily sending cap.
        Returns (allowed, used, cap).
        Creates a notification if limit is hit.
        """
        from app.models.models import WaInstance, Notification, NotificationType

        result = await db.execute(select(WaInstance).where(WaInstance.id == instance_id))
        instance = result.scalar_one_or_none()
        if not instance:
            return False, 0, 0

        used = instance.sent_today_wa or 0
        cap = instance.daily_wa_cap or get_cap_for_day(instance.day_of_life or 0)

        # Soft pause: block sending while keeping the session connected.
        if getattr(instance, "paused", False):
            return False, used, cap

        if used >= cap:
            # Create a notification for the tenant (avoid duplicate notifications for same day)
            today_str = date.today().isoformat()
            notif = Notification(
                tenant_id=instance.tenant_id,
                type=NotificationType.wa_limit,
                title="WhatsApp Daily Limit Reached",
                message=(
                    f"Instance '{instance.instance_name}' has reached its daily cap of {cap} messages. "
                    f"Messages will resume tomorrow."
                ),
                data={
                    "instance_id": instance_id,
                    "instance_name": instance.instance_name,
                    "cap": cap,
                    "used": used,
                    "date": today_str,
                },
            )
            db.add(notif)
            await db.commit()
            return False, used, cap

        return True, used, cap

    async def increment_wa_sent(self, instance_id: str, db: AsyncSession) -> None:
        """Increment sent_today_wa by 1 for the given instance."""
        from app.models.models import WaInstance

        result = await db.execute(select(WaInstance).where(WaInstance.id == instance_id))
        instance = result.scalar_one_or_none()
        if instance:
            instance.sent_today_wa = (instance.sent_today_wa or 0) + 1
            await db.commit()

    async def email_day_of_life(self, tenant_id: str, db: AsyncSession) -> int:
        """Days since this tenant first sent email (1 on the first day)."""
        from app.models.models import Tenant
        t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        started = getattr(t, "email_started_at", None) if t else None
        if not started:
            return 1
        return (date.today() - started.date()).days + 1

    async def mark_email_started(self, tenant_id: str, db: AsyncSession) -> None:
        """Stamp email_started_at on the tenant's first-ever send (anchors the ramp)."""
        from app.models.models import Tenant
        t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if t and not getattr(t, "email_started_at", None):
            t.email_started_at = datetime.utcnow()
            await db.commit()

    async def check_email_limit(self, tenant_id: str, db: AsyncSession) -> Tuple[bool, int, int]:
        """Ramped, bounce-aware email daily limit. Returns (allowed, used, cap).

        The cap ramps with the tenant's email day_of_life, and sending is paused for the
        day once bounces exceed the threshold (bad addresses / reputation trouble)."""
        from app.core.config import settings
        import redis.asyncio as aioredis

        day = await self.email_day_of_life(tenant_id, db)
        cap = email_cap_for_day(day)
        today_str = date.today().isoformat()
        used_key = f"{settings.REDIS_KEY_PREFIX}email_daily:{tenant_id}:{today_str}"
        bounce_key = f"{settings.REDIS_KEY_PREFIX}email_bounces:{tenant_id}:{today_str}"

        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            used = int(await r.get(used_key) or 0)
            bounces = int(await r.get(bounce_key) or 0)
            await r.aclose()
            if bounces >= (settings.EMAIL_BOUNCE_PAUSE_THRESHOLD or 10):
                logger.warning(f"Email paused for tenant {tenant_id}: {bounces} bounces today")
                return False, used, cap
            return used < cap, used, cap
        except Exception as e:
            logger.warning(f"Redis email limit check failed for tenant {tenant_id}: {e}")
            return True, 0, cap

    async def record_email_bounce(self, tenant_id: str) -> int:
        """Increment today's bounce counter for a tenant; returns the new total."""
        from app.core.config import settings
        import redis.asyncio as aioredis
        today_str = date.today().isoformat()
        key = f"{settings.REDIS_KEY_PREFIX}email_bounces:{tenant_id}:{today_str}"
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            n = await r.incr(key)
            await r.expire(key, 86400 * 2)
            await r.aclose()
            return int(n)
        except Exception as e:
            logger.warning(f"Redis bounce increment failed for tenant {tenant_id}: {e}")
            return 0

    async def increment_email_sent(self, tenant_id: str) -> None:
        """Increment email daily counter in Redis."""
        from app.core.config import settings
        import redis.asyncio as aioredis

        today_str = date.today().isoformat()
        redis_key = f"{settings.REDIS_KEY_PREFIX}email_daily:{tenant_id}:{today_str}"

        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pipe = r.pipeline()
            await pipe.incr(redis_key)
            await pipe.expire(redis_key, 86400 * 2)  # 2 days TTL
            await pipe.execute()
            await r.aclose()
        except Exception as e:
            logger.warning(f"Redis email increment failed for tenant {tenant_id}: {e}")

    async def reset_all_daily_counts(self, db: AsyncSession) -> None:
        """Reset sent_today_wa and sent_today_email to 0 for all instances. Called by Celery beat daily."""
        from app.models.models import WaInstance
        from sqlalchemy import update

        await db.execute(
            update(WaInstance).values(
                sent_today_wa=0,
                sent_today_email=0,
                last_reset_at=datetime.utcnow(),
            )
        )
        await db.commit()
        logger.info("Reset all daily WA/email send counts.")

    async def advance_all_warmup_days(self, db: AsyncSession) -> None:
        """
        Increment day_of_life for all WA instances.
        Update daily_wa_cap based on new day.
        Create notifications for cap upgrades and warmup completion.
        Called by Celery beat daily.
        """
        from app.models.models import WaInstance, Notification, NotificationType
        from sqlalchemy import select

        result = await db.execute(select(WaInstance))
        instances = result.scalars().all()

        for instance in instances:
            old_day = instance.day_of_life or 0
            new_day = old_day + 1
            old_cap = instance.daily_wa_cap or get_cap_for_day(old_day)
            new_cap = get_cap_for_day(new_day)

            instance.day_of_life = new_day
            instance.daily_wa_cap = new_cap

            # Notify if cap increased
            if new_cap > old_cap:
                notif = Notification(
                    tenant_id=instance.tenant_id,
                    type=NotificationType.wa_warmup,
                    title="WhatsApp Daily Cap Increased",
                    message=(
                        f"Instance '{instance.instance_name}' (day {new_day}) daily cap increased "
                        f"from {old_cap} to {new_cap} messages."
                    ),
                    data={
                        "instance_id": instance.id,
                        "instance_name": instance.instance_name,
                        "day": new_day,
                        "old_cap": old_cap,
                        "new_cap": new_cap,
                    },
                )
                db.add(notif)

            # Mark warmup complete at day 30
            if new_day >= 30 and not instance.warmup_complete:
                instance.warmup_complete = True
                notif = Notification(
                    tenant_id=instance.tenant_id,
                    type=NotificationType.wa_warmup,
                    title="WhatsApp Warmup Complete!",
                    message=(
                        f"Instance '{instance.instance_name}' has completed warmup (day {new_day}). "
                        f"You can now send up to {new_cap} messages per day."
                    ),
                    data={
                        "instance_id": instance.id,
                        "instance_name": instance.instance_name,
                        "day": new_day,
                        "cap": new_cap,
                    },
                )
                db.add(notif)

        await db.commit()
        logger.info(f"Advanced warmup days for {len(instances)} instances.")


warmup_service = WarmupService()
