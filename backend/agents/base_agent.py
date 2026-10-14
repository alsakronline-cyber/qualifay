"""BaseAgent — every AI agent extends this.

An agent owns its prompt and output shape; the LLM call goes through `agents.llm.router`
under the agent's name, so its route, model and max_tokens can be overridden per agent
(AI_AGENT_OVERRIDES) and its token usage is tracked separately.
"""
from agents.llm import ROUTES, agent_overrides, parse_json, router


class BaseAgent:
    name = "base"

    def __init__(self, llm=None):
        self.llm = llm or router

    def config(self) -> dict:
        return agent_overrides().get(self.name, {}) or {}

    async def _call(self, route: str, messages: list, max_tokens: int) -> str:
        cfg = self.config()
        if cfg.get("route") in ROUTES:
            route = cfg["route"]
        if isinstance(cfg.get("max_tokens"), int) and cfg["max_tokens"] > 0:
            max_tokens = cfg["max_tokens"]
        return await self.llm.complete(route, messages, max_tokens,
                                       agent=self.name, model=cfg.get("model") or "")

    # Default routes, named after the provider path each agent was written against.
    async def _groq(self, messages: list, max_tokens: int = 512) -> str:
        return await self._call("realtime", messages, max_tokens)

    async def _or_fast(self, messages: list, max_tokens: int = 512) -> str:
        return await self._call("fast", messages, max_tokens)

    async def _or_reason(self, messages: list, max_tokens: int = 1024) -> str:
        return await self._call("reason", messages, max_tokens)

    def _parse_json(self, text: str, fallback):
        return parse_json(text, fallback)


def _lang_instruction(language: str) -> str:
    """The one place that defines how each output-language choice is phrased to the model.
    ar = formal simplified Arabic · en = English · masri = Egyptian colloquial (عامية مصرية)."""
    if language == "en":
        return "Write in professional English."
    if language == "masri":
        return "اكتب بالعامية المصرية الدارجة (اللهجة المصرية) بأسلوب ودّي واحترافي، وليس بالفصحى."
    return "اكتب بالعربية الفصحى المبسّطة المناسبة للأعمال في مصر."
