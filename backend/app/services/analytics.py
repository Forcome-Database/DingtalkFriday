"""
Analytics data service.

Provides aggregation queries for dashboard analytics:
- Monthly leave trend with year-over-year comparison
- Leave type distribution
- Department comparison
- Weekday distribution
- Employee leave ranking
"""

import logging
from collections import defaultdict
from datetime import date as date_type
from typing import Dict, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Department, Employee, LeaveRecord, LeaveType
from app.services.department_stats import build_department_comparison
from app.services.leave import (
    _convert_duration,
    _get_leave_type_map,
    _prorate_duration,
    _record_daily_hours,
    _year_range_ms,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _load_year_records(
    session: AsyncSession,
    year: int,
) -> List[LeaveRecord]:
    """Load all leave records that overlap with the given year (handles cross-year records)."""
    year_start_ms, year_end_ms = _year_range_ms(year)
    result = await session.execute(
        select(LeaveRecord).where(
            and_(
                LeaveRecord.start_time <= year_end_ms,
                LeaveRecord.end_time >= year_start_ms,
                LeaveRecord.status == "已审批",
            )
        )
    )
    return list(result.scalars().all())


def _record_to_days(
    rec: LeaveRecord,
    type_map: Dict[str, LeaveType],
) -> float:
    """Convert a single leave record's duration to days."""
    hpd = 800
    if rec.leave_code and rec.leave_code in type_map:
        hpd = type_map[rec.leave_code].hours_in_per_day or 800
    return _convert_duration(rec.duration_percent, rec.duration_unit, "day", hpd)


# ---------------------------------------------------------------------------
# 1. Monthly trend (year-over-year)
# ---------------------------------------------------------------------------

async def get_monthly_trend(year: int) -> dict:
    """
    Aggregate leave days per month for the given year and the previous year.
    Cross-year/cross-month records are prorated by workday ratio.

    Returns:
        {
            "currentYear":  [{"month": 1, "days": 5.5}, ... x12],
            "previousYear": [{"month": 1, "days": 4.0}, ... x12],
        }
    """
    type_map = await _get_leave_type_map()

    async with async_session() as session:
        current_records = await _load_year_records(session, year)
        previous_records = await _load_year_records(session, year - 1)

    def _aggregate_by_month(records: List[LeaveRecord], target_year: int) -> List[dict]:
        monthly: Dict[int, float] = {m: 0.0 for m in range(1, 13)}
        for rec in records:
            for day, hours in _record_daily_hours(rec, type_map).items():
                if day.year == target_year:
                    monthly[day.month] += hours / 8.0
        return [
            {"month": m, "days": round(monthly[m], 1)}
            for m in range(1, 13)
        ]

    return {
        "currentYear": _aggregate_by_month(current_records, year),
        "previousYear": _aggregate_by_month(previous_records, year - 1),
    }


# ---------------------------------------------------------------------------
# 2. Leave type distribution
# ---------------------------------------------------------------------------

async def get_leave_type_distribution(year: int) -> dict:
    """
    Aggregate leave days by leave type for the given year.
    Cross-year records are prorated to the target year by workday ratio.

    Returns:
        {
            "total": 73.5,
            "items": [
                {"type": "年假", "days": 33.0, "ratio": 44.9},
                ...
            ]
        }
    """
    type_map = await _get_leave_type_map()
    year_start = date_type(year, 1, 1)
    year_end = date_type(year, 12, 31)

    async with async_session() as session:
        records = await _load_year_records(session, year)

    type_days: Dict[str, float] = defaultdict(float)
    for rec in records:
        leave_name = rec.leave_type or "请假"
        days = _prorate_duration(rec, year_start, year_end, type_map, "day")
        type_days[leave_name] += days

    total = sum(type_days.values())
    items = []
    for leave_name, days in sorted(type_days.items(), key=lambda x: -x[1]):
        ratio = round(days / total * 100, 1) if total > 0 else 0.0
        items.append({
            "type": leave_name,
            "days": round(days, 1),
            "ratio": ratio,
        })

    return {
        "total": round(total, 1),
        "items": items,
    }


# ---------------------------------------------------------------------------
# 3. Department comparison
# ---------------------------------------------------------------------------

async def get_department_comparison(year: int, metric: str = "total") -> dict:
    """
    Aggregate leave days by department for the given year.

    Args:
        year: Target year.
        metric: "total" or "avg" (used by frontend for sorting/display).

    Returns:
        {
            "departments": [
                {"name": "研发部", "totalDays": 28.5, "avgDays": 3.2, "headcount": 9},
                ...
            ],
            "average": 16.8
        }
    """
    type_map = await _get_leave_type_map()
    year_start = date_type(year, 1, 1)
    year_end = date_type(year, 12, 31)

    async with async_session() as session:
        # Load all employees to build dept mapping and headcount
        emp_result = await session.execute(select(Employee))
        employees = emp_result.scalars().all()
        dept_result = await session.execute(select(Department))
        departments = dept_result.scalars().all()
        records = await _load_year_records(session, year)

    # Build employee lookup and dept headcount
    emp_map = {e.userid: e for e in employees}
    # Aggregate leave days per department (prorated to target year)
    dept_days: Dict[int, float] = defaultdict(float)
    for rec in records:
        emp = emp_map.get(rec.userid)
        if not emp:
            continue
        days = _prorate_duration(rec, year_start, year_end, type_map, "day")
        dept_days[emp.dept_id] += days

    return build_department_comparison(employees, departments, dept_days, metric)


# ---------------------------------------------------------------------------
# 4. Weekday distribution
# ---------------------------------------------------------------------------

WEEKDAY_LABELS = {
    0: "周一",
    1: "周二",
    2: "周三",
    3: "周四",
    4: "周五",
}


async def get_weekday_distribution(year: int) -> dict:
    """
    Expand each leave record to individual workdays and count occurrences
    per weekday (Monday-Friday).

    Returns:
        {
            "weekdays": [
                {"day": 1, "label": "周一", "count": 18},
                {"day": 2, "label": "周二", "count": 10},
                ...
            ]
        }
    """
    year_start = date_type(year, 1, 1)
    year_end = date_type(year, 12, 31)
    type_map = await _get_leave_type_map()

    async with async_session() as session:
        records = await _load_year_records(session, year)

    # Count occurrences per weekday (0=Mon .. 4=Fri), clamped to target year
    weekday_counts: Dict[int, int] = {i: 0 for i in range(5)}

    for rec in records:
        for day, hours in _record_daily_hours(rec, type_map).items():
            if year_start <= day <= year_end and hours > 0 and day.weekday() in weekday_counts:
                weekday_counts[day.weekday()] += 1

    weekdays = [
        {
            "day": wd + 1,  # 1-based (1=Monday .. 5=Friday)
            "label": WEEKDAY_LABELS[wd],
            "count": weekday_counts[wd],
        }
        for wd in range(5)
    ]

    return {"weekdays": weekdays}


# ---------------------------------------------------------------------------
# 5. Employee leave ranking
# ---------------------------------------------------------------------------

async def get_employee_ranking(year: int, limit: int = 10) -> dict:
    """
    Rank employees by total leave days (descending), with per-type breakdown.

    Args:
        year: Target year.
        limit: Maximum number of employees to return.

    Returns:
        {
            "employees": [
                {
                    "name": "张三", "dept": "研发部", "total": 14.5,
                    "breakdown": [
                        {"type": "年假", "days": 8.0},
                        {"type": "事假", "days": 3.5},
                        ...
                    ]
                },
                ...
            ]
        }
    """
    type_map = await _get_leave_type_map()
    year_start = date_type(year, 1, 1)
    year_end = date_type(year, 12, 31)

    async with async_session() as session:
        emp_result = await session.execute(select(Employee))
        employees = emp_result.scalars().all()
        records = await _load_year_records(session, year)

    emp_map = {e.userid: e for e in employees}

    # { userid: { leave_type_name: total_days } } (prorated to target year)
    emp_type_days: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for rec in records:
        emp = emp_map.get(rec.userid)
        if not emp:
            continue
        leave_name = rec.leave_type or "请假"
        days = _prorate_duration(rec, year_start, year_end, type_map, "day")
        emp_type_days[rec.userid][leave_name] += days

    # Build ranked list
    ranked = []
    for uid, type_days in emp_type_days.items():
        emp = emp_map.get(uid)
        if not emp:
            continue
        total = sum(type_days.values())
        breakdown = [
            {"type": t, "days": round(d, 1)}
            for t, d in sorted(type_days.items(), key=lambda x: -x[1])
        ]
        ranked.append({
            "name": emp.name,
            "dept": emp.dept_name or "",
            "total": round(total, 1),
            "breakdown": breakdown,
        })

    # Sort by total descending and take top N
    ranked.sort(key=lambda r: r["total"], reverse=True)
    ranked = ranked[:limit]

    return {"employees": ranked}
