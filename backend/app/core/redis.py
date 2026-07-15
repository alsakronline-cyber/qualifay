"""Shared async Redis client. The Evolution webhook caches the freshly-generated QR
here (short TTL) and the instances QR endpoint reads it back — the QR is delivered
asynchronously by Evolution, so Redis is the handoff between the two."""
import redis.asyncio as aioredis

from app.core.config import settings

_redis = None


async def get_redis():
    """Process-wide async Redis client (decoded strings)."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis
