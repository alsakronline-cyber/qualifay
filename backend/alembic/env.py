from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context
import os

config = context.config

if config.config_file_name is not None:
    # Keep the app's loggers alive when migrations run in-process (init_db in scripts).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Import all models so Base.metadata is populated
from app.models.models import Base  # noqa: F401 - this registers all models
import app.models.models  # noqa: F401

target_metadata = Base.metadata

# Override sqlalchemy.url from env
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Alembic needs sync URL (not asyncpg)
sync_url = DATABASE_URL.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Fail fast instead of queueing forever behind a worker's lock (a stuck boot-time
        # ALTER once bricked every restart). A timeout fails the deploy visibly; rerun it.
        connection.execute(text("SET lock_timeout = '10s'"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
