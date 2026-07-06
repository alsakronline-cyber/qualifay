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

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ALGORITHM = "HS256"


# ─── Schemas ──────────────────────────────────────────────────

class RegisterTenantRequest(BaseModel):
    tenant_name: str
    tenant_slug: str
    email: str
    phone: Optional[str] = None
    password: str
    full_name: str
    language: str = "ar"


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Helpers ──────────────────────────────────────────────────

def create_access_token(data: dict, expires_minutes: int = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode({**data, "exp": expire, "type": "access"}, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(days=30)
    return jwt.encode({**data, "exp": expire, "type": "refresh"}, settings.SECRET_KEY, algorithm=ALGORITHM)


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

    # Check slug uniqueness
    slug_result = await db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug))
    if slug_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tenant slug already taken")

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
        slug=body.tenant_slug,
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

    token_data = {
        "sub": user.id,
        "email": user.email,
        "tenant_id": tenant.id,
        "is_admin": False,
        "is_tenant_admin": True,
    }

    return {
        "message": "Tenant registered successfully",
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token({"sub": user.id, "tenant_id": tenant.id}),
        "token_type": "bearer",
        "tenant": {
            "id": tenant.id,
            "slug": tenant.slug,
            "name": tenant.name,
            "plan": tenant.plan.value,
            "trial_ends_at": trial_end.isoformat(),
        },
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
        },
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
