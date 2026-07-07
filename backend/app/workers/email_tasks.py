"""Celery Email Tasks — inbound reply polling (IMAP)."""
import asyncio
import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        return await coro
    return asyncio.run(_wrapped())


@celery_app.task(name="poll_inbound_email", queue="default")
def poll_inbound_email():
    """Beat-scheduled: fetch new email replies and thread them into the CRM inbox."""
    from app.services.email_inbox_service import poll_inbound_email as _poll
    return run_async(_poll())
