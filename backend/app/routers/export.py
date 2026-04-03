"""
Excel export API router.

POST /api/leave/export
GET  /api/leave/today-detail/export
"""

import logging
from datetime import date as date_type, datetime
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.schemas import ExportRequest
from app.services.export import export_leave_data, export_leave_detail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leave", tags=["export"])


@router.post("/export")
async def export_excel(request: ExportRequest, _user=Depends(get_current_user)):
    """
    Export leave data as an Excel (.xlsx) file.
    Returns a file stream with proper content headers.
    """
    output = await export_leave_data(
        year=request.year,
        dept_id=request.deptId,
        leave_types=request.leaveTypes,
        employee_name=request.employeeName,
        unit=request.unit,
    )

    # Build filename: 请假数据_{部门}_{年份}.xlsx
    dept_label = f"dept{request.deptId}" if request.deptId else "全部"
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"请假数据_{dept_label}_{request.year}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.get("/today-detail/export")
async def export_today_detail(
    deptId: Optional[int] = Query(default=None),
    leaveTypes: Optional[str] = Query(default=None),
    employeeName: Optional[str] = Query(default=None),
    date: Optional[str] = Query(default=None),
    _user=Depends(get_current_user),
):
    """Export leave detail for a specific date as Excel."""
    from app.services.leave import get_today_leave_detail

    leave_type_list: Optional[List[str]] = None
    if leaveTypes:
        leave_type_list = [t.strip() for t in leaveTypes.split(",") if t.strip()]

    target_date = None
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            pass

    data = await get_today_leave_detail(
        dept_id=deptId,
        leave_types=leave_type_list,
        employee_name=employeeName,
        target_date=target_date,
    )

    output = export_leave_detail(data)
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    filename = f"请假详情_{date_str}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )
