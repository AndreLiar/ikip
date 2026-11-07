"""Engine + session factory (Story 1.5).

Builds a SQLAlchemy engine from `Settings.database_url`, forcing the psycopg (v3)
driver. Works against any Postgres the `.env` points at — Neon branch (dev), an
ephemeral test branch, or local Postgres.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ikip_common.config import Settings, get_settings


def _psycopg_url(url: str) -> str:
    # SQLAlchemy defaults bare `postgresql://` to psycopg2; force psycopg v3.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def make_engine(settings: Settings | None = None) -> Engine:
    s = settings or get_settings()
    return create_engine(_psycopg_url(s.database_url), pool_pre_ping=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False)
