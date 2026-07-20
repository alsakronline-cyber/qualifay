"""Team management — invite teammates (email link + copyable fallback), set roles, remove."""
import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.database import get_db
from app.core.config import settings
from app.api.auth import (
    get_current_user, pwd_context, require_admin as _require_admin, create_invite_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _u(u) -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "role": "admin" if u.is_tenant_admin else "agent",
        "is_tenant_admin": u.is_tenant_admin,
        "status": getattr(u, "status", "active"),   # 'invited' = hasn't accepted yet
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


class InviteIn(BaseModel):
    email: EmailStr
    full_name: Optional[str] = ""
    is_admin: bool = False


class UpdateIn(BaseModel):
    full_name: Optional[str] = None
    is_admin: Optional[bool] = None


async def _send_invite(db, tenant_id, user, email):
    """Build the accept link, email it (best-effort), and return (url, email_sent)."""
    token = create_invite_token(user.id, tenant_id)
    url = f"{settings.app_base_url_effective}/accept-invite?token={token}"
    from app.models.models import Tenant
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    company = tenant.name if tenant else "Qualifay"
    sent = False
    try:
        from app.services.email_service import send_for_tenant
        body_text = (
            f"تمت دعوتك للانضمام إلى فريق «{company}» على Qualifay.\n\n"
            f"اضغط الرابط التالي لتعيين كلمة المرور وتفعيل حسابك (صالح لمدة 7 أيام):\n{url}\n\n"
            f"إن لم تكن تتوقع هذه الدعوة، تجاهل هذه الرسالة."
        )
        await send_for_tenant(db, tenant_id, email, f"دعوة للانضمام إلى {company} على Qualifay", body_text)
        sent = True
    except Exception as e:
        logger.warning("invite email to %s failed (link still available): %s", email, e)
    return url, sent


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
    """Invite a teammate: creates a pending (invited) account with NO usable password,
    emails them an accept link, and returns a copyable link fallback for the admin."""
    _require_admin(current_user)
    from app.models.models import User
    email = str(body.email).strip().lower()
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already in use")
    u = User(
        tenant_id=current_user["tenant_id"], email=email, full_name=(body.full_name or ""),
        # No real password until they accept — random unguessable placeholder so the row
        # is valid; 'invited' status also blocks login until acceptance.
        hashed_password=pwd_context.hash(secrets.token_urlsafe(32)),
        is_admin=False, is_tenant_admin=body.is_admin, status="invited",
    )
    db.add(u)
    await db.flush()
    url, sent = await _send_invite(db, current_user["tenant_id"], u, email)
    await db.commit()
    await db.refresh(u)
    return {**_u(u), "invite_url": url, "email_sent": sent}


@router.post("/{uid}/resend")
async def resend_invite(uid: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Re-issue the invite link for a still-pending member (email + copyable fallback)."""
    _require_admin(current_user)
    u = await _get_member(uid, current_user["tenant_id"], db)
    if getattr(u, "status", "active") != "invited":
        raise HTTPException(status_code=400, detail="This member has already joined")
    url, sent = await _send_invite(db, current_user["tenant_id"], u, u.email)
    return {"invite_url": url, "email_sent": sent}


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
