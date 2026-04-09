"""Async database engine and session factory.

Engine creation is deferred to first use to avoid import-time side effects
(e.g. requiring DATABASE_URL before the app lifespan configures environment).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = str(settings.database_url)
        # SQLite doesn't support pool_size / pool_pre_ping
        if url.startswith("sqlite"):
            _engine = create_async_engine(url, echo=False)
        else:
            _engine = create_async_engine(
                url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                echo=False,
            )
    return _engine


async def create_tables() -> None:
    """Create all tables (used for SQLite dev mode, skipping Alembic)."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(), expire_on_commit=False
        )
    return _session_factory


def AsyncSessionLocal() -> AsyncSession:
    """Create a new async session (shortcut for the orchestrator)."""
    return _get_session_factory()()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency – yields an async session."""
    async with _get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the async engine, closing all pooled connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def check_db() -> bool:
    """Quick connectivity check – used by healthz."""
    try:
        from sqlalchemy import text
        async with _get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
