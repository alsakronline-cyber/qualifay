"""Adaptive memory — store, reinforce, and retrieve the per-tenant lessons the agents
learn. Kept deliberately simple (structured facts in Postgres, reinforced by recurrence)
so it needs no embeddings/API key and is fully reliable. Injected into agent context."""
import logging

from sqlalchemy import select, desc, and_

logger = logging.getLogger(__name__)

MAX_PER_TENANT = 60      # keep the top lessons; prune the long tail
CONTEXT_LIMIT = 6        # how many lessons to inject into a message's context


def _words(s: str) -> set:
    return {w for w in (s or "").lower().split() if len(w) > 2}


def _similar(a: str, b: str) -> bool:
    """Cheap overlap check so the same lesson reinforces instead of duplicating."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    return inter / max(1, min(len(wa), len(wb))) >= 0.5


async def remember(db, tenant_id: str, kind: str, content: str, source_lead_id: str = None):
    """Insert a new lesson or reinforce an existing similar one (weight++)."""
    from app.models.models import TenantMemory
    content = (content or "").strip()
    if not content:
        return
    existing = (await db.execute(select(TenantMemory).where(and_(
        TenantMemory.tenant_id == tenant_id, TenantMemory.kind == kind
    )))).scalars().all()
    for m in existing:
        if _similar(m.content, content):
            m.weight = (m.weight or 1) + 1
            return
    db.add(TenantMemory(tenant_id=tenant_id, kind=kind, content=content, source_lead_id=source_lead_id))


async def tenant_memory_str(db, tenant_id: str, limit: int = CONTEXT_LIMIT) -> str:
    """Top lessons as a short brief for injection into writer/responder context."""
    from app.models.models import TenantMemory
    rows = (await db.execute(
        select(TenantMemory).where(TenantMemory.tenant_id == tenant_id)
        .order_by(desc(TenantMemory.weight), desc(TenantMemory.updated_at)).limit(limit)
    )).scalars().all()
    if not rows:
        return ""
    label = {"win_reason": "يكسب العملاء", "loss_reason": "يخسر العملاء",
             "objection": "اعتراض شائع", "insight": "ملاحظة"}
    return "ما تعلّمناه من تجارب سابقة:\n" + "\n".join(
        f"- ({label.get(m.kind, m.kind)}) {m.content}" for m in rows)


async def prune(db, tenant_id: str):
    from app.models.models import TenantMemory
    rows = (await db.execute(
        select(TenantMemory).where(TenantMemory.tenant_id == tenant_id)
        .order_by(desc(TenantMemory.weight), desc(TenantMemory.updated_at))
    )).scalars().all()
    for m in rows[MAX_PER_TENANT:]:
        await db.delete(m)
