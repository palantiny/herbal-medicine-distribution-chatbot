"""SQLAlchemy engine factory (optional; app uses app.core.database)."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_async_engine_from_url(database_url: str) -> AsyncEngine:
    """Build async engine. URL must be async driver (postgresql+asyncpg://...)."""
    return create_async_engine(database_url, echo=False)


def normalize_postgres_url(url: str) -> str:
    """Ensure postgresql+asyncpg scheme for async SQLAlchemy."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def engine_from_settings() -> Optional[AsyncEngine]:
    from palantiny.config.settings import get_palantiny_settings

    s = get_palantiny_settings()
    if not s.database_url:
        return None
    return create_async_engine(normalize_postgres_url(s.database_url))
