"""System monitoring — a health snapshot of the moving parts (DB, Redis, Evolution API,
Celery broker) plus backup status and an on-demand backup trigger for admins."""
import logging
import shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


async def _check_db(db: AsyncSession):
    try:
        await db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _check_redis():
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _check_evolution():
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as c:
            resp = await c.get(f"{settings.EVOLUTION_API_URL}/")
        return {"ok": resp.status_code < 500, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _check_celery():
    try:
        from app.workers.celery_app import celery_app
        pong = celery_app.control.ping(timeout=3)
        return {"ok": bool(pong), "workers": len(pong or [])}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _disk():
    try:
        total, used, free = shutil.disk_usage("/app")
        return {"free_gb": round(free / 1e9, 1), "total_gb": round(total / 1e9, 1),
                "used_pct": round(used / total * 100, 1)}
    except Exception:
        return None


@router.get("/health")
async def health(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.workers.backup_tasks import latest_backup_info
    checks = {
        "database": await _check_db(db),
        "redis": _check_redis(),
        "evolution_api": await _check_evolution(),
        "celery": _check_celery(),
    }
    overall = all(c.get("ok") for c in checks.values())
    return {
        "healthy": overall,
        "services": checks,
        "disk": _disk(),
        "last_backup": latest_backup_info(),
    }


@router.get("/backups")
async def backups(current_user: dict = Depends(get_current_user)):
    from app.workers.backup_tasks import latest_backup_info
    return {"last_backup": latest_backup_info()}


@router.post("/backups/run")
async def trigger_backup(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_tenant_admin"):
        raise HTTPException(status_code=403, detail="Admins only")
    from app.workers.backup_tasks import run_backup
    task = run_backup.apply_async(queue="default")
    return {"queued": True, "task_id": task.id}
