"""LLM routing for the agents — Groq (real-time) + OpenRouter (reasoning/batch).

Three routes, each with its own fallback chain:
  realtime → Groq realtime model → fast route
  fast     → OpenRouter fast (only if OPENROUTER_ENABLED) → Groq batch models
  reason   → OpenRouter reasoning (only if OPENROUTER_ENABLED) → Groq batch models
Batch routes never fall back to the realtime model — that quota is reserved for live replies.

Every call is attributed to the agent that made it: per-agent overrides (AI_AGENT_OVERRIDES)
pick the route/model/max_tokens, and token usage is counted per agent and model in Redis.
"""
import json
import logging
import re
from datetime import datetime, timezone

from groq import AsyncGroq
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

ROUTES = ("realtime", "fast", "reason")
USAGE_KEY = "qualifay:ai:usage:{day}"  # hash: "{agent}|{model}" → total tokens
USAGE_TTL = 8 * 86400


def agent_overrides() -> dict:
    """Parsed AI_AGENT_OVERRIDES; a malformed value is logged and ignored, never fatal."""
    raw = (settings.AI_AGENT_OVERRIDES or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except ValueError:
        logger.error("AI_AGENT_OVERRIDES is not valid JSON — ignoring it")
        return {}


async def record_usage(agent: str, model: str, tokens: int) -> None:
    """Best-effort per-agent token counter. A short-lived connection per call keeps it safe
    across Celery's per-task event loops; any Redis error is swallowed."""
    if not tokens:
        return
    try:
        import redis.asyncio as aioredis
        key = USAGE_KEY.format(day=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        async with aioredis.from_url(settings.REDIS_URL, socket_timeout=1,
                                     socket_connect_timeout=1) as r:
            await r.hincrby(key, f"{agent}|{model}", int(tokens))
            await r.expire(key, USAGE_TTL)
    except Exception as e:
        logger.debug(f"AI usage tracking skipped: {e}")


async def usage_for_day(day: str) -> dict:
    """{agent: {model: tokens}} for one UTC day (YYYY-MM-DD)."""
    import redis.asyncio as aioredis
    async with aioredis.from_url(settings.REDIS_URL, decode_responses=True) as r:
        raw = await r.hgetall(USAGE_KEY.format(day=day))
    out: dict = {}
    for field, tokens in raw.items():
        agent, _, model = field.partition("|")
        out.setdefault(agent, {})[model] = int(tokens)
    return out


class LLMRouter:
    def __init__(self):
        self.reset()

    def reset(self):
        """(Re)create the SDK clients. Their underlying httpx connections bind to the
        current event loop on first use, so Celery workers must call this at the start
        of each task's fresh loop to avoid "Future attached to a different loop" errors."""
        self.groq = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.openrouter = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://qualifay.io",
                "X-Title": "Qualifay",
            },
        )

    async def complete(self, route: str, messages: list, max_tokens: int,
                       agent: str = "", model: str = "") -> str:
        """Run one completion on `route` for `agent`. `model` (from an override) replaces the
        route's primary model; the fallback chain is unchanged. Returns "" if all fail."""
        if route == "realtime":
            return await self._realtime(messages, max_tokens, agent, model)
        if route == "reason":
            return await self._openrouter_then_batch(
                messages, max_tokens, agent, model or settings.OPENROUTER_MODEL_REASONING, model)
        return await self._openrouter_then_batch(
            messages, max_tokens, agent, model or settings.OPENROUTER_MODEL_FAST, model)

    async def _create(self, client, model, messages, max_tokens, agent) -> str:
        resp = await client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, temperature=0.3,
        )
        usage = getattr(resp, "usage", None)
        await record_usage(agent or "unknown", model, getattr(usage, "total_tokens", 0) or 0)
        return (resp.choices[0].message.content or "").strip()

    async def _realtime(self, messages, max_tokens, agent, model) -> str:
        """Groq realtime, falling back to the fast route on error."""
        model = model or settings.GROQ_MODEL_REALTIME
        try:
            return await self._create(self.groq, model, messages, max_tokens, agent)
        except Exception as e:
            logger.warning(f"[{agent}] Groq {model} failed: {e} — falling back to fast route")
            return await self.complete("fast", messages, max_tokens, agent)

    async def _openrouter_then_batch(self, messages, max_tokens, agent, or_model, override) -> str:
        """OpenRouter first when enabled; otherwise (or on failure) the Groq batch models.
        Without OpenRouter, an override model is tried first on Groq."""
        if settings.OPENROUTER_ENABLED:
            try:
                return await self._create(self.openrouter, or_model, messages, max_tokens, agent)
            except Exception as e:
                logger.warning(f"[{agent}] OpenRouter {or_model} failed: {e} — falling back to Groq")
            override = ""
        return await self.groq_batch(messages, max_tokens, agent, first=override)

    async def groq_batch(self, messages, max_tokens, agent="", first="") -> str:
        """Background path: try each batch model in turn (each has its own free quota).
        Never falls back to the realtime model — that quota is reserved for live replies."""
        models = [m.strip() for m in settings.GROQ_BATCH_MODELS.split(",") if m.strip()]
        if first:
            models = [first] + [m for m in models if m != first]
        for model in models:
            try:
                text = await self._create(self.groq, model, messages, max(max_tokens, 1024), agent)
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"[{agent}] Groq batch model {model} failed: {e}")
        return ""


def parse_json(text: str, fallback):
    """Parse JSON from LLM response, stripping markdown fences. Returns fallback on failure."""
    if not text:
        return fallback
    try:
        cleaned = text.strip()
        # Strip markdown code fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        # Find first { or [
        start = min(
            (cleaned.find("{") if "{" in cleaned else len(cleaned)),
            (cleaned.find("[") if "[" in cleaned else len(cleaned)),
        )
        if start < len(cleaned):
            cleaned = cleaned[start:]
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"JSON parse failed: {e} | text={text[:200]}")
        return fallback


# One router (one pair of SDK clients) per process, shared by every agent.
router = LLMRouter()
