"""Team management — invite teammates, set roles (admin/agent), remove."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.database import get_db
from app.api.auth import get_current_user, pwd_context

router = APIRouter()


def _require_admin(current_user: dict):
    if not current_user.get("is_tenant_admin"):
        raise HTTPException(status_code=403, detail="Admins only")


def _u(u) -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "role": "admin" if u.is_tenant_admin else "agent",
        "is_tenant_admin": u.is_tenant_admin,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


class InviteIn(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    is_admin: bool = False


class UpdateIn(BaseModel):
    full_name: Optional[str] = None
    is_admin: Optional[bool] = None


@router.get("")
@router.get("/")
async def list_team(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.models import User
    rows = (await db.execute(
        select(User).where(User.tenant_id == current_user["tenant_id"]).order_by(User.created_at)
    )).scalars().all()
    return [_u(u) for u in rows]


@router.post("/invite")
async def invite(body: InviteIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    from app.models.models import User
    if (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already in use")
    u = User(
        tenant_id=current_user["tenant_id"], email=body.email, full_name=body.full_name,
        hashed_password=pwd_context.hash(body.password),
        is_admin=False, is_tenant_admin=body.is_admin,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return _u(u)


async def _get_member(uid, tenant_id, db):
    from app.models.models import User
    u = (await db.execute(select(User).where(and_(User.id == uid, User.tenant_id == tenant_id)))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return u


@router.patch("/{uid}")
async def update_member(uid: str, body: UpdateIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    from app.models.models import User
    u = await _get_member(uid, current_user["tenant_id"], db)
    if body.full_name is not None:
        u.full_name = body.full_name
    if body.is_admin is not None:
        # Don't allow demoting the last admin.
        if not body.is_admin and u.is_tenant_admin:
            admins = (await db.execute(select(func.count(User.id)).where(and_(
                User.tenant_id == current_user["tenant_id"], User.is_tenant_admin == True  # noqa: E712
            )))).scalar() or 0
            if admins <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last admin")
        u.is_tenant_admin = body.is_admin
    await db.commit()
    return _u(u)


@router.delete("/{uid}")
async def remove_member(uid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    if uid == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="You can't remove yourself")
    u = await _get_member(uid, current_user["tenant_id"], db)
    await db.delete(u)
    await db.commit()
    return {"deleted": True}
