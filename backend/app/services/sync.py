"""
Data synchronization service.

Syncs departments, employees, leave types, and leave records
from DingTalk APIs into the local SQLite database.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import async_session
from app.models import Department, Employee, LeaveRecord, LeaveType, SyncLog
from app.dingtalk import department as dept_api
from app.dingtalk import user as user_api
from app.dingtalk import attendance as att_api
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: sync log management
# ---------------------------------------------------------------------------

async def _create_sync_log(sync_type: str) -> int:
    """Create a 'running' sync log entry and return its ID."""
    async with async_session() as session:
        log = SyncLog(
            sync_type=sync_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log.id


async def _finish_sync_log(log_id: int, status: str, message: str = "") -> None:
    """Mark a sync log entry as finished."""
    async with async_session() as session:
        result = await session.execute(select(SyncLog).where(SyncLog.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            log.status = status
            log.message = message
            log.finished_at = datetime.now(timezone.utc)
            await session.commit()


# ---------------------------------------------------------------------------
# Department sync
# ---------------------------------------------------------------------------

async def sync_departments() -> str:
    """
    Recursively sync all departments starting from root (dept_id=1).
    Returns a summary message.
    """
    log_id = await _create_sync_log("department")
    try:
        count = 0
        # BFS traversal of department tree
        queue: List[int] = [settings.root_dept_id]
        visited: set = set()

        while queue:
            parent_id = queue.pop(0)
            if parent_id in visited:
                continue
            visited.add(parent_id)

            sub_depts = await dept_api.get_sub_departments(parent_id)
            for dept in sub_depts:
                async with async_session() as session:
                    stmt = sqlite_insert(Department).values(
                        dept_id=dept["dept_id"],
                        name=dept["name"],
                        parent_id=dept["parent_id"],
                        updated_at=datetime.now(timezone.utc),
                    ).on_conflict_do_update(
                        index_elements=["dept_id"],
                        set_={
                            "name": dept["name"],
                            "parent_id": dept["parent_id"],
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()
                count += 1
                queue.append(dept["dept_id"])

        msg = f"Synced {count} departments"
        await _finish_sync_log(log_id, "success", msg)
        logger.info(msg)
        return msg
    except Exception as e:
        msg = f"Department sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise


# ---------------------------------------------------------------------------
# Employee sync
# ---------------------------------------------------------------------------

async def sync_employees(dept_id: Optional[int] = None) -> str:
    """
    Sync employees for the given department, or all departments if None.
    Returns a summary message.
    """
    log_id = await _create_sync_log("employee")
    try:
        count = 0

        # Determine which departments to sync
        if dept_id is not None:
            dept_ids = [dept_id]
        else:
            async with async_session() as session:
                result = await session.execute(select(Department.dept_id))
                dept_ids = [row[0] for row in result.fetchall()]

        if not dept_ids:
            # Fallback: if no departments in DB, fetch root sub-departments
            dept_ids = [settings.root_dept_id]

        for did in dept_ids:
            users = await user_api.get_user_list_simple(did)

            # Resolve department name from local DB
            dept_name = None
            async with async_session() as session:
                result = await session.execute(
                    select(Department.name).where(Department.dept_id == did)
                )
                row = result.scalar_one_or_none()
                if row:
                    dept_name = row

            for user in users:
                async with async_session() as session:
                    stmt = sqlite_insert(Employee).values(
                        userid=user["userid"],
                        name=user["name"],
                        dept_id=did,
                        dept_name=dept_name,
                        updated_at=datetime.now(timezone.utc),
                    ).on_conflict_do_update(
                        index_elements=["userid"],
                        set_={
                            "name": user["name"],
                            "dept_id": did,
                            "dept_name": dept_name,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()
                count += 1

        msg = f"Synced {count} employees across {len(dept_ids)} departments"
        await _finish_sync_log(log_id, "success", msg)
        logger.info(msg)
        return msg
    except Exception as e:
        msg = f"Employee sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise


# ---------------------------------------------------------------------------
# Leave type sync
# ---------------------------------------------------------------------------

async def sync_leave_types() -> str:
    """
    Sync leave (vacation) types from DingTalk.
    Returns a summary message.
    """
    log_id = await _create_sync_log("leave_type")
    try:
        # Build candidate userid list: configured admin first, then from DB
        candidates = []
        if settings.admin_userid:
            candidates.append(settings.admin_userid)

        async with async_session() as session:
            result = await session.execute(select(Employee.userid).limit(5))
            for row in result.scalars():
                if row not in candidates:
                    candidates.append(row)

        if not candidates:
            msg = "No op_userid available, skipping leave type sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Try each candidate until one succeeds
        types = None
        for op_userid in candidates:
            try:
                types = await att_api.get_vacation_type_list(op_userid)
                break
            except Exception as e:
                logger.warning("get_vacation_type_list failed with userid=%s: %s", op_userid, e)
                continue

        if types is None:
            msg = f"All {len(candidates)} userid candidates failed for get_vacation_type_list"
            await _finish_sync_log(log_id, "failed", msg)
            return msg
        count = 0
        for t in types:
            async with async_session() as session:
                stmt = sqlite_insert(LeaveType).values(
                    leave_code=t["leave_code"],
                    leave_name=t["leave_name"],
                    leave_view_unit=t.get("leave_view_unit"),
                    hours_in_per_day=t.get("hours_in_per_day", 800),
                    updated_at=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    index_elements=["leave_code"],
                    set_={
                        "leave_name": t["leave_name"],
                        "leave_view_unit": t.get("leave_view_unit"),
                        "hours_in_per_day": t.get("hours_in_per_day", 800),
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await session.execute(stmt)
                await session.commit()
            count += 1

        msg = f"Synced {count} leave types"
        await _finish_sync_log(log_id, "success", msg)
        logger.info(msg)
        return msg
    except Exception as e:
        msg = f"Leave type sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise


# ---------------------------------------------------------------------------
# Leave record sync
# ---------------------------------------------------------------------------

def _year_time_chunks(year: int, max_days: int = 180) -> list:
    """
    Split a full year into (start_ms, end_ms) chunks, each at most
    *max_days* days long, to respect DingTalk's 180-day query limit.
    """
    from datetime import datetime as dt, timedelta

    year_start = dt(year, 1, 1)
    year_end = dt(year, 12, 31, 23, 59, 59)

    chunks = []
    chunk_start = year_start
    while chunk_start <= year_end:
        chunk_end_date = chunk_start + timedelta(days=max_days - 1)
        chunk_end = dt(
            chunk_end_date.year, chunk_end_date.month, chunk_end_date.day,
            23, 59, 59,
        )
        if chunk_end > year_end:
            chunk_end = year_end
        chunks.append((
            int(chunk_start.timestamp() * 1000),
            int(chunk_end.timestamp() * 1000),
        ))
        chunk_start = chunk_end.replace(hour=0, minute=0, second=0) + timedelta(days=1)

    return chunks


async def sync_leave_records(year: int) -> str:
    """
    Sync leave records using the vacation record list API.
    This API returns leave_code per record, enabling leave-type filtering.

    Strategy: iterate over each leave type, query all employees' records
    for that type, then upsert into DB with leave_code and leave_type.
    """
    log_id = await _create_sync_log("leave_record")
    try:
        # Get op_userid
        op_userid = settings.admin_userid
        if not op_userid:
            async with async_session() as session:
                result = await session.execute(select(Employee.userid).limit(1))
                op_userid = result.scalar_one_or_none()
        if not op_userid:
            msg = "No op_userid available, skipping leave record sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Gather all employee userids
        async with async_session() as session:
            result = await session.execute(select(Employee.userid))
            all_userids = [row[0] for row in result.fetchall()]

        if not all_userids:
            msg = "No employees found, skipping leave record sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Get leave types to iterate
        async with async_session() as session:
            result = await session.execute(select(LeaveType))
            leave_types = result.scalars().all()

        if not leave_types:
            msg = "No leave types found, skipping leave record sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Filter leave types by whitelist if configured
        allowed_names = []
        if settings.leave_type_names:
            allowed_names = [n.strip() for n in settings.leave_type_names.split(",") if n.strip()]
        if allowed_names:
            leave_types = [lt for lt in leave_types if lt.leave_name in allowed_names]

        year_start_ms = int(datetime(year, 1, 1).timestamp() * 1000)
        year_end_ms = int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000)
        count = 0

        # Clear old records for this year before re-syncing
        async with async_session() as session:
            await session.execute(
                delete(LeaveRecord).where(
                    LeaveRecord.start_time >= year_start_ms,
                    LeaveRecord.start_time <= year_end_ms,
                )
            )
            await session.commit()

        # For each leave type, query all employees' records
        for lt in leave_types:
            leave_code = lt.leave_code
            leave_name = lt.leave_name
            hpd = lt.hours_in_per_day or 800
            view_unit = lt.leave_view_unit or "day"

            # API accepts comma-separated userids (no documented limit,
            # but let's batch at 50 to be safe with response size)
            batch_size = 50
            for i in range(0, len(all_userids), batch_size):
                batch = all_userids[i : i + batch_size]

                try:
                    records = await att_api.get_vacation_record_list(
                        op_userid=op_userid,
                        leave_code=leave_code,
                        userids=batch,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to fetch vacation records for leave_code=%s: %s",
                        leave_code, e,
                    )
                    continue

                for rec in records:
                    st = rec.get("start_time")
                    et = rec.get("end_time")
                    if not st or not et:
                        continue
                    # Filter to target year
                    if st < year_start_ms or st > year_end_ms:
                        continue

                    # Convert record_num to duration_percent / duration_unit
                    if view_unit == "hour" and rec.get("record_num_per_hour") is not None:
                        duration_percent = abs(rec["record_num_per_hour"])
                        duration_unit = "percent_hour"
                    elif rec.get("record_num_per_day") is not None:
                        duration_percent = abs(rec["record_num_per_day"])
                        duration_unit = "percent_day"
                    elif rec.get("record_num_per_hour") is not None:
                        duration_percent = abs(rec["record_num_per_hour"])
                        duration_unit = "percent_hour"
                    else:
                        continue

                    async with async_session() as session:
                        stmt = sqlite_insert(LeaveRecord).values(
                            userid=rec["userid"],
                            start_time=st,
                            end_time=et,
                            duration_percent=duration_percent,
                            duration_unit=duration_unit,
                            leave_type=leave_name,
                            leave_code=leave_code,
                            status="已审批",
                            created_at=datetime.now(timezone.utc),
                        ).on_conflict_do_update(
                            index_elements=["userid", "start_time", "end_time"],
                            set_={
                                "duration_percent": duration_percent,
                                "duration_unit": duration_unit,
                                "leave_type": leave_name,
                                "leave_code": leave_code,
                            },
                        )
                        await session.execute(stmt)
                        await session.commit()
                    count += 1

        msg = f"Synced {count} leave records for {len(all_userids)} employees, year={year}"
        await _finish_sync_log(log_id, "success", msg)
        logger.info(msg)
        return msg
    except Exception as e:
        msg = f"Leave record sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------

async def full_sync(year: Optional[int] = None) -> str:
    """
    Execute all sync steps in order:
    1. Departments
    2. Employees
    3. Leave types
    4. Leave records
    Returns a combined summary message.
    """
    if year is None:
        year = datetime.now().year

    log_id = await _create_sync_log("full")
    try:
        messages = []
        messages.append(await sync_departments())
        messages.append(await sync_employees())
        messages.append(await sync_leave_types())
        messages.append(await sync_leave_records(year))

        combined = "; ".join(messages)
        await _finish_sync_log(log_id, "success", combined)
        logger.info("Full sync completed: %s", combined)
        return combined
    except Exception as e:
        msg = f"Full sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise
