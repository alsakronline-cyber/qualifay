"""Shared Celery event-loop entrypoint.

Each Celery task runs synchronously, so we spin a fresh asyncio loop per call and dispose
the shared async DB engine first: pooled asyncpg connections are bound to whichever loop
opened them, and reusing one across loops raises "Future attached to a different loop".

`reset_ai=True` additionally rebuilds the AI SDK clients so their httpx pools bind to the
current loop — needed only in workers that call the AI service (previously this line had
drifted into just two of the copied helpers).

Note: workers that manage their own event loop for a specific reason (Playwright subprocess
transport in scrape_tasks/tasks) intentionally do NOT use this and keep their local loop
handling.
"""
import asyncio


def run_async(coro, reset_ai: bool = False):
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        if reset_ai:
            # Rebuild AI SDK clients so their httpx pools bind to THIS loop, not a closed one.
            try:
                from app.services.ai_service import ai_service
                ai_service.reset()
            except Exception:
                pass
        return await coro
    return asyncio.run(_wrapped())
