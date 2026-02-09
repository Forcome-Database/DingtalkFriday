"""
SQLAlchemy async database engine, session factory, and declarative base.
Database file is stored at backend/data/leave.db.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

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


async def _migrate_columns() -> None:
    """Add missing columns to existing tables (simple ALTER TABLE migration)."""
    migrations = [
        ("employee", "mobile", "VARCHAR"),
    ]
    async with engine.begin() as conn:
        for table, column, col_type in migrations:
            try:
                # Check if column exists by querying PRAGMA
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                columns = [row[1] for row in result.fetchall()]
                if column not in columns:
                    await conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    )
                    logger.info("Added column %s.%s", table, column)
            except Exception as e:
                logger.warning("Migration check for %s.%s failed: %s", table, column, e)


async def init_db() -> None:
    """Create all tables if they do not exist yet, then run migrations."""
    async with engine.begin() as conn:
        from app.models import (  # noqa: F401 - ensure models are registered
            AllowedUser,
            Department,
            Employee,
            LeaveRecord,
            LeaveType,
            SyncLog,
        )
        await conn.run_sync(Base.metadata.create_all)
    # Run column migrations for existing databases
    await _migrate_columns()
