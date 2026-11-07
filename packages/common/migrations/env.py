"""Alembic environment (Story 1.5).

URL comes from Settings (.env) with the psycopg driver, so migrations run against
whichever Neon branch `.env` points at (dev / ephemeral test / prod). Target
metadata is the ORM Base, so `--autogenerate` sees all models.
"""

from __future__ import annotations

from alembic import context
from dotenv import find_dotenv, load_dotenv
from sqlalchemy import engine_from_config, pool

# Load the repo-root .env regardless of where alembic is invoked (walk up),
# so Settings resolves even when cwd is packages/common.
load_dotenv(find_dotenv(usecwd=True))

# Import models so they register on Base.metadata for autogenerate.
import ikip_common.db.models  # noqa: E402, F401
from ikip_common.config import get_settings  # noqa: E402
from ikip_common.db.base import Base  # noqa: E402
from ikip_common.db.session import _psycopg_url  # noqa: E402

config = context.config
target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", _psycopg_url(get_settings().database_url))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
