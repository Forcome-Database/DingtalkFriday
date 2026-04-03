"""
Trip analytics data service.

Provides aggregation queries for trip/outing dashboard analytics:
- Monthly trip trend (出差 vs 外出 dual lines)
- Trip type distribution (出差 vs 外出 ratio)
- Department comparison
- Weekday distribution
- Employee trip ranking
"""

import logging
from collections import defaultdict
from datetime import date as date_type
from typing import Dict, List

from sqlalchemy import select, and_

from app.database import async_session
from app.models import Employee, TripRecord

logger = logging.getLogger(__name__)

WEEKDAY_LABELS = {
    0: "周一",
    1: "周二",
    2: "周三",
    3: "周四",
    4: "周五",
}


async def _load_year_trip_records(year: int) -> List[TripRecord]:
    """Load all trip records whose work_date falls within the given year."""
    async with async_session() as session:
        result = await session.execute(
            select(TripRecord).where(
                and_(
                    TripRecord.work_date >= f"{year}-01-01",
                    TripRecord.work_date <= f"{year}-12-31",
                )
            )
        )
        return list(result.scalars().all())


async def _load_employees() -> Dict[str, Employee]:
    """Load all employees as a {userid: Employee} map."""
    async with async_session() as session:
        result = await session.execute(select(Employee))
        return {e.userid: e for e in result.scalars().all()}


def _hours_to_days(hours: float) -> float:
    """Convert duration_hours to days (8 hours = 1 day)."""
    return hours / 8.0


# ---------------------------------------------------------------------------
# 1. Monthly trend (出差 vs 外出 dual lines)
# ---------------------------------------------------------------------------

async def get_trip_monthly_trend(year: int) -> dict:
    records = await _load_year_trip_records(year)

    trip_monthly: Dict[int, float] = {m: 0.0 for m in range(1, 13)}
    outing_monthly: Dict[int, float] = {m: 0.0 for m in range(1, 13)}

    for rec in records:
        month = int(rec.work_date[5:7])
        days = _hours_to_days(rec.duration_hours)
        if rec.tag_name == "出差":
            trip_monthly[month] += days
        else:
            outing_monthly[month] += days

    return {
        "trip": [{"month": m, "days": round(trip_monthly[m], 1)} for m in range(1, 13)],
        "outing": [{"month": m, "days": round(outing_monthly[m], 1)} for m in range(1, 13)],
    }


# ---------------------------------------------------------------------------
# 2. Trip type distribution (出差 vs 外出)
# ---------------------------------------------------------------------------

async def get_trip_type_distribution(year: int) -> dict:
    records = await _load_year_trip_records(year)

    type_days: Dict[str, float] = defaultdict(float)
    for rec in records:
        type_days[rec.tag_name] += _hours_to_days(rec.duration_hours)

    total = sum(type_days.values())
    items = []
    for tag_name, days in sorted(type_days.items(), key=lambda x: -x[1]):
        ratio = round(days / total * 100, 1) if total > 0 else 0.0
        items.append({"type": tag_name, "days": round(days, 1), "ratio": ratio})

    return {"total": round(total, 1), "items": items}


# ---------------------------------------------------------------------------
# 3. Department comparison
# ---------------------------------------------------------------------------

async def get_trip_department_comparison(year: int, metric: str = "total") -> dict:
    records = await _load_year_trip_records(year)
    emp_map = await _load_employees()

    dept_headcount: Dict[str, int] = defaultdict(int)
    for emp in emp_map.values():
        dept_headcount[emp.dept_name or "未分配"] += 1

    dept_days: Dict[str, float] = defaultdict(float)
    for rec in records:
        emp = emp_map.get(rec.userid)
        if not emp:
            continue
        dept_name = emp.dept_name or "未分配"
        dept_days[dept_name] += _hours_to_days(rec.duration_hours)

    departments = []
    for dept_name, headcount in dept_headcount.items():
        total_days = dept_days.get(dept_name, 0.0)
        avg_days = total_days / headcount if headcount > 0 else 0.0
        departments.append({
            "name": dept_name,
            "totalDays": round(total_days, 1),
            "avgDays": round(avg_days, 1),
            "headcount": headcount,
        })

    sort_key = "avgDays" if metric == "avg" else "totalDays"
    departments.sort(key=lambda d: d[sort_key], reverse=True)

    avg = 0.0
    if departments:
        avg = sum(d[sort_key] for d in departments) / len(departments)

    return {"departments": departments, "average": round(avg, 1)}


# ---------------------------------------------------------------------------
# 4. Weekday distribution
# ---------------------------------------------------------------------------

async def get_trip_weekday_distribution(year: int) -> dict:
    records = await _load_year_trip_records(year)

    weekday_counts: Dict[int, int] = {i: 0 for i in range(5)}

    for rec in records:
        parts = rec.work_date.split("-")
        d = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        wd = d.weekday()
        if wd in weekday_counts:
            weekday_counts[wd] += 1

    weekdays = [
        {"day": wd + 1, "label": WEEKDAY_LABELS[wd], "count": weekday_counts[wd]}
        for wd in range(5)
    ]
    return {"weekdays": weekdays}


# ---------------------------------------------------------------------------
# 5. Employee trip ranking
# ---------------------------------------------------------------------------

async def get_trip_employee_ranking(year: int, limit: int = 10) -> dict:
    records = await _load_year_trip_records(year)
    emp_map = await _load_employees()

    # { userid: { tag_name: total_days } }
    emp_type_days: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for rec in records:
        if rec.userid not in emp_map:
            continue
        emp_type_days[rec.userid][rec.tag_name] += _hours_to_days(rec.duration_hours)

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

    ranked.sort(key=lambda r: r["total"], reverse=True)
    ranked = ranked[:limit]

    return {"employees": ranked}
