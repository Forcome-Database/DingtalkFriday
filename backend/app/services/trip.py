"""
Trip data query service.

Provides monthly summary, daily detail, today's list, and stats
for business trip (出差) and out-of-office (外出) records.
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Set

from sqlalchemy import select, func, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Department, Employee, TripRecord
from app.services.dept_utils import get_descendant_dept_ids

logger = logging.getLogger(__name__)


async def get_trip_monthly_summary(
    year: int,
    dept_id: Optional[int] = None,
    trip_type: Optional[str] = None,
    employee_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
) -> dict:
    """Get monthly summary of trip/outing data for all employees."""
    async with async_session() as session:
        # Build employee filter
        emp_query = select(Employee)
        if dept_id:
            dept_ids = await get_descendant_dept_ids(session, dept_id)
            emp_query = emp_query.where(Employee.dept_id.in_(dept_ids))
        if employee_name:
            emp_query = emp_query.where(Employee.name.contains(employee_name))

        emp_result = await session.execute(emp_query)
        employees = emp_result.scalars().all()
        emp_map = {e.userid: e for e in employees}
        emp_ids = list(emp_map.keys())

        if not emp_ids:
            return {
                "stats": {"totalCount": 0, "totalDays": 0, "todayTripCount": 0, "todayOutingCount": 0},
                "list": [],
                "summary": {"tripDays": 0, "outingDays": 0, "totalDays": 0, "months": {}},
                "pagination": {"page": page, "pageSize": page_size, "total": 0, "totalPages": 0},
            }

        # Date range for the year
        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"

        # Query trip records
        trip_query = select(TripRecord).where(
            TripRecord.userid.in_(emp_ids),
            TripRecord.work_date >= year_start,
            TripRecord.work_date <= year_end,
        )
        if trip_type:
            trip_query = trip_query.where(TripRecord.tag_name == trip_type)

        result = await session.execute(trip_query)
        records = result.scalars().all()

        # Aggregate per employee
        emp_data: Dict[str, dict] = {}
        for rec in records:
            if rec.userid not in emp_data:
                emp = emp_map[rec.userid]
                emp_data[rec.userid] = {
                    "employeeId": rec.userid,
                    "employeeName": emp.name,
                    "deptName": emp.dept_name,
                    "tripDays": 0.0,
                    "outingDays": 0.0,
                    "tripProcs": set(),
                    "outingProcs": set(),
                    "months": {str(m): 0.0 for m in range(1, 13)},
                }

            d = emp_data[rec.userid]
            hours = rec.duration_hours or 0
            days = hours / 8.0
            month_key = str(int(rec.work_date[5:7]))  # "04" -> "4"

            if rec.tag_name == "出差":
                d["tripDays"] += days
                d["tripProcs"].add(rec.proc_inst_id)
            else:
                d["outingDays"] += days
                d["outingProcs"].add(rec.proc_inst_id)
            d["months"][month_key] = round(d["months"][month_key] + days, 1)

        # Build rows
        rows = []
        for uid, d in emp_data.items():
            rows.append({
                "employeeId": d["employeeId"],
                "employeeName": d["employeeName"],
                "deptName": d["deptName"],
                "tripDays": round(d["tripDays"], 1),
                "outingDays": round(d["outingDays"], 1),
                "totalDays": round(d["tripDays"] + d["outingDays"], 1),
                "tripCount": len(d["tripProcs"]),
                "outingCount": len(d["outingProcs"]),
                "months": {k: round(v, 1) for k, v in d["months"].items()},
            })

        # Sort
        if sort_by and sort_by in ("totalDays", "tripDays", "outingDays", "employeeName"):
            reverse = sort_order == "desc"
            rows.sort(key=lambda r: r.get(sort_by, 0), reverse=reverse)
        else:
            rows.sort(key=lambda r: r["totalDays"], reverse=True)

        # Summary row
        summary_months = {str(m): 0.0 for m in range(1, 13)}
        total_trip = 0.0
        total_outing = 0.0
        for r in rows:
            total_trip += r["tripDays"]
            total_outing += r["outingDays"]
            for m, v in r["months"].items():
                summary_months[m] = round(summary_months[m] + v, 1)

        # Today stats
        today_str = date.today().isoformat()
        today_result = await session.execute(
            select(TripRecord).where(
                TripRecord.userid.in_(emp_ids),
                TripRecord.work_date == today_str,
            )
        )
        today_records = today_result.scalars().all()
        today_trip_users = set()
        today_outing_users = set()
        for r in today_records:
            if r.tag_name == "出差":
                today_trip_users.add(r.userid)
            else:
                today_outing_users.add(r.userid)

        # Total count: distinct proc_inst_id per user
        all_procs = set()
        for d in emp_data.values():
            all_procs.update(d["tripProcs"])
            all_procs.update(d["outingProcs"])

        # Pagination
        total = len(rows)
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        start = (page - 1) * page_size
        page_rows = rows[start: start + page_size]

        return {
            "stats": {
                "totalCount": len(all_procs),
                "totalDays": round(total_trip + total_outing, 1),
                "todayTripCount": len(today_trip_users),
                "todayOutingCount": len(today_outing_users),
            },
            "list": page_rows,
            "summary": {
                "tripDays": round(total_trip, 1),
                "outingDays": round(total_outing, 1),
                "totalDays": round(total_trip + total_outing, 1),
                "months": summary_months,
            },
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": total,
                "totalPages": total_pages,
            },
        }


async def get_trip_daily_detail(
    employee_id: str,
    year: int,
    month: int,
) -> dict:
    """Get daily trip records for one employee in a given month."""
    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year}-12-31"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    async with async_session() as session:
        # Get employee name
        emp_result = await session.execute(
            select(Employee.name).where(Employee.userid == employee_id)
        )
        emp_name = emp_result.scalar_one_or_none() or employee_id

        result = await session.execute(
            select(TripRecord).where(
                TripRecord.userid == employee_id,
                TripRecord.work_date >= month_start,
                TripRecord.work_date < month_end,
            ).order_by(TripRecord.work_date)
        )
        records = result.scalars().all()

        return {
            "employeeName": emp_name,
            "records": [
                {
                    "date": r.work_date,
                    "tagName": r.tag_name,
                    "durationHours": r.duration_hours,
                    "beginTime": r.begin_time,
                    "endTime": r.end_time,
                }
                for r in records
            ],
        }


async def get_trip_today(
    dept_id: Optional[int] = None,
    trip_type: Optional[str] = None,
    employee_name: Optional[str] = None,
) -> dict:
    """Get today's trip/outing records."""
    today_str = date.today().isoformat()

    async with async_session() as session:
        query = (
            select(TripRecord, Employee)
            .join(Employee, TripRecord.userid == Employee.userid)
            .where(TripRecord.work_date == today_str)
        )

        if dept_id:
            dept_ids = await get_descendant_dept_ids(session, dept_id)
            query = query.where(Employee.dept_id.in_(dept_ids))
        if trip_type:
            query = query.where(TripRecord.tag_name == trip_type)
        if employee_name:
            query = query.where(Employee.name.contains(employee_name))

        result = await session.execute(query)
        rows = result.all()

        return {
            "list": [
                {
                    "employeeId": trip.userid,
                    "employeeName": emp.name,
                    "deptName": emp.dept_name,
                    "tagName": trip.tag_name,
                    "beginTime": trip.begin_time,
                    "endTime": trip.end_time,
                    "durationHours": trip.duration_hours,
                }
                for trip, emp in rows
            ],
        }


async def get_trip_daily_count(
    year: int,
    month: int,
    dept_id: Optional[int] = None,
    trip_type: Optional[str] = None,
    employee_name: Optional[str] = None,
) -> dict:
    """Get daily trip headcount for heatmap display."""
    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1}-01-01"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    async with async_session() as session:
        query = (
            select(
                TripRecord.work_date,
                func.count(distinct(TripRecord.userid)).label("count"),
            )
            .join(Employee, TripRecord.userid == Employee.userid)
            .where(
                TripRecord.work_date >= month_start,
                TripRecord.work_date < month_end,
            )
            .group_by(TripRecord.work_date)
        )

        if dept_id:
            dept_ids = await get_descendant_dept_ids(session, dept_id)
            query = query.where(Employee.dept_id.in_(dept_ids))
        if trip_type:
            query = query.where(TripRecord.tag_name == trip_type)
        if employee_name:
            query = query.where(Employee.name.contains(employee_name))

        result = await session.execute(query)
        rows = result.all()

        return {
            "days": {row.work_date: row.count for row in rows},
        }
