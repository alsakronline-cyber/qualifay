import logging
import sys
from pathlib import Path

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


# ─── Schema ──────────────────────────────────────────────────
# The schema is owned by Alembic (backend/alembic/versions). It is migrated once per deploy,
# before uvicorn starts (`alembic upgrade head` in the backend command), never from inside
# the running app: boot-time create_all()/ALTER TABLE queued behind live workers' locks and
# crash-looped deploys. New columns/tables → `alembic revision --autogenerate -m "..."`.

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config():
    from alembic.config import Config
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def migrate_to_head() -> None:
    """Run `alembic upgrade head` (sync). For scripts and one-off setup, not app startup."""
    from alembic import command
    command.upgrade(_alembic_config(), "head")


async def init_db():
    """Bring the database to the latest schema (for setup scripts). Runs Alembic in a
    worker thread because its env.py drives its own sync engine."""
    import asyncio
    await asyncio.to_thread(migrate_to_head)


async def check_schema() -> bool:
    """Read-only: is the database at the Alembic head? Logged loudly if not — the app still
    starts (it may be mid-deploy), but a behind schema means `alembic upgrade head` was skipped."""
    from alembic.script import ScriptDirectory
    heads = set(ScriptDirectory.from_config(_alembic_config()).get_heads())
    try:
        async with engine.connect() as conn:
            current = {r[0] for r in (await conn.execute(text("SELECT version_num FROM alembic_version"))).all()}
    except Exception as e:
        logger.error("Database schema is not under Alembic yet (%s) — run `alembic upgrade head`", e)
        return False
    if current != heads:
        logger.error("Database schema is at %s, code expects %s — run `alembic upgrade head`",
                     sorted(current), sorted(heads))
        return False
    return True
