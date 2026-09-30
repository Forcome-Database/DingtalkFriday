import asyncio
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.dml import Delete

from app.database import Base
from app.event_models import AttendanceRefresh
from app.models import Employee, SyncLog, TripRecord
from app.services import trip_sync


class TripSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_patch = patch.object(trip_sync, "async_session", self.sessions)
        self.session_patch.start()
        async with self.sessions() as session:
            session.add(Employee(userid="user", name="User", dept_id=1))
            await session.commit()

    async def asyncTearDown(self):
        self.session_patch.stop()
        await self.engine.dispose()

    def approval(self, **overrides):
        item = {
            "biz_type": 2,
            "procInst_id": "approval",
            "tag_name": "trip",
            "begin_time": "2026-09-14 13:30:00",
            "end_time": "2026-09-15 18:00:00",
            "duration": "1.50",
            "duration_unit": "DAY",
        }
        item.update(overrides)
        return {"approve_list": [item]}

    async def test_day_total_is_allocated_once_across_dates(self):
        with patch.object(trip_sync, "get_update_data", AsyncMock(return_value=self.approval())):
            for work_date in ("2026-09-14", "2026-09-15"):
                await trip_sync._sync_one("user", work_date, asyncio.Semaphore(1))
        async with self.sessions() as session:
            rows = (await session.execute(select(TripRecord).order_by(TripRecord.work_date))).scalars().all()
        self.assertEqual([row.duration_hours for row in rows], [4.0, 8.0])
        self.assertEqual(sum(row.duration_hours for row in rows), 12.0)

    async def test_hour_total_preserves_partial_boundary_days(self):
        data = self.approval(
            begin_time="2026-09-14 16:00:00", duration="10", duration_unit="HOUR"
        )
        with patch.object(trip_sync, "get_update_data", AsyncMock(return_value=data)):
            for work_date in ("2026-09-14", "2026-09-15"):
                await trip_sync._sync_one("user", work_date, asyncio.Semaphore(1))
        async with self.sessions() as session:
            rows = (await session.execute(select(TripRecord).order_by(TripRecord.work_date))).scalars().all()
        self.assertEqual([row.duration_hours for row in rows], [2.0, 8.0])

    async def test_invalid_approval_does_not_replace_valid_day(self):
        async with self.sessions() as session:
            session.add(TripRecord(
                userid="user", work_date="2026-09-14", tag_name="trip",
                begin_time="2026-09-14 13:30:00", end_time="2026-09-14 18:00:00",
                duration_hours=4, proc_inst_id="old", last_synced_at=datetime.now(timezone.utc),
            ))
            await session.commit()
        with patch.object(trip_sync, "get_update_data", AsyncMock(return_value=self.approval(duration=None))):
            with self.assertRaises(ValueError):
                await trip_sync._sync_one("user", "2026-09-14", asyncio.Semaphore(1))
        async with self.sessions() as session:
            row = (await session.execute(select(TripRecord))).scalar_one()
        self.assertEqual(row.proc_inst_id, "old")
        self.assertEqual(row.duration_hours, 4)

    async def test_failed_day_cannot_be_reported_as_success(self):
        with (
            patch.object(trip_sync, "_build_force_month_dates", return_value=[datetime(2026, 9, 14).date()]),
            patch.object(trip_sync, "_sync_one", AsyncMock(side_effect=ValueError("invalid approval"))),
            patch.object(trip_sync.settings, "trip_sync_retry_count", 0),
        ):
            await trip_sync.sync_trip_records("2026-09")
        async with self.sessions() as session:
            log = (await session.execute(select(SyncLog).order_by(SyncLog.id.desc()))).scalars().first()
            queued = await session.get(AttendanceRefresh, ("trip", "user", "2026-09-14"))
        self.assertEqual(log.status, "failed")
        self.assertEqual(queued.error, "ValueError")
        self.assertEqual(queued.attempts, 1)

    async def test_busy_write_retries_without_another_dingtalk_request(self):
        execute = AsyncSession.execute
        deletes = []

        async def busy_once(session, statement, *args, **kwargs):
            if isinstance(statement, Delete) and statement.table.name == "trip_record":
                deletes.append(statement)
                if len(deletes) == 1:
                    original = sqlite3.OperationalError("database is locked")
                    original.sqlite_errorcode = sqlite3.SQLITE_BUSY
                    raise OperationalError("DELETE trip_record", {}, original)
            return await execute(session, statement, *args, **kwargs)

        source = AsyncMock(return_value=self.approval())
        with patch.object(trip_sync, "get_update_data", source), \
             patch.object(AsyncSession, "execute", busy_once):
            count = await trip_sync._sync_one("user", "2026-09-14", asyncio.Semaphore(1))
        source.assert_awaited_once()
        self.assertEqual(len(deletes), 2)
        self.assertEqual(count, 1)
        async with self.sessions() as session:
            row = (await session.execute(select(TripRecord))).scalar_one()
        self.assertEqual(row.duration_hours, 4)


if __name__ == "__main__":
    unittest.main()
