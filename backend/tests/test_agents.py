"""Per-agent routing: every AI agent goes through BaseAgent under its own name, and
AI_AGENT_OVERRIDES can change one agent's route / model / max_tokens without touching others."""
import pytest

from agents import AGENT_METHODS
from agents.base_agent import BaseAgent
from app.core.config import settings
from app.services.ai_service import AIService


class FakeRouter:
    def __init__(self, reply=""):
        self.reply, self.calls = reply, []

    async def complete(self, route, messages, max_tokens, agent="", model=""):
        self.calls.append({"route": route, "max_tokens": max_tokens, "agent": agent, "model": model})
        return self.reply

    def reset(self):
        pass


def test_every_agent_has_a_unique_name_and_a_run_method():
    names = [cls.name for cls in AGENT_METHODS.values()]
    assert len(names) == len(set(names))
    for method, cls in AGENT_METHODS.items():
        assert issubclass(cls, BaseAgent) and cls.name != "base"
        assert getattr(cls, method) is cls.run


def test_facade_keeps_the_old_method_names():
    svc = AIService(FakeRouter())
    for method in AGENT_METHODS:
        assert callable(getattr(svc, method))
    with pytest.raises(AttributeError):
        svc.not_an_agent


async def test_calls_are_attributed_to_the_agent_on_its_default_route(monkeypatch):
    monkeypatch.setattr(settings, "AI_AGENT_OVERRIDES", "")
    fake = FakeRouter('{"score": 70, "reason": "fit"}')
    svc = AIService(fake)
    out = await svc.score_bant({"company": "X"})
    assert out["score"] == 70
    assert fake.calls == [{"route": "reason", "max_tokens": fake.calls[0]["max_tokens"],
                           "agent": "bant_scorer", "model": ""}]
    await svc.classify_intent("hello")
    assert fake.calls[-1]["agent"] == "intent_classifier" and fake.calls[-1]["route"] == "realtime"


async def test_override_changes_only_that_agent(monkeypatch):
    monkeypatch.setattr(settings, "AI_AGENT_OVERRIDES",
                        '{"bant_scorer": {"route": "realtime", "model": "m-x", "max_tokens": 77}}')
    fake = FakeRouter("{}")
    svc = AIService(fake)
    await svc.score_bant({"company": "X"})
    await svc.quality_gate({"company": "X"})
    bant, gate = fake.calls
    assert (bant["route"], bant["model"], bant["max_tokens"]) == ("realtime", "m-x", 77)
    assert (gate["route"], gate["model"]) == ("fast", "")


async def test_malformed_overrides_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "AI_AGENT_OVERRIDES", "{not json")
    fake = FakeRouter("{}")
    await AIService(fake).quality_gate({"company": "X"})
    assert fake.calls[0]["route"] == "fast"


async def test_router_realtime_falls_back_to_batch_models(monkeypatch):
    """Groq realtime failing must fall through to the batch models, never raise."""
    from agents import llm as llm_mod

    class Boom:
        def __init__(self, fail_models):
            self.fail_models, self.seen = fail_models, []
            self.chat = self
            self.completions = self

        async def create(self, model, **kw):
            self.seen.append(model)
            if model in self.fail_models:
                raise RuntimeError("429")
            msg = type("M", (), {"content": "ok"})
            choice = type("C", (), {"message": msg})
            return type("R", (), {"choices": [choice], "usage": None})

    monkeypatch.setattr(settings, "OPENROUTER_ENABLED", False)
    monkeypatch.setattr(settings, "GROQ_MODEL_REALTIME", "rt")
    monkeypatch.setattr(settings, "GROQ_BATCH_MODELS", "b1,b2")
    r = llm_mod.LLMRouter()
    r.groq = Boom({"rt", "b1"})
    assert await r.complete("realtime", [], 10, agent="t") == "ok"
    assert r.groq.seen == ["rt", "b1", "b2"]
