"""Complete, atomic organization and leave snapshots from DingTalk."""

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.database import async_session
from app.dingtalk import attendance as att_api
from app.dingtalk import department as dept_api
from app.dingtalk import user as user_api
from app.models import Department, Employee, LeaveRecord, LeaveType, SyncLog

logger = logging.getLogger(__name__)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_full_sync_lock = asyncio.Lock()
_organization_sync_lock = asyncio.Lock()
_leave_sync_lock = asyncio.Lock()
_full_sync_tasks: dict[int, asyncio.Task] = {}


async def _create_sync_log(sync_type: str, task_id: Optional[str] = None) -> int:
    async with async_session() as session:
        log = SyncLog(sync_type=sync_type, task_id=task_id, status="running", started_at=datetime.now(timezone.utc))
        session.add(log)
        await session.commit()
        return log.id


async def _write_sync_log(session, log_id: int, status: str, message: str) -> None:
    await session.execute(update(SyncLog).where(SyncLog.id == log_id).values(
        status=status, message=message, finished_at=datetime.now(timezone.utc)
    ))


async def _finish_sync_log(log_id: int, status: str, message: str = "") -> None:
    async with async_session() as session:
        await _write_sync_log(session, log_id, status, message)
        await session.commit()


async def _sync_departments_impl() -> str:
    log_id = await _create_sync_log("department")
    try:
        root = await dept_api.get_department(settings.root_dept_id)
        snapshot = {root["dept_id"]: root}
        queue = deque([settings.root_dept_id])
        visited = set()
        while queue:
            parent_id = queue.popleft()
            if parent_id in visited:
                continue
            visited.add(parent_id)
            for department in await dept_api.get_sub_departments(parent_id):
                did = department["dept_id"]
                if did in snapshot:
                    raise ValueError("Repeated or cyclic department in DingTalk snapshot")
                snapshot[did] = department
                queue.append(did)

        now = datetime.now(timezone.utc)
        message = f"Synced {len(snapshot)} active departments; historical departments retained"
        async with async_session() as session:
            async with session.begin():
                await session.execute(update(Department).values(is_active=False))
                for department in snapshot.values():
                    values = dict(department, is_active=True, updated_at=now)
                    stmt = sqlite_insert(Department).values(**values)
                    await session.execute(stmt.on_conflict_do_update(
                        index_elements=["dept_id"], set_=values
                    ))
                await _write_sync_log(session, log_id, "success", message)
        return message
    except Exception as exc:
        await _finish_sync_log(log_id, "failed", f"Department sync failed: {exc}")
        raise


async def _sync_employees_impl(dept_id: Optional[int] = None) -> str:
    log_id = await _create_sync_log("employee")
    try:
        async with async_session() as session:
            departments = (await session.execute(select(Department).where(
                Department.is_active.is_(True)
            ))).scalars().all()
            previous = dict((await session.execute(select(Employee.userid, Employee.dept_id))).all())
        department_map = {department.dept_id: department.name for department in departments}
        if dept_id is not None:
            if dept_id not in department_map:
                raise ValueError("Cannot sync an inactive or unknown department")
            department_map = {dept_id: department_map[dept_id]}
        if not department_map:
            raise ValueError("No complete active department snapshot available")

        memberships = defaultdict(list)
        for did in sorted(department_map):
            for user in await user_api.get_user_list_simple(did):
                memberships[user["userid"]].append((did, user["name"]))

        now = datetime.now(timezone.utc)
        message = f"Synced {len(memberships)} active employees across {len(department_map)} departments"
        async with async_session() as session:
            async with session.begin():
                inactive = update(Employee)
                if dept_id is not None:
                    inactive = inactive.where(Employee.dept_id == dept_id)
                await session.execute(inactive.values(is_active=False))
                for userid, departments_for_user in memberships.items():
                    chosen = next((entry for entry in departments_for_user if entry[0] == previous.get(userid)),
                                  departments_for_user[0])
                    values = dict(userid=userid, name=chosen[1], dept_id=chosen[0],
                                  dept_name=department_map[chosen[0]], is_active=True, updated_at=now)
                    stmt = sqlite_insert(Employee).values(**values)
                    await session.execute(stmt.on_conflict_do_update(index_elements=["userid"], set_=values))
                await _write_sync_log(session, log_id, "success", message)
        return message
    except Exception as exc:
        await _finish_sync_log(log_id, "failed", f"Employee sync failed: {exc}")
        raise


async def sync_departments() -> str:
    async with _organization_sync_lock:
        return await _sync_departments_impl()


async def sync_employees(dept_id: Optional[int] = None) -> str:
    async with _organization_sync_lock:
        return await _sync_employees_impl(dept_id)


async def sync_leave_types() -> str:
    log_id = await _create_sync_log("leave_type")
    try:
        candidates = [settings.admin_userid] if settings.admin_userid else []
        async with async_session() as session:
            for userid in (await session.execute(select(Employee.userid).where(
                Employee.is_active.is_(True)
            ).limit(5))).scalars():
                if userid not in candidates:
                    candidates.append(userid)
        if not candidates:
            raise ValueError("No operator available for vacation type sync")
        types = None
        for operator in candidates:
            try:
                types = await att_api.get_vacation_type_list(operator)
                break
            except Exception as exc:
                logger.warning("Vacation type operator failed: %s", exc)
        if not types:
            raise ValueError("No complete vacation type snapshot obtained")
        now = datetime.now(timezone.utc)
        message = f"Synced {len(types)} leave types"
        async with async_session() as session:
            async with session.begin():
                for leave_type in types:
                    values = dict(leave_code=leave_type["leave_code"], leave_name=leave_type["leave_name"],
                                  leave_view_unit=leave_type.get("leave_view_unit"),
                                  hours_in_per_day=leave_type.get("hours_in_per_day", 800), updated_at=now)
                    stmt = sqlite_insert(LeaveType).values(**values)
                    await session.execute(stmt.on_conflict_do_update(index_elements=["leave_code"], set_=values))
                await _write_sync_log(session, log_id, "success", message)
        return message
    except Exception as exc:
        await _finish_sync_log(log_id, "failed", f"Leave type sync failed: {exc}")
        raise


def _year_time_chunks(year: int, max_days: int = 180) -> list:
    if not 1 <= max_days <= 180:
        raise ValueError("Leave chunks must contain 1-180 days")
    start = datetime(year, 1, 1, tzinfo=_SHANGHAI)
    end = datetime(year + 1, 1, 1, tzinfo=_SHANGHAI)
    chunks = []
    while start < end:
        next_start = min(start + timedelta(days=max_days), end)
        chunks.append((int(start.timestamp() * 1000), int(next_start.timestamp() * 1000) - 1))
        start = next_start
    return chunks


def _matching_vacations(record: dict, vacations: list) -> list:
    matching = []
    for vacation in vacations:
        if vacation.get("start_time") is None or vacation.get("end_time") is None:
            continue
        start, end = int(vacation["start_time"]), int(vacation["end_time"])
        if start <= record["start_time"] and end >= record["end_time"]:
            matching.append(vacation)
    exact = [item for item in matching if int(item["start_time"]) == record["start_time"]
             and int(item["end_time"]) == record["end_time"]]
    return exact or matching


def _confirmation(record: dict, matching: list) -> tuple[str, Optional[str]]:
    if record["duration_percent"] <= 0:
        return "待复核", "Attendance status reports zero leave duration"
    if record.get("leave_status") not in (None, "success"):
        return "待复核", f"Attendance status is {record['leave_status']}"
    if not matching:
        return "待复核", "Attendance status has no matching vacation consumption record"
    if any(item.get("leave_status") == "revoke" for item in matching):
        return "待复核", "Approved vacation revocation conflicts with attendance status"
    if any(item.get("cal_type") is not None for item in matching):
        return "待复核", "Vacation reversal conflicts with attendance status"
    if any(item.get("leave_record_type") not in (None, "leave") for item in matching):
        return "待复核", "Vacation record type conflicts with leave consumption"
    states = {item.get("leave_status") for item in matching}
    if states == {"success"}:
        return "已审批", None
    note = "Vacation status conflicts with attendance: " + ",".join(sorted(str(state) for state in states))
    if not states <= {"init", "success", "refuse", "abort"}:
        return "待复核", note
    if any(not item.get("record_id") for item in matching):
        return "待复核", note + "; missing consumption record ID"
    # A consumption ID identifies a ledger record, not an approval instance.
    states_by_record = defaultdict(set)
    for item in matching:
        states_by_record[item["record_id"]].add(item["leave_status"])
    for record_states in states_by_record.values():
        if len(record_states) != 1:
            return "待复核", "Vacation status conflicts for one consumption record: " + ",".join(sorted(record_states))
    if any(record_states == {"success"} for record_states in states_by_record.values()):
        return "已审批", None
    return "待复核", note


async def _sync_leave_records_impl(year: int, selected_userids: Optional[list[str]] = None) -> str:
    log_id = await _create_sync_log("leave_record" if selected_userids is None else "leave_record_incremental")
    request_start = att_api.dingtalk_client.request_counts()
    try:
        chunks = _year_time_chunks(year)
        year_start, year_end = chunks[0][0], chunks[-1][1]
        async with async_session() as session:
            userids = sorted((await session.execute(select(Employee.userid))).scalars().all())
            all_types = (await session.execute(select(LeaveType))).scalars().all()
            pending_pairs = set((await session.execute(select(LeaveRecord.userid, LeaveRecord.leave_code).where(
                LeaveRecord.status == "待复核"
            ))).all())
        if selected_userids is not None:
            if not selected_userids or any(userid not in userids for userid in selected_userids):
                raise ValueError("Incremental leave refresh requires known employee IDs")
            userids = sorted(set(selected_userids))
        if not userids or not all_types:
            raise ValueError("Employees and vacation types must be synced before leave records")
        all_type_map = {leave_type.leave_code: leave_type for leave_type in all_types}
        allowed_names = {name.strip() for name in settings.leave_type_names.split(",") if name.strip()}
        type_map = {code: leave_type for code, leave_type in all_type_map.items()
                    if not allowed_names or leave_type.leave_name in allowed_names}
        if not type_map:
            raise ValueError("No supported vacation type matches the configured names")

        # No inventory mutation occurs until every source page has succeeded.
        status_snapshot = {}
        for offset in range(0, len(userids), 100):
            for start, end in chunks:
                for record in await att_api.get_leave_status(userids[offset:offset + 100], start, end):
                    if record["end_time"] < year_start or record["start_time"] > year_end:
                        continue
                    code = record.get("leave_code")
                    if code in all_type_map and code not in type_map:
                        continue
                    key = (record["userid"], record["start_time"], record["end_time"], code)
                    previous = status_snapshot.get(key)
                    if previous is not None and previous != record:
                        raise ValueError("Conflicting leave status rows in the same snapshot")
                    status_snapshot[key] = record

        verify_all = getattr(settings, "leave_sync_verify_vacation", True)
        query_users = defaultdict(set)
        for record in status_snapshot.values():
            userid, code = record["userid"], record.get("leave_code")
            if code not in type_map:
                for supported_code in type_map:
                    query_users[supported_code].add(userid)
            elif verify_all or (userid, code) in pending_pairs or record.get("leave_status") not in (None, "success"):
                query_users[code].add(userid)
        operator = settings.admin_userid or (userids[0] if userids else None)
        vacation_lookup = defaultdict(list)
        for code, affected_users in query_users.items():
            ordered_users = sorted(affected_users)
            for offset in range(0, len(ordered_users), 50):
                records = await att_api.get_vacation_record_list(operator, code, ordered_users[offset:offset + 50])
                for record in records:
                    vacation_lookup[(code, record["userid"])].append(record)

        values_by_key = {}
        now = datetime.now(timezone.utc)
        for record in status_snapshot.values():
            userid, code = record["userid"], record.get("leave_code")
            if code not in type_map:
                possible = {candidate: _matching_vacations(record, vacation_lookup[(candidate, userid)])
                            for candidate in type_map}
                possible = {candidate: items for candidate, items in possible.items() if items}
                if len(possible) != 1:
                    raise ValueError("Missing or unknown leave_code could not be resolved unambiguously")
                code, matching = next(iter(possible.items()))
                approval_status, note = _confirmation(record, matching)
                source = "attendance+vacation"
            elif userid in query_users.get(code, set()):
                matching = _matching_vacations(record, vacation_lookup[(code, userid)])
                approval_status, note = _confirmation(record, matching)
                source = "attendance+vacation"
            else:
                approval_status = "已审批" if record["duration_percent"] > 0 else "待复核"
                note = None if approval_status == "已审批" else "Attendance status reports zero leave duration"
                source = "attendance"
            key = (userid, record["start_time"], record["end_time"], code)
            values = dict(userid=userid, start_time=record["start_time"], end_time=record["end_time"],
                          duration_percent=record["duration_percent"], duration_unit=record["duration_unit"],
                          leave_code=code, leave_type=type_map[code].leave_name,
                          status=approval_status, source=source, sync_note=note,
                          last_synced_at=now, created_at=now)
            if key in values_by_key and values_by_key[key] != values:
                raise ValueError("Conflicting leave rows after type resolution")
            values_by_key[key] = values

        pending_count = sum(value["status"] == "待复核" for value in values_by_key.values())
        approved_count = len(values_by_key) - pending_count
        request_end = att_api.dingtalk_client.request_counts()
        requests = sum(request_end.get(path, 0) - request_start.get(path, 0) for path in (
            "/topapi/attendance/getleavestatus", "/topapi/attendance/vacation/record/list",
        ))
        scope = "full" if selected_userids is None else "incremental"
        message = (f"Synced {approved_count} confirmed leave records, {pending_count} pending review, year={year}, "
                   f"scope={scope}, employees={len(userids)}, requests={requests}")
        async with async_session() as session:
            async with session.begin():
                await session.execute(delete(LeaveRecord).where(
                    LeaveRecord.start_time <= year_end, LeaveRecord.end_time >= year_start,
                    LeaveRecord.userid.in_(userids),
                    or_(LeaveRecord.leave_code.in_(type_map),
                        LeaveRecord.leave_type.in_([leave_type.leave_name for leave_type in type_map.values()])),
                ))
                if values_by_key:
                    await session.execute(sqlite_insert(LeaveRecord), list(values_by_key.values()))
                await _write_sync_log(session, log_id, "success", message)
        if pending_count:
            logger.warning(message)
        return message
    except Exception as exc:
        await _finish_sync_log(log_id, "failed", f"Leave sync failed; previous records retained: {exc}")
        raise


async def sync_leave_records(year: int, userids: Optional[list[str]] = None) -> str:
    async with _leave_sync_lock:
        return await _sync_leave_records_impl(year, userids)


async def refresh_leave_records(userid: str, year: int) -> str:
    return await sync_leave_records(year, [userid])


def is_leave_sync_running() -> bool:
    return _leave_sync_lock.locked()


def is_full_sync_running() -> bool:
    return any(not task.done() for task in _full_sync_tasks.values())


def _sync_year(year: Optional[int]) -> int:
    return datetime.now(_SHANGHAI).year if year is None else year


def _get_full_sync_task(year: Optional[int]) -> tuple[asyncio.Task, bool]:
    target_year = _sync_year(year)
    task = _full_sync_tasks.get(target_year)
    if task is not None and not task.done():
        return task, False
    task = asyncio.create_task(_run_full_sync(target_year), name=f"full:{uuid4()}")
    _full_sync_tasks[target_year] = task

    def completed(completed_task: asyncio.Task) -> None:
        if _full_sync_tasks.get(target_year) is completed_task:
            _full_sync_tasks.pop(target_year, None)
        if not completed_task.cancelled():
            completed_task.exception()

    task.add_done_callback(completed)
    return task, True


def start_full_sync(year: Optional[int] = None) -> bool:
    """Reserve a task immediately, merging overlapping requests for the same year."""
    return _get_full_sync_task(year)[1]


def full_sync_task_id(year: Optional[int] = None) -> Optional[str]:
    task = _full_sync_tasks.get(_sync_year(year))
    return task.get_name() if task is not None and not task.done() else None


async def _run_full_sync(year: int) -> str:
    log_id = await _create_sync_log("full", task_id=asyncio.current_task().get_name())
    try:
        async with _full_sync_lock:
            messages = [await sync_departments(), await sync_employees(), await sync_leave_types(),
                        await sync_leave_records(year)]
        message = "; ".join(messages)
        await _finish_sync_log(log_id, "success", message)
        return message
    except Exception as exc:
        await _finish_sync_log(log_id, "failed", f"Full sync failed: {exc}")
        raise


async def full_sync(year: Optional[int] = None) -> str:
    task, _ = _get_full_sync_task(year)
    return await asyncio.shield(task)
