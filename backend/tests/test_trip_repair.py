"""Historical trip repair reads source totals and leaves uncertain rows intact."""

import sys
import types
import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

test_config = types.ModuleType("app.config")
test_config.settings = SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:")
original_config = sys.modules.get("app.config")
sys.modules["app.config"] = test_config
try:
    from app.database import Base
    from app.models import TripRecord
    from app.services import trip_repair
finally:
    if original_config is None:
        sys.modules.pop("app.config", None)
    else:
        sys.modules["app.config"] = original_config


def stored(day, *, userid="user", approval_id="approval", hours=8, source=None, begin=None, end=None):
    return TripRecord(
        userid=userid, work_date=day, tag_name="出差", proc_inst_id=approval_id,
        begin_time=begin or "2026-09-14 13:30:00", end_time=end or "2026-09-15 18:00:00",
        duration_hours=hours, source_duration=source,
        source_duration_unit="DAY" if source is not None else None,
        last_synced_at=datetime(2026, 9, 1), created_at=datetime(2026, 1, 1),
    )


def approval(**overrides):
    item = {
        "biz_type": 2, "procInst_id": "approval", "tag_name": "出差",
        "begin_time": "2026-09-14 13:30:00", "end_time": "2026-09-15 18:00:00",
        "duration": "1.50", "duration_unit": "DAY",
    }
    item.update(overrides)
    return item


class TripRepairTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_patch = patch.object(trip_repair, "async_session", self.sessions)
        self.session_patch.start()

    async def asyncTearDown(self):
        self.session_patch.stop()
        await self.engine.dispose()

    async def save(self, *rows):
        async with self.sessions() as session:
            session.add_all(rows)
            await session.commit()

    async def rows(self):
        async with self.sessions() as session:
            return (await session.execute(select(TripRecord).order_by(TripRecord.userid, TripRecord.work_date, TripRecord.proc_inst_id))).scalars().all()

    async def test_dry_run_queries_one_date_and_does_not_mutate_two_day_approval(self):
        await self.save(stored("2026-09-14"), stored("2026-09-15"))
        query = AsyncMock(return_value={"approve_list": [approval()]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(2026)
        query.assert_awaited_once_with("user", "2026-09-14")
        self.assertEqual(report["requests"], 1)
        self.assertEqual(report["plannedChanges"], 2)
        self.assertEqual(report["updatedRows"], 0)
        self.assertEqual(report["hoursBefore"], 16)
        self.assertEqual(report["hoursAfter"], 12)
        self.assertEqual(report["plannedHoursDelta"], -4)
        self.assertEqual(report["appliedHoursDelta"], 0)
        self.assertEqual(report["unresolved"], [])
        self.assertEqual([row.duration_hours for row in await self.rows()], [8, 8])
        self.assertTrue(all(row.source_duration is None for row in await self.rows()))

    async def test_apply_keeps_rows_and_creation_time_and_is_idempotent(self):
        await self.save(stored("2026-09-14"), stored("2026-09-15"))
        initial_ids = [row.id for row in await self.rows()]
        query = AsyncMock(return_value={"approve_list": [approval()]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(2026, dry_run=False)
            second = await trip_repair.repair_trip_durations(2026, dry_run=False)
        self.assertEqual(query.await_count, 1)
        self.assertEqual(report["updatedRows"], 2)
        self.assertEqual(report["appliedHoursDelta"], -4)
        rows = await self.rows()
        self.assertEqual([row.id for row in rows], initial_ids)
        self.assertEqual([row.duration_hours for row in rows], [4, 8])
        self.assertTrue(all(row.source_duration == 1.5 and row.source_duration_unit == "DAY" for row in rows))
        self.assertTrue(all(row.created_at == datetime(2026, 1, 1) for row in rows))
        self.assertEqual(second["requests"], 0)
        self.assertEqual(second["plannedChanges"], 0)
        self.assertEqual(second["skippedSourceApprovals"], 1)
        self.assertEqual(second["skippedSources"][0]["reason"], "source_metadata_present_not_revalidated")
        self.assertEqual(second["skippedSources"][0]["localConsistency"], "consistent")

    async def test_one_user_date_resolves_multiple_approvals(self):
        await self.save(stored("2026-09-14"), stored("2026-09-15"), stored("2026-09-14", approval_id="short", begin="2026-09-14 09:00:00", end="2026-09-14 09:30:00"))
        response = {"approve_list": [approval(), approval(procInst_id="short", begin_time="2026-09-14 09:00:00", end_time="2026-09-14 09:30:00", duration="0.50", duration_unit="HOUR")]}
        query = AsyncMock(return_value=response)
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(query.await_count, 1)
        self.assertEqual(report["resolvedApprovals"], 2)
        self.assertEqual(report["hoursAfter"], 12.5)
        self.assertEqual({(row.proc_inst_id, row.work_date): row.duration_hours for row in await self.rows()}, {("approval", "2026-09-14"): 4, ("approval", "2026-09-15"): 8, ("short", "2026-09-14"): 0.5})

    async def test_same_approval_id_does_not_share_sources_between_users(self):
        await self.save(stored("2026-09-14", userid="a"), stored("2026-09-14", userid="b", begin="2026-09-14 09:00:00", end="2026-09-14 10:00:00"))

        async def response(userid, day):
            item = approval() if userid == "a" else approval(begin_time="2026-09-14 09:00:00", end_time="2026-09-14 10:00:00", duration=1, duration_unit="HOUR")
            return {"approve_list": [item]}

        query = AsyncMock(side_effect=response)
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(report["requests"], 2)
        self.assertEqual([row.duration_hours for row in await self.rows()], [4, 1])

    async def test_invalid_or_conflicting_sources_are_preserved_and_reported(self):
        for items, reason in (([approval(duration=None)], "invalid_authority_duration"), ([approval(duration_unit="minutes")], "invalid_authority_duration"), ([approval(), approval(duration="2.0")], "conflicting_authority_values")):
            with self.subTest(reason=reason):
                async with self.sessions() as session:
                    await session.execute(TripRecord.__table__.delete())
                    await session.commit()
                await self.save(stored("2026-09-14"))
                with patch.object(trip_repair, "get_update_data", AsyncMock(return_value={"approve_list": items})):
                    report = await trip_repair.repair_trip_durations(dry_run=False)
                self.assertEqual(report["updatedRows"], 0)
                self.assertEqual(report["unresolved"][0]["reason"], reason)
                self.assertEqual((await self.rows())[0].duration_hours, 8)
                self.assertIsNone((await self.rows())[0].source_duration)

    async def test_missing_first_date_tries_another_stored_date_without_guessing(self):
        await self.save(stored("2026-09-14"), stored("2026-09-15"))
        query = AsyncMock(side_effect=[{}, {"approve_list": [approval()]}])
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(query.await_count, 2)
        self.assertEqual(report["hoursAfter"], 12)
        self.assertEqual(report["unresolved"], [])

    async def test_year_restricts_mutation_even_when_approval_crosses_years(self):
        await self.save(stored("2025-12-31", begin="2025-12-31 16:00:00", end="2026-01-01 18:00:00"), stored("2026-01-01", begin="2025-12-31 16:00:00", end="2026-01-01 18:00:00"))
        item = approval(begin_time="2025-12-31 16:00:00", end_time="2026-01-01 18:00:00", duration="10", duration_unit="HOUR")
        query = AsyncMock(return_value={"approve_list": [item]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(2025, dry_run=False)
        query.assert_awaited_once_with("user", "2025-12-31")
        rows = await self.rows()
        self.assertEqual([row.duration_hours for row in rows], [2, 8])
        self.assertEqual(report["selectedRows"], 1)
        self.assertIsNone(rows[1].source_duration)

    async def test_known_source_can_be_explicitly_rechecked(self):
        await self.save(stored("2026-09-14", source=1.5))
        query = AsyncMock(return_value={"approve_list": [approval()]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False, only_missing_source=False)
        query.assert_awaited_once()
        self.assertEqual(report["updatedRows"], 1)
        self.assertEqual((await self.rows())[0].duration_hours, 4)

    async def test_incorrect_existing_sources_are_explicitly_reported_as_unverified(self):
        await self.save(stored("2026-09-14", source=1.5), stored("2026-09-15", approval_id="conflict", source=1.5), stored("2026-09-16", approval_id="conflict", source=2))
        query = AsyncMock()
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        query.assert_not_awaited()
        self.assertEqual(report["updatedRows"], 0)
        skipped = {item["approvalId"]: item for item in report["skippedSources"]}
        self.assertEqual(skipped["approval"]["localConsistency"], "hours_mismatch")
        self.assertEqual(skipped["conflict"]["localConsistency"], "conflicting")
        self.assertTrue(all(item["reason"] == "source_metadata_present_not_revalidated" for item in skipped.values()))

    async def test_request_limit_and_api_failure_leave_legacy_values_unchanged(self):
        await self.save(stored("2026-09-14"))
        query = AsyncMock(side_effect=RuntimeError("unavailable"))
        with patch.object(trip_repair, "get_update_data", query):
            limited = await trip_repair.repair_trip_durations(dry_run=False, max_requests=0)
            self.assertEqual(query.await_count, 0)
            self.assertEqual(limited["unresolved"][0]["reason"], "request_limit")
            failed = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(failed["unresolved"][0]["reason"], "query_failed:RuntimeError")
        self.assertEqual((await self.rows())[0].duration_hours, 8)

    async def test_concurrent_change_rolls_back_entire_approval(self):
        await self.save(stored("2026-09-14"), stored("2026-09-15"))

        async def concurrent_response(userid, day):
            async with self.sessions() as session:
                await session.execute(update(TripRecord).where(TripRecord.work_date == "2026-09-15").values(duration_hours=6))
                await session.commit()
            return {"approve_list": [approval()]}

        with patch.object(trip_repair, "get_update_data", AsyncMock(side_effect=concurrent_response)):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(report["updatedRows"], 0)
        self.assertEqual(report["appliedHoursDelta"], 0)
        self.assertEqual(report["unresolved"][0]["reason"], "concurrent_change_preserved")
        self.assertEqual([row.duration_hours for row in await self.rows()], [8, 6])
        self.assertTrue(all(row.source_duration is None for row in await self.rows()))

    async def test_authority_zero_hours_does_not_remove_history_or_invent_hours(self):
        await self.save(stored("2026-09-14"))
        query = AsyncMock(return_value={"approve_list": [approval(duration=0)]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(report["updatedRows"], 1)
        self.assertEqual(len(await self.rows()), 1)
        self.assertEqual((await self.rows())[0].duration_hours, 0)

    async def test_history_before_explicit_window_is_preserved_without_api_calls(self):
        await self.save(stored("2026-09-14"))
        query = AsyncMock()
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(
                dry_run=False, minimum_work_date=date(2026, 9, 15),
            )
        query.assert_not_awaited()
        self.assertEqual(report["minimumWorkDate"], "2026-09-15")
        self.assertEqual(report["skippedHistoricalQueries"], 1)
        self.assertEqual(report["unresolved"][0]["reason"], "history_outside_attendance_window")
        self.assertEqual(report["updatedRows"], 0)
        self.assertEqual((await self.rows())[0].duration_hours, 8)

    async def test_cross_window_approval_uses_newer_date_to_repair_all_stored_rows(self):
        await self.save(stored("2026-09-14"), stored("2026-09-15"))
        query = AsyncMock(return_value={"approve_list": [approval()]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(
                dry_run=False, minimum_work_date=date(2026, 9, 15),
            )
        query.assert_awaited_once_with("user", "2026-09-15")
        self.assertEqual(report["skippedHistoricalQueries"], 1)
        self.assertEqual(report["updatedRows"], 2)
        self.assertEqual(report["unresolved"], [])
        self.assertEqual([row.duration_hours for row in await self.rows()], [4, 8])

    async def test_multiple_itinerary_ranges_keep_their_own_authoritative_totals(self):
        first_begin, first_end = "2026-09-14 09:00:00", "2026-09-14 18:00:00"
        second_begin, second_end = "2026-09-15 13:30:00", "2026-09-16 18:00:00"
        await self.save(
            stored("2026-09-14", begin=first_begin, end=first_end),
            stored("2026-09-15", begin=second_begin, end=second_end),
            stored("2026-09-16", begin=second_begin, end=second_end),
        )
        query = AsyncMock(side_effect=[
            {"approve_list": [approval(begin_time=first_begin, end_time=first_end, duration=1)]},
            {"approve_list": [approval(begin_time=second_begin, end_time=second_end)]},
        ])
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        rows = await self.rows()
        self.assertEqual([r.duration_hours for r in rows], [8, 4, 8])
        self.assertEqual([(r.begin_time, r.end_time) for r in rows], [(first_begin, first_end), (second_begin, second_end), (second_begin, second_end)])
        self.assertEqual(report["candidateApprovals"], 1)
        self.assertEqual(report["candidateRanges"], 2)
        self.assertEqual(report["resolvedApprovals"], 1)
        self.assertEqual(report["resolvedRanges"], 2)
        self.assertEqual(report["unresolved"], [])
        self.assertEqual(trip_repair._local_consistency(rows), "consistent")

    async def test_one_response_can_resolve_distinct_ranges_of_same_approval(self):
        first_begin, first_end = "2026-09-14 09:00:00", "2026-09-14 18:00:00"
        second_begin, second_end = first_begin, "2026-09-15 18:00:00"
        await self.save(stored("2026-09-14", begin=first_begin, end=first_end), stored("2026-09-15", begin=second_begin, end=second_end))
        query = AsyncMock(return_value={"approve_list": [
            approval(begin_time=first_begin, end_time=first_end, duration=1),
            approval(begin_time=second_begin, end_time=second_end, duration=2),
        ]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        query.assert_awaited_once_with("user", "2026-09-14")
        self.assertEqual(report["resolvedRanges"], 2)
        self.assertEqual([r.duration_hours for r in await self.rows()], [8, 8])
        self.assertEqual(trip_repair._local_consistency(await self.rows()), "consistent")

    async def test_different_returned_range_does_not_overwrite_existing_range(self):
        await self.save(stored("2026-09-14"))
        query = AsyncMock(return_value={"approve_list": [approval(begin_time="2026-09-14 09:00:00", end_time="2026-09-14 18:00:00", duration=1)]})
        with patch.object(trip_repair, "get_update_data", query):
            report = await trip_repair.repair_trip_durations(dry_run=False)
        self.assertEqual(report["updatedRows"], 0)
        self.assertEqual(report["unresolved"][0]["reason"], "approval_range_not_returned")
        self.assertEqual(report["unresolvedRanges"], 1)
        self.assertEqual(report["unresolvedApprovals"], 1)
        row = (await self.rows())[0]
        self.assertEqual(row.begin_time, "2026-09-14 13:30:00")
        self.assertEqual(row.duration_hours, 8)


if __name__ == "__main__":
    unittest.main()
