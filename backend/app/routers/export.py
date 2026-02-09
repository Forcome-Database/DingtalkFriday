"""
Excel export API router.

POST /api/leave/export
"""

import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.schemas import ExportRequest
from app.services.export import export_leave_data

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
