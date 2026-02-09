"""
Leave data query service.

Provides monthly summary aggregation and daily detail queries
from the locally synced leave_record + employee tables.
"""

import calendar
import logging
from datetime import datetime, date as date_type, timedelta
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Employee, LeaveRecord, LeaveType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_workday(d: date_type) -> bool:
    """判断是否为工作日（考虑中国法定节假日和调休补班）"""
    try:
        from chinese_calendar import is_workday
        result = is_workday(d)
        logger.debug("_is_workday(%s) = %s (via chinese_calendar)", d, result)
        return result
    except (ImportError, NotImplementedError):
        # 库不可用或年份超出范围时，回退到简单周末判断
        logger.warning("chinese_calendar 不支持 %s，回退到简单周末判断", d)
        return d.weekday() < 5


def _ms_to_datetime(ms: int) -> datetime:
    """Convert a Unix millisecond timestamp to a datetime object."""
    return datetime.fromtimestamp(ms / 1000)


def _month_range_ms(year: int, month: int) -> Tuple[int, int]:
    """Return (start_ms, end_ms) for the given year-month."""
    _, last_day = calendar.monthrange(year, month)
    start = int(datetime(year, month, 1, 0, 0, 0).timestamp() * 1000)
    end = int(datetime(year, month, last_day, 23, 59, 59).timestamp() * 1000)
    return start, end


def _year_range_ms(year: int) -> Tuple[int, int]:
    """Return (start_ms, end_ms) for the given year."""
    start = int(datetime(year, 1, 1, 0, 0, 0).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000)
    return start, end


async def _get_descendant_dept_ids(session: AsyncSession, dept_id: int) -> Set[int]:
    """递归获取部门及其所有子部门的 ID 集合（BFS）"""
    from app.models import Department
    result = {dept_id}
    queue = [dept_id]
    while queue:
        parent = queue.pop()
        rows = await session.execute(
            select(Department.dept_id).where(Department.parent_id == parent)
        )
        for (child_id,) in rows:
            if child_id not in result:
                result.add(child_id)
                queue.append(child_id)
    return result


async def _get_leave_type_map() -> Dict[str, LeaveType]:
    """Load all leave types into a dict keyed by leave_code."""
    async with async_session() as session:
        result = await session.execute(select(LeaveType))
        types = result.scalars().all()
        return {t.leave_code: t for t in types}


def _convert_duration(
    duration_percent: int,
    duration_unit: str,
    target_unit: str,
    hours_in_per_day: int = 800,
) -> float:
    """
    Convert a duration_percent value to the target unit (day or hour).

    统一走"总小时数"中转，确保天数按标准 8h/天换算。

    duration_percent semantics:
      - If duration_unit == "percent_day":  value/100 gives 钉钉天数
      - If duration_unit == "percent_hour": value/100 gives hours

    hours_in_per_day is the *100 value (e.g. 800 means 8h/day, 1200 means 12h/day).

    Returns a float in the target unit.
    """
    raw = duration_percent / 100.0
    hpd = hours_in_per_day / 100.0  # 钉钉的每天小时数 (e.g. 8.0 or 12.0)
    STANDARD_HPD = 8.0  # 标准工作日小时数

    # Step 1: 统一转为总小时数
    if duration_unit == "percent_hour":
        total_hours = raw
    else:
        # percent_day: raw 是钉钉天数，乘以钉钉的 hpd 得到总小时
        total_hours = raw * hpd

    # Step 2: 转为目标单位
    if target_unit == "hour":
        return total_hours
    else:
        # day: 用标准 8h/天 换算
        return total_hours / STANDARD_HPD


# ---------------------------------------------------------------------------
# Monthly summary
# ---------------------------------------------------------------------------

async def get_monthly_summary(
    year: int,
    dept_id: Optional[int] = None,
    leave_types: Optional[List[str]] = None,
    employee_name: Optional[str] = None,
    unit: str = "day",
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> dict:
    """
    Build the monthly summary table data.

    Returns a dict matching MonthlySummaryResponse schema:
    {
        stats: { totalCount, totalDays, avgDays, annualRatio, annualDays },
        list: [ { employeeId, name, dept, avatar, months[12], total } ],
        summary: { personCount, months[12], total },
        pagination: { page, pageSize, total },
    }
    """
    year_start_ms, year_end_ms = _year_range_ms(year)
    type_map = await _get_leave_type_map()

    async with async_session() as session:
        # ---- Build employee filter ----
        emp_conditions = []
        if dept_id is not None:
            all_dept_ids = await _get_descendant_dept_ids(session, dept_id)
            emp_conditions.append(Employee.dept_id.in_(all_dept_ids))
        if employee_name:
            emp_conditions.append(Employee.name.contains(employee_name))

        emp_query = select(Employee)
        if emp_conditions:
            emp_query = emp_query.where(and_(*emp_conditions))

        emp_result = await session.execute(emp_query)
        employees = emp_result.scalars().all()
        emp_map = {e.userid: e for e in employees}
        emp_userids = set(emp_map.keys())

        if not emp_userids:
            return _empty_response(page, page_size)

        # ---- Load leave records for the year ----
        lr_conditions = [
            LeaveRecord.start_time >= year_start_ms,
            LeaveRecord.start_time <= year_end_ms,
            LeaveRecord.userid.in_(emp_userids),
        ]
        if leave_types:
            lr_conditions.append(LeaveRecord.leave_type.in_(leave_types))

        lr_query = select(LeaveRecord).where(and_(*lr_conditions))
        lr_result = await session.execute(lr_query)
        records = lr_result.scalars().all()

    # ---- Aggregate per employee per month ----
    # { userid: { month(1-12): total_value } }
    emp_monthly: Dict[str, Dict[int, float]] = {}
    total_count = 0  # total person-times (record count)
    total_days_all = 0.0  # total days across all records
    annual_days_all = 0.0  # annual leave days

    for rec in records:
        uid = rec.userid
        if uid not in emp_userids:
            continue

        # Determine month from start_time
        dt = _ms_to_datetime(rec.start_time)
        month = dt.month

        # Look up hours_in_per_day from leave type
        hpd = 800
        if rec.leave_code and rec.leave_code in type_map:
            hpd = type_map[rec.leave_code].hours_in_per_day or 800

        value = _convert_duration(rec.duration_percent, rec.duration_unit, unit, hpd)

        if uid not in emp_monthly:
            emp_monthly[uid] = {}
        emp_monthly[uid][month] = emp_monthly[uid].get(month, 0.0) + value

        total_count += 1

        # Compute stats in the requested unit
        total_days_all += value

        if rec.leave_type and "年假" in rec.leave_type:
            annual_days_all += value

    # ---- Build row list ----
    rows = []
    for uid, monthly in emp_monthly.items():
        emp = emp_map.get(uid)
        if emp is None:
            continue
        months = [round(monthly.get(m, 0.0), 1) for m in range(1, 13)]
        total = round(sum(months), 1)
        rows.append({
            "employeeId": uid,
            "name": emp.name,
            "dept": emp.dept_name or "",
            "avatar": emp.avatar,
            "months": months,
            "total": total,
        })

    # ---- Sorting ----
    reverse = sort_order == "desc"
    if sort_by == "total":
        rows.sort(key=lambda r: r["total"], reverse=reverse)
    else:
        # Default: sort by name
        rows.sort(key=lambda r: r["name"], reverse=reverse)

    # ---- Statistics ----
    unique_persons = len(rows)
    avg_days = round(total_days_all / unique_persons, 1) if unique_persons else 0.0
    annual_ratio = round(
        (annual_days_all / total_days_all * 100) if total_days_all else 0.0, 1
    )

    stats = {
        "totalCount": total_count,
        "totalDays": round(total_days_all, 1),
        "avgDays": avg_days,
        "annualRatio": annual_ratio,
        "annualDays": round(annual_days_all, 1),
    }

    # ---- Summary row (before pagination, across ALL matching employees) ----
    summary_months = [0.0] * 12
    summary_total = 0.0
    for row in rows:
        for i in range(12):
            summary_months[i] += row["months"][i]
        summary_total += row["total"]
    summary_months = [round(v, 1) for v in summary_months]

    summary = {
        "personCount": unique_persons,
        "months": summary_months,
        "total": round(summary_total, 1),
    }

    # ---- Pagination ----
    total_items = len(rows)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_rows = rows[start_idx:end_idx]

    pagination = {
        "page": page,
        "pageSize": page_size,
        "total": total_items,
    }

    return {
        "stats": stats,
        "list": paged_rows,
        "summary": summary,
        "pagination": pagination,
    }


def _empty_response(page: int, page_size: int) -> dict:
    """Return an empty response structure."""
    return {
        "stats": {
            "totalCount": 0,
            "totalDays": 0.0,
            "avgDays": 0.0,
            "annualRatio": 0.0,
            "annualDays": 0.0,
        },
        "list": [],
        "summary": {
            "personCount": 0,
            "months": [0.0] * 12,
            "total": 0.0,
        },
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": 0,
        },
    }


# ---------------------------------------------------------------------------
# Daily detail
# ---------------------------------------------------------------------------

async def get_daily_detail(
    employee_id: str,
    year: int,
    month: int,
) -> dict:
    """
    Get leave details for a specific employee in a specific month.

    Returns a dict matching DailyDetailResponse schema:
    {
        employee: { name, dept, avatar },
        records: [{ date, startTime, endTime, hours, leaveType, status }],
        summary: { totalDays, totalHours },
    }
    """
    start_ms, end_ms = _month_range_ms(year, month)
    type_map = await _get_leave_type_map()

    async with async_session() as session:
        # Fetch employee info
        emp_result = await session.execute(
            select(Employee).where(Employee.userid == employee_id)
        )
        emp = emp_result.scalar_one_or_none()

        # Fetch leave records that overlap with the month (handles cross-month records)
        lr_result = await session.execute(
            select(LeaveRecord).where(
                and_(
                    LeaveRecord.userid == employee_id,
                    LeaveRecord.end_time >= start_ms,
                    LeaveRecord.start_time <= end_ms,
                )
            ).order_by(LeaveRecord.start_time)
        )
        records = lr_result.scalars().all()

    employee_info = {
        "name": emp.name if emp else "",
        "dept": emp.dept_name or "" if emp else "",
        "avatar": emp.avatar if emp else None,
    }

    detail_records = []
    total_days = 0.0
    total_hours = 0.0

    # Month boundaries for clamping cross-month records
    _, last_day = calendar.monthrange(year, month)
    month_start_date = date_type(year, month, 1)
    month_end_date = date_type(year, month, last_day)

    for rec in records:
        start_dt = _ms_to_datetime(rec.start_time)
        end_dt = _ms_to_datetime(rec.end_time)

        # Look up hours_in_per_day for unit conversion
        hpd = 800
        if rec.leave_code and rec.leave_code in type_map:
            hpd = type_map[rec.leave_code].hours_in_per_day or 800

        hours = _convert_duration(rec.duration_percent, rec.duration_unit, "hour", hpd)
        days = _convert_duration(rec.duration_percent, rec.duration_unit, "day", hpd)

        total_days += days
        total_hours += hours

        # Expand multi-day records into per-day entries
        rec_start_date = start_dt.date()
        rec_end_date = end_dt.date()

        # 计算请假时间段内的工作日数
        workday_count = 0
        tmp = rec_start_date
        while tmp <= rec_end_date:
            if _is_workday(tmp):
                workday_count += 1
            tmp += timedelta(days=1)

        hours_per_day = round(hours / workday_count, 1) if workday_count > 0 else round(hours, 1)

        # Clamp to current month boundaries
        day_from = max(rec_start_date, month_start_date)
        day_to = min(rec_end_date, month_end_date)

        current = day_from
        while current <= day_to:
            if not _is_workday(current):
                current += timedelta(days=1)
                continue  # 跳过非工作日

            if current == rec_start_date:
                start_time_str = start_dt.strftime("%H:%M")
            else:
                start_time_str = "09:00"

            if current == rec_end_date:
                end_time_str = end_dt.strftime("%H:%M")
            else:
                end_time_str = "18:00"

            detail_records.append({
                "date": current.isoformat(),
                "startTime": start_time_str,
                "endTime": end_time_str,
                "hours": hours_per_day,
                "leaveType": rec.leave_type or "请假",
                "status": rec.status or "已审批",
            })
            current += timedelta(days=1)

    detail_records.sort(key=lambda r: r["date"])

    return {
        "employee": employee_info,
        "records": detail_records,
        "summary": {
            "totalDays": round(total_days, 1),
            "totalHours": round(total_hours, 1),
        },
    }


# ---------------------------------------------------------------------------
# Daily leave count (per-day headcount)
# ---------------------------------------------------------------------------

async def get_daily_leave_count(
    year: int,
    month: int,
    dept_id: Optional[int] = None,
    leave_types: Optional[List[str]] = None,
    employee_name: Optional[str] = None,
) -> dict:
    """
    Count how many employees are on leave for each day of the given month.

    A single leave record spanning multiple days is expanded so that each
    overlapping day is counted.  Cross-month records are clamped to the
    queried month boundaries.

    Returns a dict matching DailyLeaveCountResponse schema.
    """
    month_start_ms, month_end_ms = _month_range_ms(year, month)

    async with async_session() as session:
        # ---- Employee filter (same logic as monthly_summary) ----
        emp_conditions = []
        if dept_id is not None:
            all_dept_ids = await _get_descendant_dept_ids(session, dept_id)
            emp_conditions.append(Employee.dept_id.in_(all_dept_ids))
        if employee_name:
            emp_conditions.append(Employee.name.contains(employee_name))

        emp_query = select(Employee)
        if emp_conditions:
            emp_query = emp_query.where(and_(*emp_conditions))

        emp_result = await session.execute(emp_query)
        employees = emp_result.scalars().all()
        emp_map = {e.userid: e for e in employees}
        emp_userids = set(emp_map.keys())

        if not emp_userids:
            _, last_day = calendar.monthrange(year, month)
            return {
                "todayCount": 0,
                "days": [
                    {"date": f"{year}-{month:02d}-{d:02d}", "count": 0, "employees": []}
                    for d in range(1, last_day + 1)
                ],
                "maxCount": 0,
            }

        # ---- Overlap query: records that intersect with the month ----
        lr_conditions = [
            LeaveRecord.end_time >= month_start_ms,
            LeaveRecord.start_time <= month_end_ms,
            LeaveRecord.userid.in_(emp_userids),
        ]
        if leave_types:
            lr_conditions.append(LeaveRecord.leave_type.in_(leave_types))

        lr_query = select(LeaveRecord).where(and_(*lr_conditions))
        lr_result = await session.execute(lr_query)
        records = lr_result.scalars().all()

    # ---- Expand each record to individual days ----
    # day_users: { date_type -> { userid: (name, dept, leaveType) } }
    _, last_day = calendar.monthrange(year, month)
    month_start_date = date_type(year, month, 1)
    month_end_date = date_type(year, month, last_day)

    day_users: Dict[date_type, Dict[str, Tuple[str, str, str]]] = {}

    for rec in records:
        uid = rec.userid
        if uid not in emp_userids:
            continue

        rec_start = _ms_to_datetime(rec.start_time).date()
        rec_end = _ms_to_datetime(rec.end_time).date()

        # Clamp to month boundaries
        day_from = max(rec_start, month_start_date)
        day_to = min(rec_end, month_end_date)

        emp = emp_map.get(uid)
        emp_name = emp.name if emp else ""
        emp_dept = emp.dept_name or "" if emp else ""
        leave_type_name = rec.leave_type or "请假"

        current = day_from
        while current <= day_to:
            if _is_workday(current):  # 只在工作日统计
                if current not in day_users:
                    day_users[current] = {}
                # Use userid as key to deduplicate (same person, same day)
                # Keep the first leave type encountered for display
                if uid not in day_users[current]:
                    day_users[current][uid] = (emp_name, emp_dept, leave_type_name)
            current += timedelta(days=1)

    # ---- Build response ----
    days = []
    max_count = 0
    today = date_type.today()
    today_count = 0

    for d in range(1, last_day + 1):
        current_date = date_type(year, month, d)
        date_str = current_date.isoformat()
        users = day_users.get(current_date, {})
        count = len(users)
        if count > max_count:
            max_count = count

        if current_date == today:
            today_count = count

        employees_list = [
            {"name": name, "dept": dept, "leaveType": lt}
            for name, dept, lt in users.values()
        ]
        # Sort by name for consistent display
        employees_list.sort(key=lambda e: e["name"])

        days.append({
            "date": date_str,
            "count": count,
            "employees": employees_list,
        })

    return {
        "todayCount": today_count,
        "days": days,
        "maxCount": max_count,
    }
