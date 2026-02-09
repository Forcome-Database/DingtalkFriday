"""
Leave data API router.

GET /api/leave/monthly-summary
GET /api/leave/daily-detail
GET /api/leave/types
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.auth import get_current_user
from app.config import settings
from app.database import async_session
from app.models import LeaveType
from app.schemas import (
    DailyDetailResponse,
    DailyLeaveCountResponse,
    LeaveTypeOut,
    MonthlySummaryResponse,
)
from app.services.leave import get_daily_detail, get_daily_leave_count, get_monthly_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leave", tags=["leave"])


@router.get("/monthly-summary", response_model=MonthlySummaryResponse)
async def monthly_summary(
    year: int = Query(..., description="Year to query"),
    deptId: Optional[int] = Query(default=None, description="Department ID filter"),
    leaveTypes: Optional[str] = Query(
        default=None,
        description="Comma-separated leave type names (e.g. '年假,事假')",
    ),
    employeeName: Optional[str] = Query(
        default=None, description="Employee name keyword"
    ),
    unit: str = Query(default="day", description="Unit: day or hour"),
    page: int = Query(default=1, ge=1, description="Page number"),
    pageSize: int = Query(default=10, ge=1, le=100, description="Page size"),
    sortBy: str = Query(default="name", description="Sort field: name or total"),
    sortOrder: str = Query(default="asc", description="Sort order: asc or desc"),
    _user=Depends(get_current_user),
):
    """
    Get monthly leave summary with pagination, filtering, and sorting.
    """
    # Parse comma-separated leave types
    leave_type_list: Optional[List[str]] = None
    if leaveTypes:
        leave_type_list = [t.strip() for t in leaveTypes.split(",") if t.strip()]

    result = await get_monthly_summary(
        year=year,
        dept_id=deptId,
        leave_types=leave_type_list,
        employee_name=employeeName,
        unit=unit,
        page=page,
        page_size=pageSize,
        sort_by=sortBy,
        sort_order=sortOrder,
    )
    return result


@router.get("/daily-detail", response_model=DailyDetailResponse)
async def daily_detail(
    employeeId: str = Query(..., description="Employee userid"),
    year: int = Query(..., description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    _user=Depends(get_current_user),
):
    """
    Get daily leave detail for a specific employee in a specific month.
    """
    result = await get_daily_detail(
        employee_id=employeeId,
        year=year,
        month=month,
    )
    return result


@router.get("/daily-leave-count", response_model=DailyLeaveCountResponse)
async def daily_leave_count(
    year: int = Query(..., description="Year to query"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    deptId: Optional[int] = Query(default=None, description="Department ID filter"),
    leaveTypes: Optional[str] = Query(
        default=None,
        description="Comma-separated leave type names (e.g. '年假,事假')",
    ),
    employeeName: Optional[str] = Query(
        default=None, description="Employee name keyword"
    ),
    _user=Depends(get_current_user),
):
    """
    Get per-day leave headcount for a given month.
    """
    leave_type_list: Optional[List[str]] = None
    if leaveTypes:
        leave_type_list = [t.strip() for t in leaveTypes.split(",") if t.strip()]

    result = await get_daily_leave_count(
        year=year,
        month=month,
        dept_id=deptId,
        leave_types=leave_type_list,
        employee_name=employeeName,
    )
    return result


@router.get("/types", response_model=List[LeaveTypeOut])
async def leave_types(_user=Depends(get_current_user)):
    """
    Get the list of leave types from local DB.
    If LEAVE_TYPE_NAMES is configured, only return those types.
    """
    # Parse whitelist from config
    allowed_names = []
    if settings.leave_type_names:
        allowed_names = [n.strip() for n in settings.leave_type_names.split(",") if n.strip()]

    async with async_session() as session:
        query = select(LeaveType)
        if allowed_names:
            query = query.where(LeaveType.leave_name.in_(allowed_names))
        result = await session.execute(query)
        types = result.scalars().all()

    # Sort by whitelist order if configured
    if allowed_names:
        order = {name: i for i, name in enumerate(allowed_names)}
        types = sorted(types, key=lambda t: order.get(t.leave_name, 999))

    return [
        LeaveTypeOut(
            leave_code=t.leave_code,
            leave_name=t.leave_name,
            leave_view_unit=t.leave_view_unit,
            hours_in_per_day=t.hours_in_per_day or 800,
        )
        for t in types
    ]
