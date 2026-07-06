"""PostgreSQL async engine and session management.

Primary platform datastore. The engine and sessionmaker are created lazily so
the application still imports and serves traffic when Postgres is unavailable
(readiness reports it as down). Use ``get_session`` as a FastAPI dependency for
request-scoped transactions.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.postgres_url,
            pool_size=settings.postgres_pool_size,
            pool_pre_ping=True,
            echo=settings.postgres_echo,
            future=True,
        )
        logger.info("Created Postgres async engine")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: request-scoped session, commit on success."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping() -> bool:
    """Best-effort connectivity check for readiness probes."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        logger.warning("Postgres ping failed: %s", exc)
        return False


async def dispose() -> None:
    """Dispose the engine at shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("Disposed Postgres engine")
