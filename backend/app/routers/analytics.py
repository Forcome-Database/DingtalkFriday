"""
Analytics API router.

GET /api/analytics/monthly-trend
GET /api/analytics/leave-type-distribution
GET /api/analytics/department-comparison
GET /api/analytics/weekday-distribution
GET /api/analytics/employee-ranking
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user

from app.schemas import (
    DepartmentComparisonResponse,
    EmployeeRankingResponse,
    LeaveTypeDistributionResponse,
    MonthlyTrendResponse,
    WeekdayDistributionResponse,
)
from app.services.analytics import (
    get_department_comparison,
    get_employee_ranking,
    get_leave_type_distribution,
    get_monthly_trend,
    get_weekday_distribution,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
async def monthly_trend(
    year: int = Query(
        default=None,
        description="Year to query (defaults to current year)",
    ),
    _user=Depends(get_current_user),
):
    """
    Get monthly leave trend with year-over-year comparison.
    Returns aggregated leave days per month for the given year and the previous year.
    """
    if year is None:
        year = datetime.now().year
    result = await get_monthly_trend(year=year)
    return result


@router.get("/leave-type-distribution", response_model=LeaveTypeDistributionResponse)
async def leave_type_distribution(
    year: int = Query(
        default=None,
        description="Year to query (defaults to current year)",
    ),
    _user=Depends(get_current_user),
):
    """
    Get leave type distribution (for ring/donut chart).
    Returns total days and per-type breakdown with ratios.
    """
    if year is None:
        year = datetime.now().year
    result = await get_leave_type_distribution(year=year)
    return result


@router.get("/department-comparison", response_model=DepartmentComparisonResponse)
async def department_comparison(
    year: int = Query(
        default=None,
        description="Year to query (defaults to current year)",
    ),
    metric: str = Query(
        default="total",
        description="Sort metric: 'total' for total days or 'avg' for average days",
    ),
    _user=Depends(get_current_user),
):
    """
    Get department leave comparison (for horizontal bar chart).
    Returns per-department totals, averages, headcounts, and overall average.
    """
    if year is None:
        year = datetime.now().year
    result = await get_department_comparison(year=year, metric=metric)
    return result


@router.get("/weekday-distribution", response_model=WeekdayDistributionResponse)
async def weekday_distribution(
    year: int = Query(
        default=None,
        description="Year to query (defaults to current year)",
    ),
    _user=Depends(get_current_user),
):
    """
    Get leave weekday distribution (for bar chart).
    Expands each leave record to individual workdays and counts per weekday.
    """
    if year is None:
        year = datetime.now().year
    result = await get_weekday_distribution(year=year)
    return result


@router.get("/employee-ranking", response_model=EmployeeRankingResponse)
async def employee_ranking(
    year: int = Query(
        default=None,
        description="Year to query (defaults to current year)",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of employees to return",
    ),
    _user=Depends(get_current_user),
):
    """
    Get employee leave ranking (for stacked bar chart).
    Returns top N employees by total leave days with per-type breakdown.
    """
    if year is None:
        year = datetime.now().year
    result = await get_employee_ranking(year=year, limit=limit)
    return result
