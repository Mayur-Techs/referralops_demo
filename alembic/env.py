"""Alembic environment for Matrix360 / ReferralOps migrations.

Reads DATABASE_URL from the environment (with .env fallback) so migrations
work against SQLite locally and against PostgreSQL in production — same
command, different DATABASE_URL.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Load .env so DATABASE_URL is available when running alembic CLI
load_dotenv()

# Alembic Config object — values from alembic.ini
config = context.config

# Override sqlalchemy.url from environment; falls back to alembic.ini value
db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url", "sqlite:///./referralops.db"))
config.set_main_option("sqlalchemy.url", db_url)

# Python logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the app models so autogenerate can detect schema changes
from app.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,          # required for SQLite ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,       # required for SQLite ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
