"""
SQLAlchemy async database engine, session factory, and declarative base.
Database file is stored at backend/data/leave.db.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Create async engine with SQLite-specific settings
engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite does not support pool_size / max_overflow in the same way,
    # but connect_args are still useful for WAL mode etc.
    connect_args={"check_same_thread": False},
)

# Async session factory
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def get_session() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all tables if they do not exist yet."""
    async with engine.begin() as conn:
        from app.models import (  # noqa: F401 - ensure models are registered
            Department,
            Employee,
            LeaveRecord,
            LeaveType,
            SyncLog,
        )
        await conn.run_sync(Base.metadata.create_all)
