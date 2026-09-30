"""Stream outage and targeted attendance recovery regression tests."""

import asyncio
import json
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_settings.sources import DotEnvSettingsSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

with patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}):
    from app.database import Base
    from app.event_models import ApprovalScope, AttendanceRefresh, EventInbox
    from app.models import Employee, TripRecord, TripSyncCursor
    from app.services import events, sync, trip_sync


class EventRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.today = date(2026, 9, 30)
        self.now = datetime(2026, 9, 30, 4, 0)
        self.patchers = [
            patch.object(events, "async_session", self.sessions),
            patch.object(trip_sync, "async_session", self.sessions),
            patch.object(events, "_now", return_value=self.now),
            patch.object(events, "business_today", return_value=self.today),
            patch.object(trip_sync, "business_today", return_value=self.today),
            patch.object(events, "_stream", SimpleNamespace(websocket=object())),
            patch.object(events, "_connection_gap", True),
            patch.object(events, "_gap_generation", 5),
            patch.object(events, "_detail_access", None),
            patch.object(events, "_detail_retry_at", datetime.min),
            patch.object(events.settings, "dingtalk_stream_compensation_enabled", False),
            patch.object(trip_sync, "_trip_sync_reserved", False),
            patch.object(trip_sync.settings, "trip_hot_days_past", 0),
            patch.object(trip_sync.settings, "trip_hot_days_future", 1),
            patch.object(trip_sync.settings, "trip_warm_days_future", 3),
        ]
        for patcher in self.patchers:
            patcher.start()
        async with self.sessions() as session:
            session.add(Employee(userid="u1", name="User", dept_id=1))
            session.add(TripSyncCursor(userid="u1", work_date=self.today.isoformat(),
                                       last_synced_at=datetime.now(timezone.utc)))
            await session.commit()

    async def asyncTearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        await self.engine.dispose()

    def approval(self):
        return {"approve_list": [{
            "biz_type": 2, "procInst_id": "p1", "tag_name": "trip",
            "begin_time": "2026-09-30 09:00:00", "end_time": "2026-09-30 18:00:00",
            "duration": "1", "duration_unit": "DAY",
        }]}

    async def run_transport_reconnect(self, failures):
        current = [self.now]
        observations = []

        async def advance(_seconds):
            current[0] += timedelta(seconds=10)

        class Socket:
            def __init__(self, cancel):
                self.cancel = cancel

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.cancel:
                    observations.append((events._connection_gap, events._gap_generation))
                    raise asyncio.CancelledError()
                raise StopAsyncIteration()

        response = Mock()
        response.json.return_value = {"endpoint": "wss://example.invalid", "ticket": "test"}
        http = AsyncMock()
        http.post.side_effect = [response] + [RuntimeError("offline") for _ in range(failures)] + [response]
        http.__aenter__.return_value = http
        client = events.AsyncStreamClient(events.Credential("test-key", "test-secret"), logger=events._sdk_logger)
        with (
            patch.object(client, "pre_start"),
            patch.object(events, "_now", side_effect=lambda: current[0]),
            patch.object(events, "_connection_gap", False),
            patch.object(events, "_gap_generation", 0),
            patch.object(events.httpx, "AsyncClient", return_value=http),
            patch.object(events.websockets, "connect", side_effect=[Socket(False), Socket(True)]),
            patch.object(events.asyncio, "sleep", side_effect=advance),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await client.start()
        self.assertEqual(http.post.await_count, failures + 2)
        return observations[0]

    async def test_repeated_failed_handshakes_retain_whole_outage(self):
        gap, epoch = await self.run_transport_reconnect(8)
        self.assertTrue(gap)
        self.assertGreaterEqual(epoch, 1)

    async def test_short_reconnect_changes_epoch_during_coverage(self):
        _gap, epoch = await self.run_transport_reconnect(0)
        self.assertGreater(epoch, 0)

    async def test_gap_recovery_covers_fresh_warm_dates_on_wednesday(self):
        async with self.sessions() as session:
            for offset in range(1, 4):
                session.add(TripSyncCursor(
                    userid="u1", work_date=(self.today + timedelta(days=offset)).isoformat(),
                    last_synced_at=datetime.now(timezone.utc),
                ))
            await session.commit()
        fetch = AsyncMock(return_value={"approve_list": []})
        with patch.object(trip_sync, "get_update_data", fetch):
            await trip_sync.sync_trip_records(recover_gap=True)
        self.assertEqual(
            {call.args for call in fetch.await_args_list},
            {("u1", (self.today + timedelta(days=offset)).isoformat()) for offset in range(4)},
        )
        self.assertFalse(events._connection_gap)

    async def test_forced_month_does_not_clear_global_gap(self):
        with (
            patch.object(trip_sync, "_build_force_month_dates", return_value=[self.today]),
            patch.object(trip_sync, "get_update_data", AsyncMock(return_value={"approve_list": []})),
        ):
            await trip_sync.sync_trip_records("2026-09")
        self.assertTrue(events._connection_gap)

    async def test_new_gap_during_recovery_is_not_cleared(self):
        async def fetch(_userid, _work_date):
            events._gap_generation += 1
            return {"approve_list": []}

        with patch.object(trip_sync, "get_update_data", side_effect=fetch):
            await trip_sync.sync_trip_records(recover_gap=True)
        self.assertTrue(events._connection_gap)
        self.assertGreater(events._gap_generation, 5)

    async def test_compensation_explicitly_requests_gap_recovery(self):
        recover = AsyncMock(return_value="recovered")
        with (
            patch.object(events, "event_status", AsyncMock(return_value={"connected": True})),
            patch.object(trip_sync, "sync_trip_records", recover),
        ):
            self.assertEqual(await events.compensate_trip_sync(), "recovered")
        recover.assert_awaited_once_with(recover_gap=True)

    async def test_unverified_stream_retains_full_daily_coverage(self):
        recover = AsyncMock(return_value="recovered")
        with (
            patch.object(events, "event_status", AsyncMock(return_value={"connected": True})),
            patch.object(events, "_connection_gap", False),
            patch.object(trip_sync, "sync_trip_records", recover),
        ):
            self.assertEqual(await events.compensate_trip_sync(), "recovered")
        recover.assert_awaited_once_with(recover_gap=False)

    async def test_verified_compensation_refreshes_known_employee_dates(self):
        async with self.sessions() as session:
            session.add(TripRecord(
                userid="u1", work_date="2026-10-01", tag_name="trip",
                begin_time="2026-10-01 09:00:00", end_time="2026-10-01 18:00:00",
                duration_hours=8, proc_inst_id="known", last_synced_at=self.now,
            ))
            await session.commit()
        recover = AsyncMock()
        with (
            patch.object(events, "event_status", AsyncMock(return_value={"connected": True})),
            patch.object(events, "_connection_gap", False),
            patch.object(events.settings, "dingtalk_stream_compensation_enabled", True),
            patch.object(trip_sync, "sync_trip_records", recover),
        ):
            self.assertEqual(await events.compensate_trip_sync(), "Queued 1 known trip dates")
        recover.assert_not_awaited()
        async with self.sessions() as session:
            rows = (await session.execute(select(AttendanceRefresh))).scalars().all()
        self.assertEqual([(row.domain, row.userid, row.date_key) for row in rows],
                         [("trip", "u1", "2026-10-01")])

    async def test_unsettled_date_stays_pending_then_valid_empty_snapshot_completes(self):
        target_day = "2026-10-01"
        async with self.sessions() as session:
            await events._enqueue(session, "trip", "u1", target_day)
            session.add(TripRecord(
                userid="u1", work_date=target_day, tag_name="trip",
                begin_time="2026-10-01 09:00:00", end_time="2026-10-01 18:00:00",
                duration_hours=8, proc_inst_id="old", last_synced_at=self.now,
            ))
            await session.commit()
        with (
            patch.object(sync, "is_full_sync_running", return_value=False),
            patch.object(trip_sync, "get_update_data", AsyncMock(return_value={})),
        ):
            await events.process_refreshes()
        async with self.sessions() as session:
            queued = await session.get(AttendanceRefresh, ("trip", "u1", target_day))
            self.assertEqual(queued.attempts, 1)
            self.assertEqual(queued.error, "TripDataPending")
            self.assertGreater(queued.next_attempt_at, self.now)
            self.assertEqual((await session.execute(select(TripRecord))).scalar_one().proc_inst_id, "old")
            self.assertIsNone((await session.execute(select(TripSyncCursor).where(
                TripSyncCursor.work_date == target_day,
            ))).scalar_one_or_none())
        with (
            patch.object(sync, "is_full_sync_running", return_value=False),
            patch.object(events, "_now", return_value=self.now + timedelta(minutes=1)),
            patch.object(trip_sync, "get_update_data", AsyncMock(return_value={"approve_list": []})),
        ):
            await events.process_refreshes()
        async with self.sessions() as session:
            self.assertIsNone(await session.get(AttendanceRefresh, ("trip", "u1", target_day)))
            self.assertEqual((await session.execute(select(TripRecord))).scalars().all(), [])
            self.assertIsNotNone((await session.execute(select(TripSyncCursor).where(
                TripSyncCursor.work_date == target_day,
            ))).scalar_one_or_none())

    async def test_late_event_without_detail_retains_terminated_tombstone(self):
        async with self.sessions() as session:
            session.add(ApprovalScope(
                instance_id="p1", userid="u1", status="TERMINATED", dates='["2026-09-30"]',
                attached_ids="[]", updated_at=self.now,
            ))
            await session.commit()
        with patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(
            side_effect=events.DingTalkClientError(403, "forbidden"),
        )):
            await events._approval_event({"processInstanceId": "p1", "staffId": "u1", "type": "finish"})
        with patch.object(trip_sync, "get_update_data", AsyncMock(return_value=self.approval())):
            await trip_sync._sync_one("u1", self.today.isoformat(), asyncio.Semaphore(1))
        async with self.sessions() as session:
            self.assertEqual((await session.get(ApprovalScope, "p1")).status, "TERMINATED")
            self.assertEqual((await session.execute(select(TripRecord))).scalars().all(), [])

    async def test_grouped_late_event_cannot_discard_terminal_event(self):
        for terminal in ("terminate", "delete"):
            with self.subTest(terminal=terminal):
                instance_id = "p1" if terminal == "terminate" else "p2"
                async with self.sessions() as session:
                    for index, event_type in enumerate((terminal, "finish")):
                        session.add(EventInbox(
                            event_id=f"{terminal}-{index}", event_type="bpms_instance_change",
                            payload=json.dumps({"processInstanceId": instance_id, "staffId": "u1", "type": event_type}),
                            received_at=self.now - timedelta(seconds=2 - index), next_attempt_at=self.now,
                        ))
                    await session.commit()
                with patch.object(events.dingtalk_client, "workflow_instance", AsyncMock(
                    side_effect=events.DingTalkClientError(403, "forbidden"),
                )):
                    await events.process_events()
                async with self.sessions() as session:
                    scope = await session.get(ApprovalScope, instance_id)
                    self.assertEqual(scope.status, "TERMINATED" if terminal == "terminate" else "DELETED")
                    inbox = (await session.execute(select(EventInbox).where(
                        EventInbox.event_id.like(f"{terminal}-%"),
                    ))).scalars().all()
                    self.assertTrue(all(row.processed_at is not None for row in inbox))


if __name__ == "__main__":
    unittest.main()
