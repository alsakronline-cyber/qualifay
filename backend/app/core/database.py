import logging
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from app.core.config import settings

logger = logging.getLogger(__name__)

# Celery workers run each task in a fresh event loop (asyncio.run per task). A pooled
# asyncpg connection is bound to the loop that opened it, so reusing the pool across
# tasks raises "Future attached to a different loop" / "Event loop is closed". Give the
# worker process a non-pooling engine (a connection is opened and closed within each
# task's own loop); the FastAPI web process keeps its normal pool.
_IS_WORKER = any("celery" in str(a) for a in sys.argv)


class Base(DeclarativeBase):
    pass


if _IS_WORKER:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,   # no cross-loop connection reuse in Celery tasks
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Additive columns that were introduced after their tables already existed in
# production. create_all() only creates missing TABLES, never adds columns to an
# existing one, so these are applied idempotently on every startup (Postgres
# ADD COLUMN IF NOT EXISTS). Keep this list append-only.
_ENSURE_COLUMNS = [
    ("campaigns", "sequence_id", "VARCHAR"),
    ("campaigns", "audience_filter", "JSON"),
    ("campaigns", "instance_ids", "JSON"),
    ("campaigns", "auto_enroll", "BOOLEAN DEFAULT false"),
    ("sequence_enrollments", "campaign_id", "VARCHAR"),
    # Added mid-session to pre-existing tables; missing on the production DB (its
    # tables predate these features), which silently broke email routing/warmup there.
    ("conversations", "channel", "VARCHAR DEFAULT 'whatsapp'"),
    ("conversations", "last_message_at", "TIMESTAMP"),
    ("messages", "attachments", "JSON"),
    ("tenants", "email_started_at", "TIMESTAMP"),
    ("tenants", "tenant_profile", "JSON"),
    ("tenants", "autonomy", "VARCHAR DEFAULT 'copilot'"),
    ("tenants", "onboarding_done", "BOOLEAN DEFAULT false"),
    ("users", "status", "VARCHAR DEFAULT 'active'"),
    ("tenants", "status", "VARCHAR DEFAULT 'active'"),
    ("leads", "verified_real", "BOOLEAN"),
    ("tenants", "ai_language", "VARCHAR DEFAULT 'ar'"),
    ("sales_docs", "payment_terms", "TEXT"),
    ("tenants", "scraper_keys_enc", "TEXT"),
    ("wa_instances", "wa_cap_override", "INTEGER"),
]

# Enum values added to native PG enums after they were first created. create_all()
# never alters an existing enum type, so new members are applied idempotently on
# startup (PG12+ supports ADD VALUE IF NOT EXISTS). Keep append-only.
_ENSURE_ENUM_VALUES = [
    ("notificationtype", "missed_followup"),
    ("leadsource", "inbound_email"),
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Cap lock waits so a stuck session can never hang boot indefinitely (one once did,
        # holding locks and bricking every restart). Fail-fast → visible crash-loop instead.
        await conn.execute(text("SET lock_timeout = '10s'"))
        for table, col, coltype in _ENSURE_COLUMNS:
            await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}'))
    # Enum ADD VALUE must run OUTSIDE a transaction block (Postgres won't let a new enum
    # label be added and used within the same tx), so use an autocommit connection.
    # Best-effort per value: a lock/timeout here degrades one feature, it must not brick boot.
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("SET lock_timeout = '10s'"))
        for enum_name, value in _ENSURE_ENUM_VALUES:
            try:
                await conn.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'"))
            except Exception as e:
                logger.warning("enum ensure failed (%s += %s): %s", enum_name, value, e)
