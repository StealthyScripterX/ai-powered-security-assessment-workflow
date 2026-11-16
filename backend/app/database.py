"""Database engine/session wiring.

Single primary datastore, per architecture/TASD-v1.0.md ADR-003. The
engine URL is config-driven (app/config.py) so pointing this at PostgreSQL
16 instead of the SQLite dev default is a configuration change, not a
rewrite -- see IMPLEMENTATION-NOTES.md for what is intentionally deferred
until a Postgres instance is available (triggers, row locking per section 11.9,
CHECK-constraint-backed invariants that SQLite cannot express as written).
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(settings.database_url, echo=False, connect_args=connect_args)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create tables from the ORM metadata.

    Stands in for the Alembic migration chain (alembic/versions) for a
    quick local start; `alembic upgrade head` is the real migration path
    and is what IMPLEMENTATION-NOTES.md / the run instructions use.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
