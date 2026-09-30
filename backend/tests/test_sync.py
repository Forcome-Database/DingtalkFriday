"""Regression tests using isolated SQLite databases and mocked DingTalk responses."""

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_settings.sources import DotEnvSettingsSource
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

with patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}):
    from app import database
    from app.dingtalk import attendance, user
    from app.models import Department, Employee, LeaveRecord, LeaveType, SyncLog
    from app.services import sync


def milliseconds(year, month, day, hour=9):
    return int(datetime(year, month, day, hour, tzinfo=sync._SHANGHAI).timestamp() * 1000)


def leave(userid="u1", code="annual", start=None, end=None):
    return dict(userid=userid, leave_code=code,
                start_time=start or milliseconds(2026, 9, 30),
                end_time=end or milliseconds(2026, 9, 30, 18),
                duration_percent=800, duration_unit="percent_hour", leave_status=None)


def consumption(record, status="success", code=None, cal_type=None, record_id=None):
    return dict(record, leave_code=code or record.get("leave_code") or "annual",
                leave_status=status, cal_type=cal_type,
                record_num_per_hour=800, record_num_per_day=100, record_id=record_id)


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name, "test.sqlite").as_posix()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(database.Base.metadata.create_all)
        self.settings = SimpleNamespace(root_dept_id=1, admin_userid="operator", leave_type_names="",
                                        leave_sync_verify_vacation=True)
        self.patchers = [patch.object(sync, "async_session", self.sessions),
                         patch.object(sync, "settings", self.settings)]
        for patcher in self.patchers:
            patcher.start()
        sync._full_sync_lock = asyncio.Lock()
        sync._organization_sync_lock = asyncio.Lock()
        sync._leave_sync_lock = asyncio.Lock()
        sync._full_sync_tasks.clear()
        async with self.sessions() as session:
            session.add_all([Department(dept_id=1, name="Root", parent_id=0),
                             Department(dept_id=2, name="Current", parent_id=1),
                             Department(dept_id=9, name="Historical", parent_id=1, is_active=False),
                             Employee(userid="u1", name="One", dept_id=2),
                             Employee(userid="u2", name="Two", dept_id=1),
                             Employee(userid="u3", name="Three", dept_id=1),
                             LeaveType(leave_code="annual", leave_name="年假", leave_view_unit="hour"),
                             LeaveType(leave_code="sick", leave_name="病假", leave_view_unit="hour")])
            await session.commit()

    async def asyncTearDown(self):
        if sync._full_sync_tasks:
            await asyncio.gather(*sync._full_sync_tasks.values(), return_exceptions=True)
        for patcher in reversed(self.patchers):
            patcher.stop()
        await self.engine.dispose()
        self.directory.cleanup()

    async def records(self):
        async with self.sessions() as session:
            return (await session.execute(select(LeaveRecord).order_by(LeaveRecord.id))).scalars().all()

    async def seed_record(self, record=None):
        record = record or leave()
        async with self.sessions() as session:
            session.add(LeaveRecord(userid=record["userid"], leave_code=record["leave_code"], leave_type="年假",
                                    start_time=record["start_time"], end_time=record["end_time"],
                                    duration_percent=100, duration_unit="percent_day", status="已审批"))
            await session.commit()

    def status_mock(self, records):
        async def status(userids, start, end):
            return [record for record in records if record["userid"] in userids
                    and record["end_time"] >= start and record["start_time"] <= end]
        return AsyncMock(side_effect=status)

    async def test_department_failure_keeps_previous_snapshot(self):
        root = dict(dept_id=1, name="Changed", parent_id=0)
        children = AsyncMock(side_effect=RuntimeError("injected page failure"))
        with patch.object(sync.dept_api, "get_department", AsyncMock(return_value=root)), \
             patch.object(sync.dept_api, "get_sub_departments", children):
            with self.assertRaises(RuntimeError):
                await sync.sync_departments()
        async with self.sessions() as session:
            self.assertEqual((await session.get(Department, 1)).name, "Root")
            self.assertFalse((await session.get(Department, 9)).is_active)
            self.assertEqual((await session.execute(select(SyncLog))).scalar_one().status, "failed")

    async def test_department_snapshot_soft_disables_without_deleting(self):
        async with self.sessions() as session:
            (await session.get(Department, 9)).is_active = True
            await session.commit()
        async def children(did):
            return [dict(dept_id=2, name="Renamed", parent_id=1)] if did == 1 else []
        with patch.object(sync.dept_api, "get_department", AsyncMock(return_value=dict(dept_id=1, name="Root", parent_id=0))), \
             patch.object(sync.dept_api, "get_sub_departments", AsyncMock(side_effect=children)):
            await sync.sync_departments()
        async with self.sessions() as session:
            self.assertTrue((await session.get(Department, 2)).is_active)
            self.assertFalse((await session.get(Department, 9)).is_active)
            self.assertEqual((await session.get(Department, 2)).name, "Renamed")

    async def test_employee_failure_keeps_all_memberships(self):
        calls = AsyncMock(side_effect=[[dict(userid="u1", name="Changed")], RuntimeError("injected failure")])
        with patch.object(sync.user_api, "get_user_list_simple", calls):
            with self.assertRaises(RuntimeError):
                await sync.sync_employees()
        async with self.sessions() as session:
            self.assertEqual((await session.get(Employee, "u1")).name, "One")
            self.assertTrue((await session.get(Employee, "u2")).is_active)
        self.assertEqual([call.args[0] for call in calls.await_args_list], [1, 2])

    async def test_employee_snapshot_preserves_history_and_stable_primary_department(self):
        await self.seed_record(leave("u2"))
        calls = AsyncMock(side_effect=[[dict(userid="u1", name="One")],
                                      [dict(userid="u1", name="One"), dict(userid="u3", name="Three")]])
        with patch.object(sync.user_api, "get_user_list_simple", calls):
            await sync.sync_employees()
        async with self.sessions() as session:
            self.assertEqual((await session.get(Employee, "u1")).dept_id, 2)
            self.assertFalse((await session.get(Employee, "u2")).is_active)
        self.assertEqual(len(await self.records()), 1)

    async def test_failed_status_page_keeps_previous_year(self):
        await self.seed_record()
        status = AsyncMock(side_effect=[[], RuntimeError("injected status failure")])
        with patch.object(sync.att_api, "get_leave_status", status):
            with self.assertRaises(RuntimeError):
                await sync.sync_leave_records(2026)
        self.assertEqual(len(await self.records()), 1)

    async def test_failed_consumption_keeps_previous_year(self):
        await self.seed_record()
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([leave()])), \
             patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(side_effect=RuntimeError("failure"))):
            with self.assertRaises(RuntimeError):
                await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].duration_percent, 100)

    async def test_consumption_queries_only_affected_user_type_pairs(self):
        records = [leave("u1", "annual"), leave("u2", "sick")]
        async def vacation(operator, code, userids):
            return [consumption(record) for record in records if record["userid"] in userids and record["leave_code"] == code]
        requests = AsyncMock(side_effect=vacation)
        with patch.object(sync.att_api, "get_leave_status", self.status_mock(records)), \
             patch.object(sync.att_api, "get_vacation_record_list", requests):
            await sync.sync_leave_records(2026)
        self.assertEqual({(call.args[1], tuple(call.args[2])) for call in requests.await_args_list},
                         {("annual", ("u1",)), ("sick", ("u2",))})
        self.assertTrue(all(record.status == "已审批" for record in await self.records()))

    async def test_pending_application_is_persisted_and_rechecked_in_primary_mode(self):
        record = leave()
        vacation = AsyncMock(return_value=[consumption(record, "init")])
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([record])), \
             patch.object(sync.att_api, "get_vacation_record_list", vacation):
            await sync.sync_leave_records(2026)
            pending = (await self.records())[0]
            self.assertEqual(pending.status, "待复核")
            self.assertIn("init", pending.sync_note)
            self.settings.leave_sync_verify_vacation = False
            vacation.return_value = [consumption(record)]
            await sync.sync_leave_records(2026)
        self.assertEqual(vacation.await_count, 2)
        self.assertEqual((await self.records())[0].status, "已审批")

    async def test_http_distinct_consumption_ids_do_not_mix_success_with_aborted_record(self):
        record = leave()
        page = dict(result=dict(leave_records=[
            consumption(record, "success", record_id="active-record"),
            consumption(record, "abort", record_id="aborted-record"),
        ], has_more=False))
        with (
            patch.object(sync.att_api, "get_leave_status", self.status_mock([record])),
            patch.object(attendance.dingtalk_client, "post", AsyncMock(return_value=page)),
        ):
            await sync.sync_leave_records(2026)
        saved = (await self.records())[0]
        self.assertEqual(saved.status, "已审批")
        self.assertEqual(saved.duration_percent, record["duration_percent"])
        self.assertEqual(saved.source, "attendance+vacation")
        self.assertIsNone(saved.sync_note)

    async def test_distinct_consumption_ids_do_not_override_approved_revocation(self):
        record = leave()
        page = dict(result=dict(leave_records=[
            consumption(record, "success", record_id="original-record"),
            consumption(record, "revoke", record_id="new-revocation-record"),
        ], has_more=False))
        with (
            patch.object(sync.att_api, "get_leave_status", self.status_mock([record])),
            patch.object(attendance.dingtalk_client, "post", AsyncMock(return_value=page)),
        ):
            await sync.sync_leave_records(2026)
        saved = (await self.records())[0]
        self.assertEqual(saved.status, "待复核")
        self.assertEqual(saved.duration_percent, record["duration_percent"])
        self.assertIn("revocation", saved.sync_note)

    async def test_same_consumption_id_conflicts_stay_pending_even_with_another_success(self):
        record = leave()
        matching = [consumption(record, "success", record_id="conflicted"),
                    consumption(record, "abort", record_id="conflicted"),
                    consumption(record, "success", record_id="other-success")]
        with (
            patch.object(sync.att_api, "get_leave_status", self.status_mock([record])),
            patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=matching)),
        ):
            await sync.sync_leave_records(2026)
        saved = (await self.records())[0]
        self.assertEqual(saved.status, "待复核")
        self.assertIn("consumption record", saved.sync_note)
        self.assertIn("abort", saved.sync_note)

    async def test_missing_consumption_id_cannot_separate_success_from_revocation(self):
        record = leave()
        for success_id, revoked_id in ((None, "revoked"), ("success", None), (None, None)):
            with self.subTest(success_id=success_id, revoked_id=revoked_id):
                matching = [consumption(record, "success", record_id=success_id),
                            consumption(record, "revoke", record_id=revoked_id)]
                with (
                    patch.object(sync.att_api, "get_leave_status", self.status_mock([record])),
                    patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=matching)),
                ):
                    await sync.sync_leave_records(2026)
                self.assertEqual((await self.records())[0].status, "待复核")

    async def test_distinct_ids_without_confirmed_consumption_remain_pending(self):
        record = leave()
        for other_status in ("init", "refuse", "abort", "revoke"):
            with self.subTest(other_status=other_status):
                matching = [consumption(record, "init", record_id="pending-record"),
                            consumption(record, other_status, record_id="other-record")]
                with (
                    patch.object(sync.att_api, "get_leave_status", self.status_mock([record])),
                    patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=matching)),
                ):
                    await sync.sync_leave_records(2026)
                self.assertEqual((await self.records())[0].status, "待复核")

    async def test_unknown_or_quota_status_cannot_be_hidden_by_distinct_success(self):
        record = leave()
        alternatives = [
            consumption(record, None, record_id="unknown-status"),
            consumption(record, "unknown", record_id="unknown-status"),
            dict(consumption(record, "success", record_id="quota"), leave_record_type="update"),
            consumption(record, "success", cal_type="delete", record_id="reversal"),
        ]
        for alternative in alternatives:
            with self.subTest(alternative=alternative):
                matching = [consumption(record, "success", record_id="success"), alternative]
                with (
                    patch.object(sync.att_api, "get_leave_status", self.status_mock([record])),
                    patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=matching)),
                ):
                    await sync.sync_leave_records(2026)
                self.assertEqual((await self.records())[0].status, "待复核")

    async def test_primary_mode_retains_multiple_types_at_same_interval(self):
        self.settings.leave_sync_verify_vacation = False
        vacation = AsyncMock()
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([leave(), leave(code="sick")])), \
             patch.object(sync.att_api, "get_vacation_record_list", vacation):
            await sync.sync_leave_records(2026)
        vacation.assert_not_awaited()
        self.assertEqual({record.leave_code for record in await self.records()}, {"annual", "sick"})

    async def test_empty_successful_snapshot_clears_year_but_keeps_other_history(self):
        await self.seed_record()
        await self.seed_record(leave(start=milliseconds(2025, 2, 1), end=milliseconds(2025, 2, 1, 18)))
        vacation = AsyncMock()
        with patch.object(sync.att_api, "get_leave_status", AsyncMock(return_value=[])), \
             patch.object(sync.att_api, "get_vacation_record_list", vacation):
            await sync.sync_leave_records(2026)
        vacation.assert_not_awaited()
        records = await self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].start_time, milliseconds(2025, 2, 1))

    async def test_cross_year_overlap_is_imported(self):
        self.settings.leave_sync_verify_vacation = False
        record = leave(start=milliseconds(2025, 12, 31), end=milliseconds(2026, 1, 3, 18))
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([record])):
            await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].start_time, record["start_time"])

    async def test_status_daily_duration_is_not_replaced_with_approval_total(self):
        record = dict(leave(), duration_percent=400)
        total = consumption(leave(start=milliseconds(2026, 9, 29), end=milliseconds(2026, 10, 1, 18)))
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([record])), \
             patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=[total])):
            await sync.sync_leave_records(2026)
        saved = (await self.records())[0]
        self.assertEqual(saved.status, "已审批")
        self.assertEqual(saved.duration_percent, 400)

    async def test_missing_type_is_resolved_with_targeted_queries(self):
        record = leave(code=None)
        async def vacation(operator, code, userids):
            return [consumption(record, code="annual")] if code == "annual" else []
        requests = AsyncMock(side_effect=vacation)
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([record])), \
             patch.object(sync.att_api, "get_vacation_record_list", requests):
            await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].leave_code, "annual")
        self.assertTrue(all(call.args[2] == ["u1"] for call in requests.await_args_list))

    async def test_unresolved_type_fails_without_changing_inventory(self):
        await self.seed_record()
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([leave(code="unknown")])), \
             patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=[])):
            with self.assertRaisesRegex(ValueError, "unambiguously"):
                await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].duration_percent, 100)

    async def test_reversal_never_becomes_confirmed_leave(self):
        record = leave()
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([record])), \
             patch.object(sync.att_api, "get_vacation_record_list", AsyncMock(return_value=[consumption(record), consumption(record, cal_type=1)])):
            await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].status, "待复核")

    async def test_write_failure_rolls_back_deletion(self):
        await self.seed_record()
        self.settings.leave_sync_verify_vacation = False
        async with self.engine.begin() as connection:
            await connection.execute(text("CREATE TRIGGER reject_synced BEFORE INSERT ON leave_record "
                                          "WHEN NEW.source IS NOT NULL BEGIN SELECT RAISE(ABORT, 'injected failure'); END"))
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([leave()])):
            with self.assertRaises(Exception):
                await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].duration_percent, 100)

    async def test_incremental_refresh_never_changes_other_users(self):
        await self.seed_record(leave("u2"))
        self.settings.leave_sync_verify_vacation = False
        requests = self.status_mock([leave("u1")])
        with patch.object(sync.att_api, "get_leave_status", requests):
            await sync.refresh_leave_records("u1", 2026)
        records = await self.records()
        self.assertEqual({record.userid for record in records}, {"u1", "u2"})
        self.assertEqual(next(record.duration_percent for record in records if record.userid == "u2"), 100)
        self.assertTrue(all(call.args[0] == ["u1"] for call in requests.await_args_list))
        self.assertIsNotNone(next(record.last_synced_at for record in records if record.userid == "u1"))

    async def test_success_log_failure_also_rolls_back_inventory(self):
        await self.seed_record()
        self.settings.leave_sync_verify_vacation = False
        original = sync._write_sync_log
        async def write_log(session, log_id, status, message):
            if status == "success":
                raise RuntimeError("injected completion log failure")
            await original(session, log_id, status, message)
        with patch.object(sync.att_api, "get_leave_status", self.status_mock([leave()])), \
             patch.object(sync, "_write_sync_log", side_effect=write_log):
            with self.assertRaisesRegex(RuntimeError, "completion"):
                await sync.sync_leave_records(2026)
        self.assertEqual((await self.records())[0].duration_percent, 100)

    async def test_incremental_refresh_waits_for_full_leave_snapshot(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def status(userids, start, end):
            calls.append(list(userids))
            if len(calls) == 1:
                entered.set()
                await release.wait()
            return []
        with patch.object(sync.att_api, "get_leave_status", AsyncMock(side_effect=status)):
            full = asyncio.create_task(sync.sync_leave_records(2026))
            await entered.wait()
            targeted = asyncio.create_task(sync.refresh_leave_records("u1", 2026))
            await asyncio.sleep(0)
            self.assertEqual(len(calls), 1)
            release.set()
            await asyncio.gather(full, targeted)
        self.assertEqual(calls, [["u1", "u2", "u3"]] * 3 + [["u1"]] * 3)

    async def test_legacy_unique_key_migration_preserves_ids_and_metadata(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(LeaveRecord.__table__.drop)
            await connection.execute(text("CREATE TABLE leave_record (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                                          "userid VARCHAR NOT NULL, start_time INTEGER NOT NULL, end_time INTEGER NOT NULL, "
                                          "duration_percent INTEGER NOT NULL, duration_unit VARCHAR NOT NULL, leave_type VARCHAR, "
                                          "leave_code VARCHAR, status VARCHAR, created_at DATETIME, "
                                          "CONSTRAINT uq_leave_record UNIQUE(userid,start_time,end_time))"))
            await connection.execute(text("INSERT INTO leave_record VALUES "
                                          "(7,'u1',1,2,100,'percent_day','Annual','annual','Approved','2025-01-01 00:00:00')"))
            await connection.execute(text("CREATE INDEX custom_leave_status ON leave_record(status)"))
            await connection.execute(text("CREATE TRIGGER custom_leave_guard BEFORE UPDATE ON leave_record "
                                          "BEGIN SELECT RAISE(ABORT, 'custom guard'); END"))
        with patch.object(database, "engine", self.engine):
            await database._migrate_columns()
            await database._migrate_leave_record_key()
            await database._migrate_leave_record_key()
        records = await self.records()
        self.assertEqual([(record.id, record.duration_percent, record.status) for record in records], [(7, 100, "Approved")])
        self.assertEqual(records[0].created_at, datetime(2025, 1, 1))
        self.assertIsNone(records[0].source)
        async with self.sessions() as session:
            session.add(LeaveRecord(userid="u1", start_time=1, end_time=2, duration_percent=100,
                                    duration_unit="percent_day", leave_code="sick"))
            await session.commit()
        self.assertEqual(len(await self.records()), 2)
        async with self.engine.connect() as connection:
            objects = (await connection.execute(text("SELECT name FROM sqlite_master "
                                                      "WHERE name IN ('custom_leave_status','custom_leave_guard')"))).scalars().all()
        self.assertEqual(set(objects), {"custom_leave_status", "custom_leave_guard"})

    async def test_failed_migration_rolls_back_ddl_and_keeps_original_rows(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(LeaveRecord.__table__.drop)
            await connection.execute(text("CREATE TABLE leave_record (id INTEGER PRIMARY KEY, userid VARCHAR, "
                                          "start_time INTEGER, end_time INTEGER, duration_percent INTEGER, "
                                          "duration_unit VARCHAR, leave_type VARCHAR, leave_code VARCHAR, status VARCHAR, "
                                          "created_at DATETIME, UNIQUE(userid,start_time,end_time))"))
            await connection.execute(text("INSERT INTO leave_record VALUES "
                                          "(13,'u1',1,2,NULL,'percent_day','Annual','annual','Approved',NULL)"))
        with patch.object(database, "engine", self.engine):
            await database._migrate_columns()
            with self.assertRaises(Exception):
                await database._migrate_leave_record_key()
        async with self.engine.connect() as connection:
            row = (await connection.execute(text("SELECT id,duration_percent FROM leave_record"))).one()
            temporary = (await connection.execute(text("SELECT COUNT(*) FROM sqlite_master "
                                                       "WHERE name='leave_record_migrating'"))).scalar_one()
        self.assertEqual(tuple(row), (13, None))
        self.assertEqual(temporary, 0)

    async def test_active_flags_migrate_existing_rows_to_true(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Department.__table__.drop)
            await connection.run_sync(Employee.__table__.drop)
            await connection.execute(text("CREATE TABLE department (dept_id INTEGER PRIMARY KEY, name VARCHAR, "
                                          "parent_id INTEGER, updated_at DATETIME)"))
            await connection.execute(text("CREATE TABLE employee (userid VARCHAR PRIMARY KEY, name VARCHAR, "
                                          "dept_id INTEGER, dept_name VARCHAR, avatar VARCHAR, updated_at DATETIME)"))
            await connection.execute(text("INSERT INTO department VALUES (1,'Root',0,NULL)"))
            await connection.execute(text("INSERT INTO employee VALUES ('old','Old',1,'Root',NULL,NULL)"))
        with patch.object(database, "engine", self.engine):
            await database._migrate_columns()
        async with self.sessions() as session:
            self.assertTrue((await session.get(Employee, "old")).is_active)
            self.assertTrue((await session.get(Department, 1)).is_active)

    async def test_same_year_tasks_merge_and_other_years_run_serially(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def departments():
            entered.set()
            await release.wait()
            return "departments"
        department_mock = AsyncMock(side_effect=departments)
        leave_mock = AsyncMock(return_value="leaves")
        with patch.object(sync, "sync_departments", department_mock), \
             patch.object(sync, "sync_employees", AsyncMock(return_value="employees")), \
             patch.object(sync, "sync_leave_types", AsyncMock(return_value="types")), \
             patch.object(sync, "sync_leave_records", leave_mock):
            first = asyncio.create_task(sync.full_sync(2026))
            await entered.wait()
            same = asyncio.create_task(sync.full_sync(2026))
            other = asyncio.create_task(sync.full_sync(2025))
            await asyncio.sleep(0)
            self.assertTrue(sync.is_full_sync_running())
            self.assertEqual(department_mock.await_count, 1)
            release.set()
            await asyncio.gather(first, same, other)
        self.assertEqual(department_mock.await_count, 2)
        self.assertEqual([call.args[0] for call in leave_mock.await_args_list], [2026, 2025])
        self.assertFalse(sync.is_full_sync_running())

    async def test_task_id_migration_preserves_existing_sync_log(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(SyncLog.__table__.drop)
            await connection.execute(text(
                "CREATE TABLE sync_log (id INTEGER PRIMARY KEY, sync_type VARCHAR NOT NULL, "
                "status VARCHAR NOT NULL, message TEXT, started_at DATETIME, finished_at DATETIME)"
            ))
            await connection.execute(text(
                "INSERT INTO sync_log VALUES (7,'full','success','old result',NULL,'2026-09-01 01:00:00')"
            ))
        with patch.object(database, "engine", self.engine):
            await database._migrate_columns()
            await database._migrate_columns()
        async with self.sessions() as session:
            log = await session.get(SyncLog, 7)
        self.assertIsNone(log.task_id)
        self.assertEqual((log.status, log.message), ("success", "old result"))
        self.assertEqual(log.finished_at, datetime(2026, 9, 1, 1))

    async def test_http_task_status_keeps_different_year_success_and_failure_separate(self):
        import httpx
        from fastapi import FastAPI
        from app.routers import sync as sync_router
        from app.services import trip_sync

        entered, release = asyncio.Event(), asyncio.Event()

        async def departments():
            entered.set()
            await release.wait()
            return "departments"

        async def leaves(year):
            if year == 2025:
                raise ValueError("2025 source failed")
            return "2026 leave success"

        event_module = ModuleType("app.services.events")
        event_module.event_status = AsyncMock(return_value={"enabled": False, "connected": False})
        application = FastAPI()
        application.include_router(sync_router.router)
        application.dependency_overrides[sync_router.require_admin] = lambda: {}
        application.dependency_overrides[sync_router.get_current_user] = lambda: {}
        with (
            patch.object(sync_router, "async_session", self.sessions),
            patch.object(sync, "sync_departments", AsyncMock(side_effect=departments)),
            patch.object(sync, "sync_employees", AsyncMock(return_value="employees")),
            patch.object(sync, "sync_leave_types", AsyncMock(return_value="types")),
            patch.object(sync, "sync_leave_records", AsyncMock(side_effect=leaves)),
            patch.object(trip_sync, "is_trip_sync_running", return_value=False),
            patch.dict(sys.modules, {"app.services.events": event_module}),
        ):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
                try:
                    first = await client.post("/api/sync", json={"year": 2026})
                    self.assertEqual(first.status_code, 200)
                    first_id = first.json()["taskId"]
                    self.assertTrue(first.json()["success"])
                    self.assertTrue(first_id.startswith("full:"))
                    await entered.wait()
                    same = await client.post("/api/sync", json={"year": 2026})
                    self.assertFalse(same.json()["success"])
                    self.assertEqual(same.json()["taskId"], first_id)
                    second = await client.post("/api/sync", json={"year": 2025})
                    self.assertTrue(second.json()["success"])
                    second_id = second.json()["taskId"]
                    self.assertNotEqual(first_id, second_id)
                    running = await client.get("/api/sync/status", params={"taskId": first_id})
                    self.assertEqual(running.status_code, 200)
                    self.assertTrue(running.json()["running"]["full"])
                    self.assertEqual(running.json()["task"]["task_id"], first_id)
                    self.assertEqual(running.json()["task"]["status"], "running")
                finally:
                    release.set()
                    results = await asyncio.gather(*list(sync._full_sync_tasks.values()), return_exceptions=True)
                self.assertTrue(any(isinstance(result, ValueError) for result in results))
                successful = (await client.get("/api/sync/status", params={"taskId": first_id})).json()
                failed = (await client.get("/api/sync/status", params={"taskId": second_id})).json()
                unknown = (await client.get("/api/sync/status", params={"taskId": "full:unknown"})).json()
                untracked = (await client.get("/api/sync/status")).json()
        self.assertEqual(successful["latest"]["full"]["task_id"], second_id)
        self.assertEqual(successful["latest"]["full"]["status"], "failed")
        self.assertEqual(successful["task"]["task_id"], first_id)
        self.assertEqual(successful["task"]["status"], "success")
        self.assertIn("2026 leave success", successful["task"]["message"])
        self.assertEqual(failed["task"]["task_id"], second_id)
        self.assertEqual(failed["task"]["status"], "failed")
        self.assertIn("2025 source failed", failed["task"]["message"])
        self.assertIsNone(unknown["task"])
        self.assertIsNone(untracked["task"])
        self.assertFalse(successful["running"]["full"])

    async def test_sync_status_separates_domains_and_exposes_pending_warning(self):
        from app.routers import sync as sync_router
        from app.services import trip_sync
        events = ModuleType("app.services.events")
        events.event_status = AsyncMock(return_value={"enabled": False, "connected": False})
        await self.seed_record()
        async with self.sessions() as session:
            record = (await session.execute(select(LeaveRecord))).scalar_one()
            record.status = "待复核"
            session.add_all([SyncLog(sync_type="leave_record", status="success", finished_at=datetime(2026, 9, 30, 1)),
                             SyncLog(sync_type="full", status="success", finished_at=datetime(2026, 9, 30, 1)),
                             SyncLog(sync_type="trip_record", status="failed", message="Trip failed")])
            await session.commit()
        with patch.object(sync_router, "async_session", self.sessions), \
             patch.object(trip_sync, "is_trip_sync_running", return_value=False), \
             patch.dict(sys.modules, {"app.services.events": events}):
            response = await sync_router.sync_status({})
        self.assertEqual(response.latest["full"].sync_type, "full")
        self.assertEqual(response.latest["trip"].status, "failed")
        self.assertEqual(response.freshness["leave"].state, "warning")
        self.assertEqual(response.freshness["leave"].pending_count, 1)
        self.assertEqual(response.freshness["leave"].last_success_at.tzinfo, timezone.utc)


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_vacation_wrapper_retains_consumption_record_identity(self):
        records = [consumption(leave(), "success", record_id="success-record"),
                   consumption(leave(), "abort", record_id="aborted-record")]
        with patch.object(attendance.dingtalk_client, "post", AsyncMock(return_value=dict(
            result=dict(leave_records=records, has_more=False),
        ))):
            result = await attendance.get_vacation_record_list("operator", "annual", ["u1"])
        self.assertEqual([item["record_id"] for item in result], ["success-record", "aborted-record"])

    async def test_http_response_keeps_distinct_trip_headcount(self):
        import httpx
        from fastapi import FastAPI
        from app.schemas import TripMonthlySummaryResponse

        app = FastAPI()

        @app.get("/summary", response_model=TripMonthlySummaryResponse)
        async def summary():
            return dict(stats=dict(totalCount=0, totalDays=0, todayTripCount=5,
                                   todayOutingCount=4, todayTotalCount=6),
                        list=[], summary={}, pagination=dict(page=1, pageSize=10, total=0))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stats"]["todayTotalCount"], 6)

    async def test_vacation_uses_200_and_retains_pending_status(self):
        record = consumption(leave(), "init")
        request = AsyncMock(side_effect=[dict(result=dict(leave_records=[record], has_more=True)),
                                         dict(result=dict(leave_records=[], has_more=False))])
        with patch.object(attendance.dingtalk_client, "post", request):
            result = await attendance.get_vacation_record_list("operator", "annual", ["u1"])
        self.assertEqual(result[0]["leave_status"], "init")
        self.assertEqual(request.await_args_list[0].kwargs["json_body"]["size"], 200)
        self.assertEqual(request.await_args_list[1].kwargs["json_body"]["offset"], 200)

    async def test_balance_adjustment_without_leave_interval_is_not_malformed(self):
        balance = dict(userid="u1", leave_code="annual", start_time=0, end_time=0, cal_type=1)
        with patch.object(attendance.dingtalk_client, "post", AsyncMock(return_value=dict(
            result=dict(leave_records=[balance], has_more=False)
        ))):
            records = await attendance.get_vacation_record_list("operator", "annual", ["u1"])
        self.assertIsNone(records[0]["start_time"])

    async def test_repeated_page_and_malformed_page_fail(self):
        page = dict(result=dict(leave_records=[consumption(leave())], has_more=True))
        with patch.object(attendance.dingtalk_client, "post", AsyncMock(return_value=page)):
            with self.assertRaisesRegex(ValueError, "Repeated"):
                await attendance.get_vacation_record_list("operator", "annual", ["u1"])
        with patch.object(attendance.dingtalk_client, "post", AsyncMock(return_value=dict(result={}))):
            with self.assertRaisesRegex(ValueError, "Malformed"):
                await attendance.get_vacation_record_list("operator", "annual", ["u1"])

    async def test_status_preserves_optional_leave_code_and_has_20_page_size(self):
        record = leave()
        request = AsyncMock(return_value=dict(result=dict(leave_status=[record], has_more=False)))
        with patch.object(attendance.dingtalk_client, "post", request):
            result = await attendance.get_leave_status(["u1"], milliseconds(2026, 9, 1), milliseconds(2026, 10, 1))
        self.assertEqual(result[0]["leave_code"], "annual")
        self.assertEqual(request.await_args.kwargs["json_body"]["size"], 20)

    async def test_status_does_not_silently_truncate_user_batch(self):
        request = AsyncMock()
        with patch.object(attendance.dingtalk_client, "post", request):
            with self.assertRaises(ValueError):
                await attendance.get_leave_status([f"u{number}" for number in range(101)], 1, 2)
        request.assert_not_awaited()

    async def test_user_list_cursor_must_advance(self):
        request = AsyncMock(return_value=dict(result=dict(list=[dict(userid="u1", name="One")],
                                                          has_more=True, next_cursor=0)))
        with patch.object(user.dingtalk_client, "post", request):
            with self.assertRaisesRegex(ValueError, "cursor"):
                await user.get_user_list_simple(1)

    def test_year_chunks_cover_every_millisecond_in_shanghai(self):
        chunks = sync._year_time_chunks(2024)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0][0], milliseconds(2024, 1, 1, 0))
        self.assertEqual(chunks[-1][1], milliseconds(2025, 1, 1, 0) - 1)
        self.assertTrue(all(end - start < 180 * 86400000 for start, end in chunks))
        self.assertTrue(all(chunks[index][1] + 1 == chunks[index + 1][0] for index in range(len(chunks) - 1)))


if __name__ == "__main__":
    unittest.main()
