"""
Trip Analytics API router.

GET /api/analytics/trip/monthly-trend
GET /api/analytics/trip/type-distribution
GET /api/analytics/trip/department-comparison
GET /api/analytics/trip/weekday-distribution
GET /api/analytics/trip/employee-ranking
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.schemas import (
    DepartmentComparisonResponse,
    EmployeeRankingResponse,
    LeaveTypeDistributionResponse,
    TripMonthlyTrendResponse,
    WeekdayDistributionResponse,
)
from app.services.trip_analytics import (
    get_trip_department_comparison,
    get_trip_employee_ranking,
    get_trip_monthly_trend,
    get_trip_type_distribution,
    get_trip_weekday_distribution,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics/trip", tags=["trip-analytics"])


@router.get("/monthly-trend", response_model=TripMonthlyTrendResponse)
async def trip_monthly_trend(
    year: int = Query(default=None, description="Year to query (defaults to current year)"),
    _user=Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    return await get_trip_monthly_trend(year=year)


@router.get("/type-distribution", response_model=LeaveTypeDistributionResponse)
async def trip_type_distribution(
    year: int = Query(default=None, description="Year to query (defaults to current year)"),
    _user=Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    return await get_trip_type_distribution(year=year)


@router.get("/department-comparison", response_model=DepartmentComparisonResponse)
async def trip_department_comparison(
    year: int = Query(default=None, description="Year to query (defaults to current year)"),
    metric: str = Query(default="total", description="Sort metric: 'total' or 'avg'"),
    _user=Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    return await get_trip_department_comparison(year=year, metric=metric)


@router.get("/weekday-distribution", response_model=WeekdayDistributionResponse)
async def trip_weekday_distribution(
    year: int = Query(default=None, description="Year to query (defaults to current year)"),
    _user=Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    return await get_trip_weekday_distribution(year=year)


@router.get("/employee-ranking", response_model=EmployeeRankingResponse)
async def trip_employee_ranking(
    year: int = Query(default=None, description="Year to query (defaults to current year)"),
    limit: int = Query(default=10, ge=1, le=50, description="Max employees to return"),
    _user=Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    return await get_trip_employee_ranking(year=year, limit=limit)
