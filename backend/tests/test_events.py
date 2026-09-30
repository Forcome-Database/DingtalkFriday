import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic_settings.sources import DotEnvSettingsSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

with patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}):
    from app.database import Base
    from app.event_models import ApprovalScope, AttendanceRefresh, EventInbox
    from app.models import Employee, TripRecord
    from app.services import events, sync, trip_sync


class EventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        events._detail_access = None
        events._detail_retry_at = datetime.min
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.patchers = [patch.object(events, "async_session", self.sessions)]
        for patcher in self.patchers:
            patcher.start()
        async with self.sessions() as session:
            session.add(Employee(userid="u1", name="User", dept_id=1))
            await session.commit()

    async def asyncTearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        await self.engine.dispose()

    async def add_event(self, event_id="e1", event_type="bpms_instance_change", **payload):
        event = SimpleNamespace(headers=SimpleNamespace(event_id=event_id, message_id=event_id,
                                                       event_type=event_type), data=payload)
        return await events.InboxHandler().process(event)

    def detail(self, start="2026-09-30 09:00", end="2026-10-01 18:00", **values):
        detail = dict(originatorUserId="u1", status="COMPLETED", result="agree",
                      formComponentValues=[dict(value=json.dumps([start, end, "2", "day"]))])
        detail.update(values)
        return detail

    async def test_ack_follows_durable_insert_and_duplicate_is_merged(self):
        for _ in range(2):
            code, _ = await self.add_event(processInstanceId="p1", staffId="u1")
            self.assertEqual(code, 200)
        async with self.sessions() as session:
            self.assertEqual(len((await session.execute(select(EventInbox))).scalars().all()), 1)
        with patch.object(events, "async_session", side_effect=RuntimeError("database unavailable")):
            with self.assertRaises(RuntimeError):
                await self.add_event("e2")

    async def test_change_refreshes_union_of_old_and_new_dates(self):
        async with self.sessions() as session:
            session.add(ApprovalScope(instance_id="p1", userid="u1", dates='["2026-09-01"]',
                                      attached_ids="[]", updated_at=datetime.utcnow()))
            await session.commit()
        with patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(return_value=self.detail())):
            await events._approval_event(dict(processInstanceId="p1", staffId="u1"))
            await events._approval_event(dict(processInstanceId="p1", staffId="u1"))
        async with self.sessions() as session:
            rows = (await session.execute(select(AttendanceRefresh))).scalars().all()
        self.assertEqual({r.date_key for r in rows if r.domain == "trip"},
                         {"2026-09-01", "2026-09-30", "2026-10-01"})
        self.assertEqual(sum(r.domain == "leave" for r in rows), 1)

    async def test_failed_event_is_retryable_and_not_marked_processed(self):
        await self.add_event(processInstanceId="p1", staffId="u1")
        with patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(side_effect=ValueError("bad response"))):
            await events.process_events()
        async with self.sessions() as session:
            row = await session.get(EventInbox, "e1")
        self.assertIsNone(row.processed_at)
        self.assertEqual(row.attempts, 1)
        self.assertGreater(row.next_attempt_at, row.received_at)

    async def test_revocation_attachment_removes_parent_and_retains_tombstone(self):
        async with self.sessions() as session:
            session.add_all([
                ApprovalScope(instance_id="parent", userid="u1", dates='["2026-09-01"]',
                              attached_ids='["revoke"]', updated_at=datetime.utcnow()),
                TripRecord(userid="u1", work_date="2026-09-01", tag_name="trip", begin_time="2026-09-01 09:00",
                           end_time="2026-09-01 18:00", duration_hours=8, proc_inst_id="parent", last_synced_at=datetime.utcnow()),
            ])
            await session.commit()
        with patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(return_value=self.detail(bizAction="REVOKE"))):
            await events._approval_event(dict(processInstanceId="revoke", staffId="u1"))
        async with self.sessions() as session:
            self.assertEqual((await session.get(ApprovalScope, "parent")).status, "REVOKED")
            self.assertEqual((await session.execute(select(TripRecord))).scalars().all(), [])
        with patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(return_value=self.detail())):
            await events._approval_event(dict(processInstanceId="parent", staffId="u1"))
        async with self.sessions() as session:
            self.assertEqual((await session.get(ApprovalScope, "parent")).status, "REVOKED")

    async def test_refresh_failure_remains_in_durable_queue(self):
        async with self.sessions() as session:
            await events._enqueue(session, "leave", "u1", 2026)
            await session.commit()
        with (patch.object(sync, "is_full_sync_running", return_value=False),
              patch.object(trip_sync, "is_trip_sync_running", return_value=False),
              patch.object(sync, "refresh_leave_records", AsyncMock(side_effect=ValueError("failed")))):
            await events.process_refreshes()
        async with self.sessions() as session:
            row = await session.get(AttendanceRefresh, ("leave", "u1", "2026"))
        self.assertEqual(row.attempts, 1)

    async def test_missing_workflow_permission_falls_back_to_employee_scope(self):
        with (patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(side_effect=events.DingTalkClientError(403, "forbidden"))),
              patch.object(events.settings, "trip_hot_days_past", 1),
              patch.object(events.settings, "trip_hot_days_future", 1),
              patch.object(events.settings, "trip_warm_days_future", 2)):
            await events._approval_event(dict(processInstanceId="p1", staffId="u1"))
        async with self.sessions() as session:
            rows = (await session.execute(select(AttendanceRefresh))).scalars().all()
        self.assertEqual(sum(r.domain == "trip" for r in rows), 4)
        self.assertFalse(events._detail_access)

    def test_nested_form_dates_and_millisecond_ranges(self):
        result = events.form_dates(dict(formComponentValues=[dict(value=json.dumps({
            "rows": [{"startTime": "2026-09-30T16:30:00Z", "endTime": "2026-10-01T10:00:00+08:00"}]
        }))]))
        self.assertEqual(result, {"2026-10-01"})
        self.assertEqual(events.form_dates(self.detail()), {"2026-09-30", "2026-10-01"})

    def test_observed_nested_trip_table_with_half_day_strings(self):
        detail = dict(formComponentValues=[dict(componentType="TableField", value=json.dumps([
            dict(rowValue=[dict(extendValue={"_from": "2026-11-12 \u4e0b\u5348", "_to": "2026-12-18 \u4e0b\u5348"})])
        ]))])
        result = events.form_dates(detail)
        self.assertEqual(len(result), 37)
        self.assertIn("2026-11-12", result)
        self.assertIn("2026-12-18", result)


if __name__ == "__main__":
    unittest.main()
