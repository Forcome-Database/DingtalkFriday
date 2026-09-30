import unittest
from datetime import datetime
from types import ModuleType
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import LeaveRecord, SyncLog
from app.routers import sync as sync_router
from app.services import trip_sync


class FreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as session:
            session.add(LeaveRecord(userid="u1", start_time=1, end_time=2,
                                    duration_percent=100, duration_unit="percent_hour",
                                    leave_code="annual", status="\u5f85\u590d\u6838"))
            session.add(SyncLog(sync_type="leave_record", status="success",
                                message="Complete snapshot: 10 confirmed, 1 pending",
                                finished_at=datetime(2026, 9, 30, 1)))
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def status_after_incremental(self, status):
        async with self.sessions() as session:
            session.add(SyncLog(sync_type="leave_record_incremental", status=status,
                                message="Employee refresh: " + status,
                                finished_at=datetime(2026, 9, 30, 2)))
            await session.commit()
        events = ModuleType("app.services.events")
        events.event_status = AsyncMock(return_value={})
        with patch.object(sync_router, "async_session", self.sessions), \
             patch.object(sync_router, "is_leave_sync_running", return_value=False), \
             patch.object(sync_router, "is_full_sync_running", return_value=False), \
             patch.object(trip_sync, "is_trip_sync_running", return_value=False), \
             patch.dict("sys.modules", {"app.services.events": events}):
            return (await sync_router.sync_status({}, taskId=None)).freshness["leave"]

    async def test_employee_success_preserves_complete_snapshot_summary(self):
        result = await self.status_after_incremental("success")
        self.assertEqual(result.message, "Complete snapshot: 10 confirmed, 1 pending")
        self.assertEqual((result.state, result.pending_count), ("warning", 1))
        self.assertEqual(result.last_success_at.hour, 1)

    async def test_employee_failure_remains_visible(self):
        result = await self.status_after_incremental("failed")
        self.assertEqual(result.message, "Employee refresh: failed")
        self.assertEqual((result.state, result.pending_count), ("failed", 1))
        self.assertEqual(result.last_success_at.hour, 1)
