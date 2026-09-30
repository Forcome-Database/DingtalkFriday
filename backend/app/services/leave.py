"""
Leave data query service.

Provides monthly summary aggregation and daily detail queries
from the locally synced leave_record + employee tables.
"""

import calendar
import logging
from datetime import datetime, date as date_type, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, and_

from app.database import async_session
from app.models import Employee, LeaveRecord, LeaveType
from app.services.dept_utils import get_descendant_dept_ids
from app.services.durations import BUSINESS_TIMEZONE, allocate_hours_by_date, business_today

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
    return datetime.fromtimestamp(ms / 1000, BUSINESS_TIMEZONE)


def _month_range_ms(year: int, month: int) -> Tuple[int, int]:
    """Return (start_ms, end_ms) for the given year-month."""
    _, last_day = calendar.monthrange(year, month)
    start = int(datetime(year, month, 1, tzinfo=BUSINESS_TIMEZONE).timestamp() * 1000)
    next_month = datetime(year, month, last_day, tzinfo=BUSINESS_TIMEZONE) + timedelta(days=1)
    end = int(next_month.timestamp() * 1000) - 1
    return start, end


def _year_range_ms(year: int) -> Tuple[int, int]:
    """Return (start_ms, end_ms) for the given year."""
    start = int(datetime(year, 1, 1, tzinfo=BUSINESS_TIMEZONE).timestamp() * 1000)
    end = int(datetime(year + 1, 1, 1, tzinfo=BUSINESS_TIMEZONE).timestamp() * 1000) - 1
    return start, end


# 按自然日计算的假期类型关键词（产假、婚假等，包含周末和节假日）
CALENDAR_DAY_LEAVE_KEYWORDS = ("产假", "婚假")


def _is_calendar_day_leave(leave_type: Optional[str]) -> bool:
    """判断是否为按自然日计算的假期类型（产假、婚假等）。"""
    if not leave_type:
        return False
    return any(kw in leave_type for kw in CALENDAR_DAY_LEAVE_KEYWORDS)


def _prorate_duration(
    rec,
    period_start_date: date_type,
    period_end_date: date_type,
    type_map: Dict[str, "LeaveType"],
    unit: str = "day",
) -> float:
    """Sum the same daily allocation used by details and daily headcounts."""
    if _ms_to_datetime(rec.end_time).date() < period_start_date or _ms_to_datetime(rec.start_time).date() > period_end_date:
        return 0.0
    hours = sum(
        value for day, value in _record_daily_hours(rec, type_map).items()
        if period_start_date <= day <= period_end_date
    )
    return hours if unit == "hour" else hours / 8.0


def _record_daily_hours(rec, type_map: Dict[str, LeaveType]) -> Dict[date_type, float]:
    hpd = 800
    if rec.leave_code and rec.leave_code in type_map:
        hpd = type_map[rec.leave_code].hours_in_per_day or 800
    total_hours = _convert_duration(rec.duration_percent, rec.duration_unit, "hour", hpd)
    return allocate_hours_by_date(
        _ms_to_datetime(rec.start_time),
        _ms_to_datetime(rec.end_time),
        total_hours,
        calendar_days=_is_calendar_day_leave(rec.leave_type),
        is_workday=_is_workday,
        day_unit=rec.duration_unit == "percent_day",
    )


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
    elif duration_unit == "percent_day":
        # percent_day: raw 是钉钉天数，乘以钉钉的 hpd 得到总小时
        total_hours = raw * hpd
    else:
        raise ValueError(f"Unsupported leave duration unit: {duration_unit}")

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
            all_dept_ids = await get_descendant_dept_ids(session, dept_id)
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

        # ---- Load leave records (overlap query: records that intersect the year) ----
        lr_conditions = [
            LeaveRecord.start_time <= year_end_ms,
            LeaveRecord.end_time >= year_start_ms,
            LeaveRecord.userid.in_(emp_userids),
            LeaveRecord.status == "已审批",
        ]
        if leave_types is not None:
            lr_conditions.append(LeaveRecord.leave_type.in_(leave_types))

        lr_query = select(LeaveRecord).where(and_(*lr_conditions))
        lr_result = await session.execute(lr_query)
        records = lr_result.scalars().all()

    # ---- Aggregate per employee per month (with proration) ----
    # { userid: { month(1-12): total_value } }
    emp_monthly: Dict[str, Dict[int, float]] = {}
    total_count = 0  # total person-times (record count)
    total_days_all = 0.0  # total days across all records
    annual_days_all = 0.0  # annual leave days

    for rec in records:
        uid = rec.userid
        if uid not in emp_userids:
            continue

        counted = False
        for day, hours in _record_daily_hours(rec, type_map).items():
            if day.year != year:
                continue
            month = day.month
            value = hours if unit == "hour" else hours / 8.0
            if value <= 0:
                continue
            counted = True

            if uid not in emp_monthly:
                emp_monthly[uid] = {}
            emp_monthly[uid][month] = emp_monthly[uid].get(month, 0.0) + value

            total_days_all += value

            if rec.leave_type and "年假" in rec.leave_type:
                annual_days_all += value
        total_count += int(counted)

    # ---- Build row list ----
    rows = []
    for uid, monthly in emp_monthly.items():
        emp = emp_map.get(uid)
        if emp is None:
            continue
        months = [round(monthly.get(m, 0.0), 1) for m in range(1, 13)]
        total = round(sum(monthly.values()), 1)
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
    for monthly in emp_monthly.values():
        for month, value in monthly.items():
            summary_months[month - 1] += value
    summary_months = [round(v, 1) for v in summary_months]

    summary = {
        "personCount": unique_persons,
        "months": summary_months,
        "total": round(total_days_all, 1),
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
    leave_types: Optional[List[str]] = None,
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
        conditions = [
            LeaveRecord.userid == employee_id,
            LeaveRecord.end_time >= start_ms,
            LeaveRecord.start_time <= end_ms,
            LeaveRecord.status == "已审批",
        ]
        if leave_types is not None:
            conditions.append(LeaveRecord.leave_type.in_(leave_types))
        lr_result = await session.execute(select(LeaveRecord).where(*conditions).order_by(LeaveRecord.start_time))
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

        rec_start_date = start_dt.date()
        rec_end_date = end_dt.date()
        for current, day_hours in _record_daily_hours(rec, type_map).items():
            if not month_start_date <= current <= month_end_date or day_hours <= 0:
                continue
            total_hours += day_hours
            total_days += day_hours / 8.0

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
                "hours": day_hours,
                "leaveType": rec.leave_type or "请假",
                "status": rec.status or "已审批",
            })

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
    type_map = await _get_leave_type_map()

    async with async_session() as session:
        # ---- Employee filter (same logic as monthly_summary) ----
        emp_conditions = []
        if dept_id is not None:
            all_dept_ids = await get_descendant_dept_ids(session, dept_id)
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
            LeaveRecord.status == "已审批",
        ]
        if leave_types is not None:
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

        emp = emp_map.get(uid)
        emp_name = emp.name if emp else ""
        emp_dept = emp.dept_name or "" if emp else ""
        leave_type_name = rec.leave_type or "请假"

        for current, hours in _record_daily_hours(rec, type_map).items():
            if not month_start_date <= current <= month_end_date or hours <= 0:
                continue
            if current not in day_users:
                day_users[current] = {}
            if uid not in day_users[current]:
                day_users[current][uid] = (emp_name, emp_dept, leave_type_name)

    # ---- Build response ----
    days = []
    max_count = 0
    today = business_today()
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


# ---------------------------------------------------------------------------
# Today leave detail
# ---------------------------------------------------------------------------

async def get_today_leave_detail(
    dept_id: Optional[int] = None,
    leave_types: Optional[List[str]] = None,
    employee_name: Optional[str] = None,
    target_date: Optional[date_type] = None,
) -> dict:
    """
    Get detailed leave records for a specific date (defaults to today).

    Returns a dict matching TodayLeaveDetailResponse schema:
    {
        date: str   -- the queried date (YYYY-MM-DD),
        count: int  -- distinct person count on leave,
        records: [{ userid, name, avatar, deptName, leaveType, leaveCode,
                     startTime, endTime, durationPercent, durationUnit,
                     durationDisplay, timeDisplay, status }],
    }
    """
    today = target_date or business_today()
    today_start = datetime.combine(today, datetime.min.time(), BUSINESS_TIMEZONE)
    today_start_ms = int(today_start.timestamp() * 1000)
    today_end_ms = int((today_start + timedelta(days=1)).timestamp() * 1000) - 1

    async with async_session() as session:
        # Employee filter (same logic as get_daily_leave_count)
        emp_conditions = []
        if dept_id is not None:
            all_dept_ids = await get_descendant_dept_ids(session, dept_id)
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
            return {"date": today.isoformat(), "count": 0, "records": []}

        # Overlap query: records that intersect with today
        lr_conditions = [
            LeaveRecord.end_time >= today_start_ms,
            LeaveRecord.start_time <= today_end_ms,
            LeaveRecord.userid.in_(emp_userids),
            LeaveRecord.status == "已审批",
        ]
        if leave_types is not None:
            lr_conditions.append(LeaveRecord.leave_type.in_(leave_types))

        lr_query = select(LeaveRecord).where(and_(*lr_conditions)).order_by(LeaveRecord.start_time)
        lr_result = await session.execute(lr_query)
        records = lr_result.scalars().all()

    type_map = await _get_leave_type_map()
    result_records = []
    person_ids = set()

    for rec in records:
        uid = rec.userid
        if uid not in emp_userids:
            continue

        emp = emp_map.get(uid)
        if not emp:
            continue

        today_hours = _record_daily_hours(rec, type_map).get(today, 0.0)
        if today_hours <= 0:
            continue

        person_ids.add(uid)

        start_dt = _ms_to_datetime(rec.start_time)
        end_dt = _ms_to_datetime(rec.end_time)
        rec_start_date = start_dt.date()
        rec_end_date = end_dt.date()

        # Build timeDisplay
        if rec_start_date == rec_end_date:
            time_display = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
        elif rec_start_date == today:
            time_display = f"{start_dt.strftime('%H:%M')} - 18:00"
        elif rec_end_date == today:
            time_display = f"09:00 - {end_dt.strftime('%H:%M')}"
        else:
            time_display = "09:00 - 18:00"

        today_hours = round(today_hours, 1)
        if today_hours == int(today_hours):
            duration_display = f"{int(today_hours)}小时"
        else:
            duration_display = f"{today_hours}小时"

        result_records.append({
            "userid": uid,
            "name": emp.name,
            "avatar": emp.avatar,
            "deptName": emp.dept_name or "",
            "leaveType": rec.leave_type or "请假",
            "leaveCode": rec.leave_code,
            "startTime": rec.start_time,
            "endTime": rec.end_time,
            "durationPercent": rec.duration_percent,
            "durationUnit": rec.duration_unit,
            "durationDisplay": duration_display,
            "timeDisplay": time_display,
            "status": rec.status or "已审批",
        })

    result_records.sort(key=lambda r: r["name"])

    return {
        "date": today.isoformat(),
        "count": len(person_ids),
        "records": result_records,
    }
