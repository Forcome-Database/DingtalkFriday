"""Trip (business trip / out-of-office) API endpoints."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse

from app.auth import get_current_user, require_admin
from app.schemas import (
    MessageResponse,
    TripMonthlySummaryResponse,
    TripDailyDetailResponse,
    TripTodayResponse,
    TripStatsResponse,
    TripExportRequest,
    TripSyncRequest,
)
from app.services.trip import (
    get_trip_monthly_summary,
    get_trip_daily_detail,
    get_trip_today,
    get_trip_daily_count,
)
from app.services.export import export_trip_excel
from app.services.trip_sync import sync_trip_records

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trip", tags=["trip"])

_trip_sync_lock = asyncio.Lock()


@router.get("/monthly-summary", response_model=TripMonthlySummaryResponse)
async def monthly_summary(
    year: int = Query(..., description="Year to query"),
    deptId: Optional[int] = Query(default=None, description="Department ID"),
    tripType: Optional[str] = Query(default=None, description="出差 or 外出"),
    employeeName: Optional[str] = Query(default=None, description="Employee name filter"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    sortBy: Optional[str] = Query(default=None),
    sortOrder: str = Query(default="desc"),
    _user=Depends(get_current_user),
):
    """Get monthly trip/outing summary with pagination and filtering."""
    return await get_trip_monthly_summary(
        year=year,
        dept_id=deptId,
        trip_type=tripType,
        employee_name=employeeName,
        page=page,
        page_size=pageSize,
        sort_by=sortBy,
        sort_order=sortOrder,
    )


@router.get("/daily-detail", response_model=TripDailyDetailResponse)
async def daily_detail(
    employeeId: str = Query(..., description="Employee userid"),
    year: int = Query(..., description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    _user=Depends(get_current_user),
):
    """Get daily trip records for a specific employee in a given month."""
    return await get_trip_daily_detail(employeeId, year, month)


@router.get("/today", response_model=TripTodayResponse)
async def today_list(
    deptId: Optional[int] = Query(default=None, description="Department ID filter"),
    tripType: Optional[str] = Query(default=None, description="出差 or 外出"),
    employeeName: Optional[str] = Query(default=None, description="Employee name keyword"),
    _user=Depends(get_current_user),
):
    """Get today's trip/outing records with optional department and type filtering."""
    return await get_trip_today(dept_id=deptId, trip_type=tripType, employee_name=employeeName)


@router.get("/stats", response_model=TripStatsResponse)
async def stats(
    year: int = Query(..., description="Year to query"),
    deptId: Optional[int] = Query(default=None, description="Department ID filter"),
    tripType: Optional[str] = Query(default=None, description="出差 or 外出"),
    employeeName: Optional[str] = Query(default=None, description="Employee name keyword"),
    _user=Depends(get_current_user),
):
    """Get aggregated trip statistics for the given filters."""
    data = await get_trip_monthly_summary(
        year=year,
        dept_id=deptId,
        trip_type=tripType,
        employee_name=employeeName,
        page=1,
        page_size=1,
    )
    return data["stats"]


@router.get("/daily-count")
async def daily_count(
    year: int = Query(..., description="Year to query"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    deptId: Optional[int] = Query(default=None, description="Department ID filter"),
    tripType: Optional[str] = Query(default=None, description="出差 or 外出"),
    employeeName: Optional[str] = Query(default=None, description="Employee name keyword"),
    _user=Depends(get_current_user),
):
    """Get per-day trip headcount for heatmap display."""
    return await get_trip_daily_count(year, month, deptId, tripType, employeeName)


@router.post("/export")
async def export_excel(
    request: TripExportRequest,
    _user=Depends(get_current_user),
):
    """Export trip data as an Excel file."""
    output = await export_trip_excel(
        year=request.year,
        dept_id=request.deptId,
        trip_type=request.tripType,
        employee_name=request.employeeName,
    )
    filename = f"trip_data_{request.year}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _run_trip_sync(force_month: Optional[str] = None) -> None:
    """Background task that runs the trip sync."""
    async with _trip_sync_lock:
        try:
            await sync_trip_records(force_month)
        except Exception as e:
            logger.exception("Background trip sync failed: %s", e)


@router.post("/sync", response_model=MessageResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    request: Optional[TripSyncRequest] = None,
    _admin=Depends(require_admin),
):
    """
    Trigger a trip data sync in the background.
    Returns immediately while the sync runs asynchronously.
    Optionally pass a month (YYYY-MM) to force-sync that entire month.
    """
    if _trip_sync_lock.locked():
        return MessageResponse(message="Trip sync is already running", success=False)

    month = request.month if request else None
    background_tasks.add_task(_run_trip_sync, month)
    return MessageResponse(message="Trip sync started", success=True)
