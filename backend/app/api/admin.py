"""Platform-owner console API — cross-tenant management. EVERY route is gated by
require_platform_admin (is_admin). These deliberately bypass tenant scoping, so the gate
is the only thing standing between one tenant and everyone else's data — keep it on."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import require_platform_admin, pwd_context

logger = logging.getLogger(__name__)
# Gate the whole router: no endpoint here is reachable without is_admin.
router = APIRouter(dependencies=[Depends(require_platform_admin)])


async def log_admin(db, actor, action, target_type=None, target_id=None, target_label=None, detail=None):
    """Record an owner action to the audit trail. Caller commits."""
    from app.models.models import AdminAudit
    db.add(AdminAudit(
        actor_user_id=actor.get("user_id"), actor_email=actor.get("email"),
        action=action, target_type=target_type, target_id=target_id,
        target_label=target_label, detail=detail or {},
    ))


# ─── Overview ─────────────────────────────────────────────────
@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    from app.models.models import (
        Tenant, User, Lead, Message, MessageDirection, Plan,
    )
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    soon = now + timedelta(days=7)

    async def scalar(q):
        return (await db.execute(q)).scalar() or 0

    tenants = await scalar(select(func.count(Tenant.id)))
    users = await scalar(select(func.count(User.id)))
    leads = await scalar(select(func.count(Lead.id)))
    msgs_24h = await scalar(select(func.count(Message.id)).where(Message.created_at >= since))
    sent_24h = await scalar(select(func.count(Message.id)).where(and_(
        Message.direction == MessageDirection.outbound, Message.created_at >= since)))
    trials = await scalar(select(func.count(Tenant.id)).where(Tenant.plan == Plan.trial))
    expiring = await scalar(select(func.count(Tenant.id)).where(and_(
        Tenant.plan == Plan.trial, Tenant.trial_ends_at.isnot(None),
        Tenant.trial_ends_at <= soon, Tenant.trial_ends_at >= now)))
    suspended = await scalar(select(func.count(Tenant.id)).where(Tenant.status == "suspended"))
    unverified = await scalar(select(func.count(User.id)).where(User.status == "unverified"))

    return {
        "tenants": tenants, "users": users, "leads": leads,
        "messages_24h": msgs_24h, "sent_24h": sent_24h,
        "active_trials": trials, "trials_expiring_7d": expiring,
        "suspended_tenants": suspended, "unverified_users": unverified,
    }


# ─── Tenants (companies) ──────────────────────────────────────
def _tenant_dict(t, user_count=0, lead_count=0) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "plan": t.plan.value if t.plan else None,
        "status": getattr(t, "status", "active"),
        "autonomy": t.autonomy, "onboarding_done": bool(t.onboarding_done),
        "trial_ends_at": t.trial_ends_at.isoformat() if t.trial_ends_at else None,
        "created_at": t.created_at.isoformat() if getattr(t, "created_at", None) else None,
        "users": user_count, "leads": lead_count,
    }


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    from app.models.models import Tenant, User, Lead
    tenants = (await db.execute(select(Tenant))).scalars().all()
    uc = dict((await db.execute(
        select(User.tenant_id, func.count(User.id)).group_by(User.tenant_id))).all())
    lc = dict((await db.execute(
        select(Lead.tenant_id, func.count(Lead.id)).group_by(Lead.tenant_id))).all())
    rows = [_tenant_dict(t, uc.get(t.id, 0), lc.get(t.id, 0)) for t in tenants]
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows


class TenantUpdate(BaseModel):
    plan: Optional[str] = None
    status: Optional[str] = None            # active | suspended
    extend_trial_days: Optional[int] = None  # add N days to the trial
    autonomy: Optional[str] = None


async def _get_tenant(tid, db):
    from app.models.models import Tenant
    t = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t


@router.patch("/tenants/{tid}")
async def update_tenant(tid: str, body: TenantUpdate, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    from app.models.models import Plan
    t = await _get_tenant(tid, db)
    if body.plan is not None:
        try:
            t.plan = Plan(body.plan)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid plan: {body.plan}")
    if body.status is not None:
        if body.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="status must be active|suspended")
        t.status = body.status
    if body.autonomy is not None:
        t.autonomy = body.autonomy
    if body.extend_trial_days is not None:
        base = t.trial_ends_at if (t.trial_ends_at and t.trial_ends_at > datetime.utcnow()) else datetime.utcnow()
        t.trial_ends_at = base + timedelta(days=int(body.extend_trial_days))
    await log_admin(db, current, "tenant.update", "tenant", t.id, t.name,
                    body.model_dump(exclude_none=True))
    await db.commit()
    return _tenant_dict(t)


# Ordered cascade for a full tenant wipe. Children before parents (from the live FK
# graph). lead_pool is SHARED across tenants, so we null this tenant's contribution
# rather than delete pool rows other tenants may reference.
_TENANT_WIPE = [
    "UPDATE lead_pool SET contributed_by = NULL WHERE contributed_by = :tid",
    "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE tenant_id = :tid)",
    "DELETE FROM flow_submissions WHERE tenant_id = :tid",
    "DELETE FROM sequence_steps WHERE sequence_id IN (SELECT id FROM sequences WHERE tenant_id = :tid)",
    "DELETE FROM sequence_enrollments WHERE tenant_id = :tid",
    "DELETE FROM ab_variants WHERE test_id IN (SELECT id FROM ab_tests WHERE tenant_id = :tid)",
    "DELETE FROM consent_logs WHERE tenant_id = :tid",
    "DELETE FROM conversations WHERE tenant_id = :tid",
    "DELETE FROM campaigns WHERE tenant_id = :tid",
    "DELETE FROM sequences WHERE tenant_id = :tid",
    "DELETE FROM conversion_flows WHERE tenant_id = :tid",
    "DELETE FROM message_templates WHERE tenant_id = :tid",
    "DELETE FROM leads WHERE tenant_id = :tid",
    "DELETE FROM wa_instances WHERE tenant_id = :tid",
    "DELETE FROM ab_tests WHERE tenant_id = :tid",
    "DELETE FROM agent_runs WHERE tenant_id = :tid",
    "DELETE FROM agent_tasks WHERE tenant_id = :tid",
    "DELETE FROM email_accounts WHERE tenant_id = :tid",
    "DELETE FROM notifications WHERE tenant_id = :tid",
    "DELETE FROM scrape_jobs WHERE tenant_id = :tid",
    "DELETE FROM scrape_schedules WHERE tenant_id = :tid",
    "DELETE FROM subscriptions WHERE tenant_id = :tid",
    "DELETE FROM tenant_memories WHERE tenant_id = :tid",
    "DELETE FROM webhook_endpoints WHERE tenant_id = :tid",
    "DELETE FROM activity_logs WHERE tenant_id = :tid",
    "DELETE FROM users WHERE tenant_id = :tid",
    "DELETE FROM tenants WHERE id = :tid",
]


@router.delete("/tenants/{tid}")
async def delete_tenant(tid: str, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    """HARD-delete a company and ALL its data (irreversible). Ordered FK-safe cascade.
    Guarded: you can't delete your own tenant (self-lockout)."""
    from sqlalchemy import text
    if tid == current["tenant_id"]:
        raise HTTPException(status_code=400, detail="You can't delete your own company")
    t = await _get_tenant(tid, db)
    name = t.name
    # Audit BEFORE the wipe (the tenant row is about to vanish).
    await log_admin(db, current, "tenant.delete", "tenant", tid, name)
    for stmt in _TENANT_WIPE:
        await db.execute(text(stmt), {"tid": tid})
    await db.commit()
    logger.warning("platform admin %s hard-deleted tenant %s (%s)", current.get("email"), tid, name)
    return {"deleted": True, "company": name}


# ─── Users (accounts, all tenants) ────────────────────────────
def _user_dict(u, tenant_name="") -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "tenant_id": u.tenant_id, "company": tenant_name,
        "is_admin": u.is_admin, "is_tenant_admin": u.is_tenant_admin,
        "role": "platform" if u.is_admin else ("admin" if u.is_tenant_admin else "agent"),
        "status": getattr(u, "status", "active"),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/users")
async def list_users(
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import User, Tenant
    q = select(User)
    if search:
        term = f"%{search.strip()}%"
        q = q.where(func.lower(User.email).like(func.lower(term)) |
                    func.lower(User.full_name).like(func.lower(term)))
    users = (await db.execute(q.order_by(User.created_at.desc()).limit(limit))).scalars().all()
    names = dict((await db.execute(select(Tenant.id, Tenant.name))).all())
    return [_user_dict(u, names.get(u.tenant_id, "")) for u in users]


class UserUpdate(BaseModel):
    status: Optional[str] = None          # active | suspended | (unverified→active via 'active')
    is_tenant_admin: Optional[bool] = None
    is_admin: Optional[bool] = None       # grant/revoke PLATFORM admin


class PasswordBody(BaseModel):
    password: str


async def _get_user(uid, db):
    from app.models.models import User
    u = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u


async def _last_admin_guard(db, tenant_id, exclude_uid):
    from app.models.models import User
    n = (await db.execute(select(func.count(User.id)).where(and_(
        User.tenant_id == tenant_id, User.is_tenant_admin == True, User.id != exclude_uid  # noqa: E712
    )))).scalar() or 0
    if n == 0:
        raise HTTPException(status_code=400, detail="Can't remove/suspend the last admin of a company")


@router.patch("/users/{uid}")
async def update_user(uid: str, body: UserUpdate, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user(uid, db)
    if body.status is not None:
        if body.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="status must be active|suspended")
        if body.status == "suspended" and u.is_tenant_admin:
            await _last_admin_guard(db, u.tenant_id, u.id)
        u.status = body.status
    if body.is_tenant_admin is not None:
        if body.is_tenant_admin is False and u.is_tenant_admin:
            await _last_admin_guard(db, u.tenant_id, u.id)
        u.is_tenant_admin = body.is_tenant_admin
    if body.is_admin is not None:
        if u.id == current["user_id"] and body.is_admin is False:
            raise HTTPException(status_code=400, detail="You can't revoke your own platform admin")
        u.is_admin = body.is_admin
    await log_admin(db, current, "user.update", "user", u.id, u.email, body.model_dump(exclude_none=True))
    await db.commit()
    return _user_dict(u)


@router.post("/users/{uid}/set-password")
async def set_user_password(uid: str, body: PasswordBody, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user(uid, db)
    if len(body.password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    u.hashed_password = pwd_context.hash(body.password)
    if getattr(u, "status", "active") == "unverified":
        u.status = "active"   # setting a password for them also activates
    await log_admin(db, current, "user.set_password", "user", u.id, u.email)
    await db.commit()
    return {"ok": True}


@router.delete("/users/{uid}")
async def delete_user(uid: str, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    from app.models.models import User, Lead, Notification
    if uid == current["user_id"]:
        raise HTTPException(status_code=400, detail="You can't delete yourself")
    u = await _get_user(uid, db)
    if u.is_tenant_admin:
        await _last_admin_guard(db, u.tenant_id, u.id)
    # Clear the two FK references before deleting the row.
    await db.execute(update(Lead).where(Lead.assigned_to == uid).values(assigned_to=None))
    await db.execute(delete(Notification).where(Notification.user_id == uid))
    await log_admin(db, current, "user.delete", "user", u.id, u.email)
    await db.delete(u)
    await db.commit()
    return {"deleted": True}


# ─── System health (Phase 2) ──────────────────────────────────
@router.get("/system")
async def system_health(db: AsyncSession = Depends(get_db)):
    """Platform health snapshot: core dependencies + last backup + disk."""
    from sqlalchemy import text
    from app.core.config import settings
    out: dict = {}

    # Database — if we can run this, it's up.
    try:
        await db.execute(text("SELECT 1"))
        out["database"] = "ok"
    except Exception:
        out["database"] = "error"

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        out["redis"] = "ok"
    except Exception as e:
        out["redis"] = f"down: {str(e)[:60]}"

    # Evolution API (WhatsApp gateway)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=6) as c:
            resp = await c.get(f"{settings.EVOLUTION_API_URL}/")
        out["evolution_api"] = "ok" if resp.status_code < 500 else f"http {resp.status_code}"
    except Exception as e:
        out["evolution_api"] = f"down: {str(e)[:60]}"

    # Last backup (from the MinIO 'backups' bucket)
    try:
        from minio import Minio
        ep = settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        client = Minio(ep, access_key=settings.MINIO_USER, secret_key=settings.MINIO_PASSWORD,
                       secure=settings.MINIO_ENDPOINT.startswith("https"))
        if client.bucket_exists("backups"):
            objs = list(client.list_objects("backups"))
            if objs:
                latest = max(objs, key=lambda o: o.last_modified)
                out["last_backup"] = {
                    "file": latest.object_name,
                    "at": latest.last_modified.isoformat() if latest.last_modified else None,
                    "size_kb": round((latest.size or 0) / 1024, 1),
                    "count": len(objs),
                }
            else:
                out["last_backup"] = None
        else:
            out["last_backup"] = None
    except Exception as e:
        out["last_backup"] = {"error": str(e)[:60]}

    # Disk
    try:
        import shutil
        du = shutil.disk_usage("/")
        out["disk"] = {"used_gb": round(du.used / 1e9, 1), "total_gb": round(du.total / 1e9, 1),
                       "pct": round(du.used / du.total * 100)}
    except Exception:
        out["disk"] = None

    return out


# ─── Platform-wide WhatsApp instances (Phase 2) ───────────────
@router.get("/instances")
async def all_instances(db: AsyncSession = Depends(get_db)):
    from app.models.models import WaInstance, Tenant
    rows = (await db.execute(select(WaInstance).order_by(WaInstance.tenant_id))).scalars().all()
    names = dict((await db.execute(select(Tenant.id, Tenant.name))).all())
    return [{
        "id": i.id, "instance_name": i.instance_name,
        "company": names.get(i.tenant_id, ""),
        "status": i.status, "day_of_life": i.day_of_life,
        "daily_wa_cap": i.daily_wa_cap, "sent_today_wa": i.sent_today_wa,
        "sent_today_email": i.sent_today_email,
    } for i in rows]


# ─── Plan / revenue snapshot (Phase 2) ────────────────────────
@router.get("/plans")
async def plan_breakdown(db: AsyncSession = Depends(get_db)):
    from app.models.models import Tenant
    rows = (await db.execute(
        select(Tenant.plan, func.count(Tenant.id)).group_by(Tenant.plan))).all()
    breakdown = {(p.value if p else "unknown"): n for p, n in rows}
    paying = sum(n for p, n in breakdown.items() if p not in ("trial", "unknown"))
    return {"by_plan": breakdown, "paying_tenants": paying, "trial_tenants": breakdown.get("trial", 0)}


# ─── Editable plan limits + feature flags ─────────────────────
@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db)):
    from app.services.platform_config import get_platform_config, DEFAULT_CONFIG
    return {"config": await get_platform_config(db), "defaults": DEFAULT_CONFIG}


class ConfigBody(BaseModel):
    data: dict


@router.put("/config")
async def put_config(body: ConfigBody, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    from app.models.models import PlatformSettings
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == "singleton"))).scalar_one_or_none()
    if not row:
        row = PlatformSettings(id="singleton", data=body.data or {})
        db.add(row)
    else:
        row.data = body.data or {}
    await log_admin(db, current, "config.update", "config", "singleton", None, body.data)
    await db.commit()
    from app.services.platform_config import get_platform_config
    return {"config": await get_platform_config(db)}


# ─── Audit log (Phase 3) ──────────────────────────────────────
@router.get("/audit")
async def audit_log(limit: int = Query(default=100, le=500), db: AsyncSession = Depends(get_db)):
    from app.models.models import AdminAudit
    rows = (await db.execute(
        select(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(limit))).scalars().all()
    return [{
        "id": a.id, "actor_email": a.actor_email, "action": a.action,
        "target_type": a.target_type, "target_label": a.target_label,
        "detail": a.detail, "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in rows]


# ─── Impersonation (Phase 3) ──────────────────────────────────
@router.post("/tenants/{tid}/impersonate")
async def impersonate_tenant(tid: str, current=Depends(require_platform_admin), db: AsyncSession = Depends(get_db)):
    """Issue a short-lived (60-min) session as a tenant's admin, for support. The token
    carries an 'imp_by' marker; the owner keeps their own token to return."""
    from app.models.models import User
    from app.api.auth import create_access_token
    t = await _get_tenant(tid, db)
    target = (await db.execute(select(User).where(and_(
        User.tenant_id == tid, User.is_tenant_admin == True, User.status == "active"  # noqa: E712
    )).order_by(User.created_at))).scalars().first()
    if not target:
        raise HTTPException(status_code=400, detail="No active admin on this company to impersonate")
    token = create_access_token({
        "sub": target.id, "email": target.email, "tenant_id": target.tenant_id,
        "is_admin": False,   # act strictly as the tenant admin, not as platform owner
        "is_tenant_admin": target.is_tenant_admin, "imp_by": current["user_id"],
    }, expires_minutes=60)
    await log_admin(db, current, "impersonate", "tenant", t.id, t.name, {"as_user": target.email})
    await db.commit()
    return {"access_token": token, "company": t.name, "as_email": target.email}
