from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings


class Base(DeclarativeBase):
    pass


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
]

# Enum values added to native PG enums after they were first created. create_all()
# never alters an existing enum type, so new members are applied idempotently on
# startup (PG12+ supports ADD VALUE IF NOT EXISTS). Keep append-only.
_ENSURE_ENUM_VALUES = [
    ("notificationtype", "missed_followup"),
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, col, coltype in _ENSURE_COLUMNS:
            await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}'))
        for enum_name, value in _ENSURE_ENUM_VALUES:
            await conn.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'"))
