"""
SQLAlchemy async database engine, session factory, and declarative base.
Database file is stored at backend/data/leave.db.
"""

import logging

from sqlalchemy import MetaData, text
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
        ("employee", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        ("department", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        ("leave_record", "source", "VARCHAR"),
        ("leave_record", "sync_note", "TEXT"),
        ("leave_record", "last_synced_at", "DATETIME"),
        ("trip_record", "source_duration", "FLOAT"),
        ("trip_record", "source_duration_unit", "VARCHAR"),
        ("sync_log", "task_id", "VARCHAR"),
        ("allowed_user", "role", "VARCHAR DEFAULT 'user'"),
    ]
    async with engine.begin() as conn:
        for table, column, col_type in migrations:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            columns = [row[1] for row in result.fetchall()]
            if column not in columns:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                )
                logger.info("Added column %s.%s", table, column)


async def _migrate_leave_record_key() -> None:
    """Preserve legacy rows while allowing different leave types at the same time."""
    from app.models import LeaveRecord

    async with engine.begin() as conn:
        indexes = (await conn.execute(text("PRAGMA index_list(leave_record)"))).fetchall()
        legacy_key = False
        discarded_indexes = set()
        for index in indexes:
            if not index[2]:
                continue
            index_name = index[1].replace('"', '""')
            columns = (await conn.execute(text(f'PRAGMA index_info("{index_name}")'))).fetchall()
            if [row[2] for row in columns] == ["userid", "start_time", "end_time"]:
                legacy_key = True
                discarded_indexes.add(index[1])
        if not legacy_key:
            return

        columns = (await conn.execute(text("PRAGMA table_info(leave_record)"))).fetchall()
        known_columns = {column.name for column in LeaveRecord.__table__.columns}
        if any(column[1] not in known_columns for column in columns):
            raise RuntimeError("Leave migration found unrecognized columns; existing table retained")
        schema_objects = (await conn.execute(text(
            "SELECT name, sql FROM sqlite_master WHERE tbl_name='leave_record' "
            "AND type IN ('index','trigger') AND sql IS NOT NULL"
        ))).fetchall()

        # A savepoint makes SQLite DDL and the row copy one rollback unit.
        async with conn.begin_nested():
            replacement = LeaveRecord.__table__.to_metadata(
                MetaData(), name="leave_record_migrating"
            )
            await conn.run_sync(lambda sync_conn: replacement.create(sync_conn))
            names = ", ".join(f'"{column.name}"' for column in LeaveRecord.__table__.columns)
            await conn.execute(text(
                f"INSERT INTO leave_record_migrating ({names}) SELECT {names} FROM leave_record"
            ))
            old_count = (await conn.execute(text("SELECT COUNT(*) FROM leave_record"))).scalar_one()
            new_count = (await conn.execute(text("SELECT COUNT(*) FROM leave_record_migrating"))).scalar_one()
            if old_count != new_count:
                raise RuntimeError("Leave record migration row count mismatch")
            await conn.execute(text("DROP TABLE leave_record"))
            await conn.execute(text("ALTER TABLE leave_record_migrating RENAME TO leave_record"))
            for name, sql in schema_objects:
                if name not in discarded_indexes:
                    await conn.execute(text(sql))
        logger.info("Migrated leave_record unique key without dropping historical rows")


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
    await _migrate_leave_record_key()
