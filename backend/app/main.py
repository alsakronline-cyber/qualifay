"""
Qualifay B2B Lead Generation SaaS — FastAPI Application
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, AsyncSessionLocal
from app.api.router import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Qualifay backend...")
    await init_db()
    await _seed_admin()
    logger.info("Qualifay backend ready.")
    yield
    logger.info("Shutting down...")


async def _seed_admin():
    """Create default super-admin user and tenant if not exists."""
    from app.models.models import User, Tenant, Subscription, Plan
    from passlib.context import CryptContext
    from sqlalchemy import select
    from datetime import datetime, timedelta

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == settings.DEFAULT_ADMIN_EMAIL)
        )
        if result.scalar_one_or_none():
            return  # Already seeded

        tenant = Tenant(
            slug="qualifay-admin",
            name="Qualifay Admin",
            plan=Plan.agency,
            language="ar",
        )
        db.add(tenant)
        await db.flush()

        user = User(
            tenant_id=tenant.id,
            email=settings.DEFAULT_ADMIN_EMAIL,
            full_name="Admin",
            hashed_password=pwd.hash(settings.DEFAULT_ADMIN_PASSWORD),
            is_admin=True,
            is_tenant_admin=True,
            language="ar",
        )
        sub = Subscription(
            tenant_id=tenant.id,
            plan=Plan.agency,
            status="active",
            currency="USD",
            current_period_end=datetime.utcnow() + timedelta(days=3650),
        )
        db.add(user)
        db.add(sub)
        await db.commit()
        logger.info(f"Admin user seeded: {settings.DEFAULT_ADMIN_EMAIL}")


app = FastAPI(
    title="Qualifay API",
    description="B2B Lead Generation SaaS — AI-powered BANT scoring, WhatsApp outreach, shared lead pool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_effective,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "qualifay-backend",
        "version": "1.0.0",
    }
