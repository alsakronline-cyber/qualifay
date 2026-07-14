"""Agent activity feed — the transparent record of what the autonomous orchestrator
did for this tenant. This is the 'what did my AI do today' view."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import get_current_user

router = APIRouter()


def _run(r) -> dict:
    return {
        "id": r.id, "kind": r.kind, "status": r.status, "summary": r.summary,
        "actions": r.actions or [], "metrics": r.metrics or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
@router.get("/")
async def list_runs(limit: int = 50, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import AgentRun
    rows = (await db.execute(
        select(AgentRun).where(AgentRun.tenant_id == current_user["tenant_id"])
        .order_by(desc(AgentRun.created_at)).limit(min(limit, 200))
    )).scalars().all()
    return {"items": [_run(r) for r in rows]}


@router.post("/run-now")
async def run_now(current_user: dict = Depends(get_current_user)):
    """Trigger an orchestrator cycle immediately (so the owner can see it work on demand)."""
    from app.workers.orchestrator_tasks import run_orchestrator
    task = run_orchestrator.apply_async(queue="default")
    return {"queued": True, "task_id": task.id}


@router.get("/memory")
async def list_memory(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """What the system has learned about this tenant's market — the adaptive memory."""
    from sqlalchemy import desc
    from app.models.models import TenantMemory
    rows = (await db.execute(
        select(TenantMemory).where(and_(
            TenantMemory.tenant_id == current_user["tenant_id"], TenantMemory.weight > 0))
        .order_by(desc(TenantMemory.weight), desc(TenantMemory.updated_at)).limit(50)
    )).scalars().all()
    return {"items": [{"id": m.id, "kind": m.kind, "content": m.content, "weight": m.weight,
                       "created_at": m.created_at.isoformat() if m.created_at else None} for m in rows]}
