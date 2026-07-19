"""Boundary tests for the WhatsApp daily-cap check — the gate that stops a burst-send
from getting the number banned. Uses a tiny fake async session so no DB is required.
"""
import asyncio
from types import SimpleNamespace

from app.services.warmup_service import warmup_service


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    """Minimal stand-in for AsyncSession: returns a fixed instance, records add/commit."""
    def __init__(self, instance):
        self._instance = instance
        self.added = []
        self.committed = False

    async def execute(self, *_a, **_k):
        return _Result(self._instance)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _instance(sent, cap, paused=False):
    return SimpleNamespace(
        id="i1", tenant_id="t1", instance_name="alsakr",
        sent_today_wa=sent, daily_wa_cap=cap, day_of_life=3, paused=paused,
    )


def _check(instance):
    db = _FakeDB(instance)
    result = asyncio.run(warmup_service.check_wa_limit("i1", db))
    return result, db


def test_under_cap_allows_send():
    (allowed, used, cap), db = _check(_instance(sent=5, cap=10))
    assert allowed is True
    assert (used, cap) == (5, 10)
    assert db.added == []  # no limit notification when under cap


def test_at_cap_blocks_and_notifies():
    (allowed, used, cap), db = _check(_instance(sent=10, cap=10))
    assert allowed is False
    assert (used, cap) == (10, 10)
    assert len(db.added) == 1  # a wa_limit notification was raised


def test_over_cap_blocks():
    (allowed, _u, _c), _db = _check(_instance(sent=15, cap=10))
    assert allowed is False


def test_paused_instance_blocks_even_under_cap():
    (allowed, _u, _c), db = _check(_instance(sent=1, cap=10, paused=True))
    assert allowed is False
    assert db.added == []  # paused is a soft block, not a cap notification


def test_missing_instance_blocks():
    db = _FakeDB(None)
    allowed, used, cap = asyncio.run(warmup_service.check_wa_limit("nope", db))
    assert (allowed, used, cap) == (False, 0, 0)
