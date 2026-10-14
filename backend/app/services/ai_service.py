"""
AI Service — facade over the agents in backend/agents/.

Each agent (BANT scoring, intent, WhatsApp replies, AIDA copy, ...) lives in its own module
with its own prompt, and routes its LLM calls through agents.llm under its own name, so the
model, fallbacks and token tracking are configurable per agent (AI_AGENT_OVERRIDES). This
class keeps the original method names so callers don't change: ai_service.score_bant(...)
runs the BANTScorer agent.
"""
import logging

from agents import AGENT_METHODS
from agents.base_agent import BaseAgent, _lang_instruction  # noqa: F401 — re-exported
from agents.llm import parse_json, router

logger = logging.getLogger(__name__)


class _AdHoc(BaseAgent):
    """Attribution for one-off prompts that aren't a named agent (e.g. Site Factory)."""
    name = "adhoc"


class AIService:
    def __init__(self, llm=None):
        self.llm = llm or router
        self.agents = {method: cls(self.llm) for method, cls in AGENT_METHODS.items()}
        self._adhoc = _AdHoc(self.llm)

    def __getattr__(self, method):
        # Only reached for names not defined on the class: public agent methods.
        agents = self.__dict__.get("agents") or {}
        if method in agents:
            return agents[method].run
        raise AttributeError(method)

    def agent(self, method: str) -> BaseAgent:
        return self.agents[method]

    def reset(self):
        """Recreate the SDK clients for the current event loop (see LLMRouter.reset)."""
        self.llm.reset()

    # Ad-hoc prompts used outside the named agents.
    async def _or_fast(self, messages: list, max_tokens: int = 512) -> str:
        return await self._adhoc._or_fast(messages, max_tokens)

    def _parse_json(self, text: str, fallback):
        return parse_json(text, fallback)


def tenant_context_str(profile: dict) -> str:
    """Condense a tenant's onboarding profile into a short brand brief that is injected
    into outreach/reply copy so every message sounds like THIS business, not a generic bot."""
    if not profile:
        return ""
    fields = [
        ("business_name", "Business"), ("industry", "Industry"), ("sells", "Sells"),
        ("value_prop", "Why customers choose us"), ("ideal_customer", "Ideal customer"),
        ("tone", "Preferred tone"), ("price_range", "Price range"), ("cities", "Target markets"),
    ]
    parts = []
    for key, label in fields:
        val = profile.get(key)
        if val:
            parts.append(f"{label}: {val}")
    return "\n".join(parts)

# Singleton
ai_service = AIService()
