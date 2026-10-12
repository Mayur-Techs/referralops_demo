"""Database engine/session helpers.

Supports:
  • SQLite  — local development and tests (default)
  • PostgreSQL — set DATABASE_URL=postgresql+psycopg2://... in environment

The engine is built once per application instance. New columns added to
models are nullable/with defaults so `create_all` adds them safely on a
fresh DB; for the existing DB we use Alembic migrations (see alembic/).
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .models import Base, Partner


def build_engine(database_url: str):
    """Build an SQLAlchemy engine with the correct driver settings.

    SQLite-only: check_same_thread=False (required by FastAPI/Starlette).
    PostgreSQL: pool_pre_ping keeps connections alive after idle periods.
    """
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    engine_kwargs: dict = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }

    # PostgreSQL: add SSL mode if not already in the URL
    if not is_sqlite and "sslmode" not in database_url:
        # prefer SSL but allow hosts that don't support it (e.g. local pg)
        connect_args["sslmode"] = "prefer"

    return create_engine(database_url, **engine_kwargs)


def initialise_database(engine) -> None:
    """Create all tables that do not yet exist and seed reference data.

    This is safe for both fresh SQLite and PostgreSQL databases.
    For an existing database being *upgraded*, run Alembic migrations
    (`alembic upgrade head`) instead of relying on this function alone.
    """
    Base.metadata.create_all(engine)
    _seed_partners(engine)


def _seed_partners(engine) -> None:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as db:
        seeds = [
            ("PARTNER-001", "Demo Industrial Network Partner"),
            ("PARTNER-002", "Demo Broker Partner"),
        ]
        for code, name in seeds:
            if db.query(Partner).filter(Partner.code == code).first() is None:
                db.add(Partner(code=code, display_name=name, active=True))
        db.commit()
