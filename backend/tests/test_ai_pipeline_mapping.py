"""AI → pipeline mapping: score clamping, stage normalization, and the conversation
analysis parse/fallback path."""
import pytest

from app.workers.ai_tasks import clamp_score, normalize_stage, VALID_WA_STAGES


@pytest.mark.parametrize("value,expected", [
    (150, 100),      # above range clamps to 100
    (-5, 0),         # negative clamps to 0
    (50, 50),        # in range unchanged
    ("80", 80),      # numeric string coerced
    (99.9, 99),      # float truncated
    (None, 0),       # missing -> 0
    ("abc", 0),      # garbage -> 0
    (0, 0),
    (100, 100),
])
def test_clamp_score(value, expected):
    assert clamp_score(value) == expected


def test_normalize_stage_accepts_all_valid():
    for stage in VALID_WA_STAGES:
        assert normalize_stage(stage) == stage


@pytest.mark.parametrize("bad", ["", "unknown", "NEW", None, 123, "archived"])
def test_normalize_stage_defaults_to_replied(bad):
    # 'archived'/'new' are real LeadStages but not valid outcomes for an engaged WA chat.
    assert normalize_stage(bad) == "replied"


@pytest.mark.asyncio
async def test_analyze_conversation_parses_valid_json(monkeypatch):
    from app.services.ai_service import AIService
    svc = AIService()

    async def fake_groq(messages, max_tokens=300):
        return ('{"is_lead": true, "intent": "pricing", "score": 85, '
                '"stage": "qualifying", "reason": "asked for price"}')

    monkeypatch.setattr(svc, "_groq", fake_groq)
    out = await svc.analyze_conversation_for_pipeline(
        [{"direction": "inbound", "content": "how much is it?"}], "Ali"
    )
    assert out["is_lead"] is True
    assert out["intent"] == "pricing"
    assert out["score"] == 85
    assert out["stage"] == "qualifying"


@pytest.mark.asyncio
async def test_analyze_conversation_strips_markdown_fence(monkeypatch):
    from app.services.ai_service import AIService
    svc = AIService()

    async def fake_groq(messages, max_tokens=300):
        return '```json\n{"is_lead": true, "intent": "booking", "score": 70, "stage": "meeting", "reason": "x"}\n```'

    monkeypatch.setattr(svc, "_groq", fake_groq)
    out = await svc.analyze_conversation_for_pipeline([{"direction": "inbound", "content": "book me"}], "")
    assert out["is_lead"] is True
    assert out["stage"] == "meeting"


@pytest.mark.asyncio
async def test_analyze_conversation_falls_back_on_bad_json(monkeypatch):
    from app.services.ai_service import AIService
    svc = AIService()

    async def fake_groq(messages, max_tokens=300):
        return "sorry, I cannot help with that"

    monkeypatch.setattr(svc, "_groq", fake_groq)
    out = await svc.analyze_conversation_for_pipeline([{"direction": "inbound", "content": "hi"}], "")
    # Safe fallback: not a lead, defaults present.
    assert out["is_lead"] is False
    assert out["stage"] == "replied"
    assert out["score"] == 0


@pytest.mark.asyncio
async def test_analyze_then_clamp_and_normalize_end_to_end(monkeypatch):
    """A hostile/garbage LLM response must not produce an out-of-range score or bad stage
    once run through the task's clamp + normalize helpers."""
    from app.services.ai_service import AIService
    svc = AIService()

    async def fake_groq(messages, max_tokens=300):
        return '{"is_lead": true, "intent": "x", "score": 9999, "stage": "TOTALLY_BOGUS", "reason": "y"}'

    monkeypatch.setattr(svc, "_groq", fake_groq)
    out = await svc.analyze_conversation_for_pipeline([{"direction": "inbound", "content": "?"}], "")
    assert clamp_score(out["score"]) == 100
    assert normalize_stage(out["stage"]) == "replied"
