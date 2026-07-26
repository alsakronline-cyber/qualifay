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
async def update_tenant(tid: str, body: TenantUpdate, db: AsyncSession = Depends(get_db)):
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
    await db.commit()
    return _tenant_dict(t)


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
    await db.commit()
    return _user_dict(u)


@router.post("/users/{uid}/set-password")
async def set_user_password(uid: str, body: PasswordBody, db: AsyncSession = Depends(get_db)):
    u = await _get_user(uid, db)
    if len(body.password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    u.hashed_password = pwd_context.hash(body.password)
    if getattr(u, "status", "active") == "unverified":
        u.status = "active"   # setting a password for them also activates
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
    await db.delete(u)
    await db.commit()
    return {"deleted": True}
