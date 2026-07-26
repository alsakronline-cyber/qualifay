"""
Auth API — JWT authentication, tenant registration, user management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.config import settings
from app.models.models import User, Tenant, Subscription, Plan

import logging

router = APIRouter()
logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ALGORITHM = "HS256"


# ─── Schemas ──────────────────────────────────────────────────

class RegisterTenantRequest(BaseModel):
    tenant_name: str
    tenant_slug: Optional[str] = None   # auto-derived from the company name if omitted
    email: str
    phone: Optional[str] = None
    password: str
    full_name: str
    language: str = "ar"


class RefreshRequest(BaseModel):
    refresh_token: str


class AcceptInviteRequest(BaseModel):
    token: str
    full_name: str
    password: str


# ─── Helpers ──────────────────────────────────────────────────

def create_access_token(data: dict, expires_minutes: int = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode({**data, "exp": expire, "type": "access"}, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(days=30)
    return jwt.encode({**data, "exp": expire, "type": "refresh"}, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_invite_token(user_id: str, tenant_id: str, days: int = 7) -> str:
    """Signed, self-expiring team-invite token — no separate table needed. Single-use in
    effect: acceptance flips the user to 'active', after which the token is rejected."""
    expire = datetime.utcnow() + timedelta(days=days)
    return jwt.encode(
        {"sub": user_id, "tenant_id": tenant_id, "type": "invite", "exp": expire},
        settings.SECRET_KEY, algorithm=ALGORITHM,
    )


def _decode_invite_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "invite":
        raise JWTError("not an invite token")
    return payload


def create_verify_token(user_id: str, tenant_id: str, hours: int = 48) -> str:
    """Signed email-verification token for a new signup (48h)."""
    expire = datetime.utcnow() + timedelta(hours=hours)
    return jwt.encode(
        {"sub": user_id, "tenant_id": tenant_id, "type": "verify", "exp": expire},
        settings.SECRET_KEY, algorithm=ALGORITHM,
    )


def _decode_verify_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "verify":
        raise JWTError("not a verify token")
    return payload


async def _send_verification(db, user, base_url: str) -> bool:
    """Email the signup verification link. Best-effort — returns whether it sent."""
    token = create_verify_token(user.id, user.tenant_id)
    url = f"{base_url}/verify-email?token={token}"
    body = (
        f"مرحباً {user.full_name or ''}،\n\n"
        f"لتفعيل حسابك على Qualifay، اضغط الرابط التالي (صالح 48 ساعة):\n{url}\n\n"
        f"إن لم تكن قد سجّلت، تجاهل هذه الرسالة."
    )
    try:
        from app.services.email_service import send_system
        await send_system(db, user.email, "فعّل حسابك على Qualifay", body)
        return True
    except Exception as e:
        logger.warning("verification email to %s failed: %s", user.email, e)
        return False


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dependency: decode JWT and return user info dict."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Only access tokens authenticate API calls — a refresh token (30-day lifetime)
        # must not be usable as a bearer on protected routes.
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        tenant_id: str = payload.get("tenant_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception

    return {
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "is_tenant_admin": user.is_tenant_admin,
        "language": user.language,
    }


import re as _re


def _slugify(text: str) -> str:
    """A URL-safe slug from a company name. Arabic/other scripts collapse to '-', so we
    fall back to a generic base when nothing ASCII-usable remains."""
    s = _re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40] or "tenant"


async def _unique_tenant_slug(db: AsyncSession, base_text: str) -> str:
    base = _slugify(base_text)
    slug, n = base, 1
    while (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{base}-{n}"
    return slug


def require_admin(current_user: dict) -> None:
    """Raise 403 unless the caller is a tenant admin. Shared by admin-only endpoints."""
    if not current_user.get("is_tenant_admin"):
        raise HTTPException(status_code=403, detail="Admins only")


async def require_admin_dep(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency form — attach to admin-only endpoints so a non-admin (agent)
    can't perform the action even by calling the API directly (defense in depth beyond
    the UI hiding the page)."""
    require_admin(current_user)
    return current_user


async def get_tenant_user(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dependency: verify user belongs to an active tenant."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this account")

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant not found")

    return current_user


# ─── Routes ───────────────────────────────────────────────────

@router.post("/login")
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with email OR phone + password → access + refresh tokens."""
    identifier = form.username.strip()
    result = await db.execute(select(User).where(User.email == identifier))
    user = result.scalar_one_or_none()
    if not user:
        # Not an email match — try as a phone number (normalized to E.164).
        from app.lib.phone import normalize_egyptian_phone
        normalized = normalize_egyptian_phone(identifier)
        if normalized:
            result = await db.execute(select(User).where(User.phone == normalized))
            user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Block accounts that aren't active yet, with the right next step.
    st = getattr(user, "status", "active")
    if st == "unverified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لم يتم تفعيل بريدك بعد — افتح رابط التفعيل من بريدك، أو اطلب إعادة الإرسال.",
        )
    if st != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لم يتم تفعيل الحساب بعد — افتح رابط الدعوة من بريدك لتعيين كلمة المرور.",
        )

    token_data = {
        "sub": user.id,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "is_admin": user.is_admin,
        "is_tenant_admin": user.is_tenant_admin,
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": user.id, "tenant_id": user.tenant_id})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "tenant_id": user.tenant_id,
            "is_admin": user.is_admin,
            "is_tenant_admin": user.is_tenant_admin,
            "language": user.language,
        },
    }


class TokenBody(BaseModel):
    token: str


class EmailBody(BaseModel):
    email: EmailStr


@router.post("/verify-email")
async def verify_email(body: TokenBody, db: AsyncSession = Depends(get_db)):
    """Confirm a new signup's email → activate the account and log them in."""
    try:
        payload = _decode_verify_token(body.token)
    except JWTError:
        raise HTTPException(status_code=400, detail="رابط التفعيل غير صالح أو منتهي")
    user = (await db.execute(select(User).where(User.id == payload.get("sub")))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="رابط التفعيل غير صالح")
    if getattr(user, "status", "active") == "unverified":
        user.status = "active"
        await db.commit()
        await db.refresh(user)
    # Idempotent: if already active, still issue a session.
    token_data = {"sub": user.id, "email": user.email, "tenant_id": user.tenant_id,
                  "is_admin": user.is_admin, "is_tenant_admin": user.is_tenant_admin}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token({"sub": user.id, "tenant_id": user.tenant_id}),
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name,
                 "tenant_id": user.tenant_id, "is_tenant_admin": user.is_tenant_admin},
    }


@router.post("/resend-verification")
async def resend_verification(body: EmailBody, db: AsyncSession = Depends(get_db)):
    """Resend the signup verification email. Always returns success (no account enumeration)."""
    user = (await db.execute(
        select(User).where(User.email == str(body.email).strip().lower())
    )).scalar_one_or_none()
    if user and getattr(user, "status", "active") == "unverified":
        await _send_verification(db, user, settings.app_base_url_effective)
    return {"ok": True, "message": "إن كان الحساب بحاجة لتفعيل، أرسلنا رابطاً جديداً إلى بريدك."}


@router.get("/invite/{token}")
async def get_invite(token: str, db: AsyncSession = Depends(get_db)):
    """Public: validate an invite token and return who/what it's for, so the accept page
    can greet the invitee. Does not reveal anything on an invalid/expired/used token."""
    try:
        payload = _decode_invite_token(token)
    except JWTError:
        raise HTTPException(status_code=400, detail="رابط الدعوة غير صالح أو منتهي")
    user = (await db.execute(select(User).where(User.id == payload.get("sub")))).scalar_one_or_none()
    if not user or getattr(user, "status", "active") != "invited":
        raise HTTPException(status_code=400, detail="انتهت صلاحية الدعوة أو تم استخدامها")
    tenant = (await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))).scalar_one_or_none()
    return {
        "email": user.email,
        "full_name": user.full_name or "",
        "company": tenant.name if tenant else "",
        "role": "admin" if user.is_tenant_admin else "agent",
    }


@router.post("/accept-invite")
async def accept_invite(body: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    """Public: the invitee sets their own name + password, activating the account. Then
    they're auto-logged-in. Acceptance is single-use — status flips to 'active'."""
    try:
        payload = _decode_invite_token(body.token)
    except JWTError:
        raise HTTPException(status_code=400, detail="رابط الدعوة غير صالح أو منتهي")
    if len(body.password or "") < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")
    user = (await db.execute(select(User).where(User.id == payload.get("sub")))).scalar_one_or_none()
    if not user or getattr(user, "status", "active") != "invited":
        raise HTTPException(status_code=400, detail="انتهت صلاحية الدعوة أو تم استخدامها")

    user.full_name = body.full_name.strip() or user.full_name
    user.hashed_password = pwd_context.hash(body.password)
    user.status = "active"
    await db.commit()
    await db.refresh(user)

    token_data = {
        "sub": user.id, "email": user.email, "tenant_id": user.tenant_id,
        "is_admin": user.is_admin, "is_tenant_admin": user.is_tenant_admin,
    }
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token({"sub": user.id, "tenant_id": user.tenant_id}),
        "token_type": "bearer",
        "user": {
            "id": user.id, "email": user.email, "full_name": user.full_name,
            "tenant_id": user.tenant_id, "is_admin": user.is_admin,
            "is_tenant_admin": user.is_tenant_admin, "language": user.language,
        },
    }


@router.post("/register-tenant")
async def register_tenant(
    body: RegisterTenantRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new tenant with an admin user.
    Creates: Tenant, User (tenant_admin), Subscription (trial 30 days).
    """
    # Check email uniqueness
    email_result = await db.execute(select(User).where(User.email == body.email))
    if email_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(body.password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Slug: use the given one, else derive from the company name; ensure it's unique by
    # appending -2, -3… on collision, so the user never has to invent one.
    slug = await _unique_tenant_slug(db, body.tenant_slug or body.tenant_name)

    # Normalize + check phone uniqueness (optional field)
    phone = None
    if body.phone:
        from app.lib.phone import normalize_egyptian_phone
        phone = normalize_egyptian_phone(body.phone)
        if not phone:
            raise HTTPException(status_code=400, detail="Invalid phone number")
        phone_result = await db.execute(select(User).where(User.phone == phone))
        if phone_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone number already registered")

    trial_end = datetime.utcnow() + timedelta(days=30)

    tenant = Tenant(
        slug=slug,
        name=body.tenant_name,
        plan=Plan.trial,
        language=body.language,
        trial_ends_at=trial_end,
    )
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        phone=phone,
        full_name=body.full_name,
        hashed_password=pwd_context.hash(body.password),
        is_admin=False,
        is_tenant_admin=True,
        language=body.language,
        status="unverified",   # must confirm email before first login
    )
    db.add(user)

    subscription = Subscription(
        tenant_id=tenant.id,
        plan=Plan.trial,
        status="trial",
        currency="EGP",
        current_period_end=trial_end,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(user)

    # Email the verification link (no auto-login until confirmed).
    sent = await _send_verification(db, user, settings.app_base_url_effective)

    return {
        "verification_required": True,
        "email_sent": sent,
        "email": user.email,
        "message": "تحقّق من بريدك لتفعيل الحساب" if sent
                   else "تم إنشاء الحساب، لكن تعذّر إرسال بريد التفعيل — استخدم «إعادة الإرسال».",
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info from JWT."""
    return current_user


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange refresh token for new access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = jwt.decode(body.refresh_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise credentials_exception
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception

    token_data = {
        "sub": user.id,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "is_admin": user.is_admin,
        "is_tenant_admin": user.is_tenant_admin,
    }
    return {
        "access_token": create_access_token(token_data),
        "token_type": "bearer",
    }
