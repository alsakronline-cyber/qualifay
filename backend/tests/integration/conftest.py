"""Integration tests: the real FastAPI app, real Postgres (migrated with Alembic) and real
Redis. Only the outside world is stubbed — LLM calls, WhatsApp (Evolution) sends and Celery
dispatch — so these exercise routes, auth, tenant isolation, the DB schema and the worker
pipeline as they actually run.

They are destructive (every table is truncated between tests), so they only run when
RUN_INTEGRATION=1 and DATABASE_URL names a database whose name contains "test":

    RUN_INTEGRATION=1 DATABASE_URL=postgresql+asyncpg://.../qualifay_test pytest tests/integration
"""
import json
import os
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.engine import make_url


def _enabled() -> bool:
    if os.environ.get("RUN_INTEGRATION") != "1":
        return False
    db = make_url(os.environ.get("DATABASE_URL", "")).database or ""
    if "test" not in db:
        raise RuntimeError(f"Refusing to run destructive integration tests against database {db!r}")
    return True


def pytest_collection_modifyitems(config, items):
    if _enabled():
        return
    skip = pytest.mark.skip(reason="integration tests need RUN_INTEGRATION=1 and a *test* DATABASE_URL")
    for item in items:
        if "tests/integration" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db():
    """Rebuild the schema from scratch through the real migration chain, once per run."""
    from alembic import command
    from app.core.database import _alembic_config
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
async def clean_db(migrated_db):
    """Each test gets empty tables and an engine bound to its own event loop."""
    from sqlalchemy import text
    from app.core.database import engine
    from app.models.models import Base
    await engine.dispose()
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield
    await engine.dispose()


@pytest.fixture
async def db():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    import httpx
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Stubs for the outside world ──────────────────────────────────────────────

class LLMStub:
    """Replaces every agent's LLM call. Responses are keyed by agent name; each agent's real
    prompt building and JSON parsing still run. Unknown agents get "" (their fallbacks)."""

    def __init__(self):
        self.responses: dict = {}
        self.calls: list = []

    def set(self, agent: str, value):
        self.responses[agent] = value if isinstance(value, str) else json.dumps(value)

    async def __call__(self, agent_self, route, messages, max_tokens):
        self.calls.append((agent_self.name, route))
        return self.responses.get(agent_self.name, "")


class WhatsAppStub:
    def __init__(self):
        self.sent: list = []

    async def send_text(self, instance_name, jid, text, *a, **kw):
        self.sent.append({"instance": instance_name, "jid": jid, "text": text})
        return {"key": {"id": f"out-{len(self.sent)}"}}

    async def send_typing(self, *a, **kw):
        return None


class CeleryStub:
    """Records task dispatches instead of sending them to a broker."""

    def __init__(self):
        self.dispatched: list = []

    def names(self):
        return [d["task"] for d in self.dispatched]

    def args_for(self, task_suffix):
        return [d["args"] for d in self.dispatched if d["task"].endswith(task_suffix)]


@pytest.fixture
def llm(monkeypatch):
    from agents.base_agent import BaseAgent
    stub = LLMStub()

    async def fake_call(self, route, messages, max_tokens):
        return await stub(self, route, messages, max_tokens)

    monkeypatch.setattr(BaseAgent, "_call", fake_call)
    return stub


@pytest.fixture
def whatsapp(monkeypatch):
    from app.services.evolution_service import EvolutionService
    stub = WhatsAppStub()
    monkeypatch.setattr(EvolutionService, "send_text", lambda self, *a, **kw: stub.send_text(*a, **kw))
    monkeypatch.setattr(EvolutionService, "send_typing", lambda self, *a, **kw: stub.send_typing(*a, **kw))
    return stub


@pytest.fixture
def celery(monkeypatch):
    from celery.app.task import Task
    stub = CeleryStub()

    class _Result:
        id = "stub-task"

    def apply_async(self, args=None, kwargs=None, **options):
        stub.dispatched.append({"task": self.name, "args": list(args or []), "kwargs": kwargs or {}})
        return _Result()

    def delay(self, *args, **kwargs):
        return apply_async(self, args, kwargs)

    monkeypatch.setattr(Task, "apply_async", apply_async)
    monkeypatch.setattr(Task, "delay", delay)
    return stub


# ── Data factories ───────────────────────────────────────────────────────────

@pytest.fixture
def make_tenant(db):
    async def _make(name="Acme", **kw):
        from app.models.models import Plan, Tenant, User
        from app.api.auth import create_access_token, pwd_context
        tenant = Tenant(slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", name=name,
                        plan=kw.pop("plan", Plan.growth), language="ar",
                        tenant_profile=kw.pop("tenant_profile", {"business_name": name, "sells": "ERP software"}),
                        **kw)
        db.add(tenant)
        await db.flush()
        user = User(tenant_id=tenant.id, email=f"owner-{uuid.uuid4().hex[:6]}@{name.lower()}.test",
                    full_name=f"{name} Owner", hashed_password=pwd_context.hash("password123"),
                    is_tenant_admin=True, status="active")
        db.add(user)
        await db.commit()
        token = create_access_token({"sub": user.id, "tenant_id": tenant.id, "email": user.email,
                                     "is_admin": False, "is_tenant_admin": True})
        return tenant, user, {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture
def make_lead(db):
    async def _make(tenant, **kw):
        from app.models.models import Lead, LeadSource, LeadStage
        fields = dict(tenant_id=tenant.id, source=LeadSource.google_maps, name="Mona Adel",
                      company="Nile Builders", industry="Construction", city="Cairo",
                      phone="+201001234567", website="https://nilebuilders.example",
                      stage=LeadStage.new, language="ar")
        fields.update(kw)
        lead = Lead(**fields)
        db.add(lead)
        await db.commit()
        return lead
    return _make


@pytest.fixture
def make_instance(db):
    async def _make(tenant, **kw):
        from app.models.models import WaInstance
        fields = dict(tenant_id=tenant.id, instance_name=f"inst-{uuid.uuid4().hex[:8]}",
                      status="open", day_of_life=40, daily_wa_cap=200, sent_today_wa=0,
                      last_reset_at=datetime.utcnow(), created_at=datetime.utcnow() - timedelta(days=40))
        fields.update(kw)
        inst = WaInstance(**fields)
        db.add(inst)
        await db.commit()
        return inst
    return _make


def evolution_message(instance_name, phone_digits, text, msg_id=None, push_name="Mona"):
    """An Evolution API `messages.upsert` webhook payload for an inbound text."""
    return {
        "event": "messages.upsert",
        "instance": instance_name,
        "data": {
            "key": {"remoteJid": f"{phone_digits}@s.whatsapp.net", "fromMe": False,
                    "id": msg_id or uuid.uuid4().hex},
            "pushName": push_name,
            "message": {"conversation": text},
            "messageTimestamp": int(datetime.utcnow().timestamp()),
        },
    }
