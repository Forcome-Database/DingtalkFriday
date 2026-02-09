"""
Excel export service.

Generates .xlsx files using openpyxl with the same data structure
as the monthly summary table displayed in the frontend.
"""

import io
import logging
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.services.leave import get_monthly_summary

logger = logging.getLogger(__name__)

# Style constants
HEADER_FILL = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
HEADER_FONT = Font(name="Microsoft YaHei", bold=True, color="FFFFFF", size=11)
SUMMARY_FILL = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
SUMMARY_FONT = Font(name="Microsoft YaHei", bold=True, size=11)
DATA_FONT = Font(name="Microsoft YaHei", size=11)
TOTAL_COL_FILL = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin", color="E4E4E7"),
    right=Side(style="thin", color="E4E4E7"),
    top=Side(style="thin", color="E4E4E7"),
    bottom=Side(style="thin", color="E4E4E7"),
)
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")
LEFT_ALIGN = Alignment(horizontal="left", vertical="center")


async def export_leave_data(
    year: int,
    dept_id: Optional[int] = None,
    leave_types: Optional[List[str]] = None,
    employee_name: Optional[str] = None,
    unit: str = "day",
) -> io.BytesIO:
    """
    Generate an Excel file containing the monthly leave summary.

    The export includes ALL matching rows (no pagination) plus
    a summary (totals) row at the bottom.

    Returns a BytesIO object containing the .xlsx data.
    """
    # Fetch all data without pagination
    data = await get_monthly_summary(
        year=year,
        dept_id=dept_id,
        leave_types=leave_types,
        employee_name=employee_name,
        unit=unit,
        page=1,
        page_size=999999,  # effectively no limit
        sort_by="name",
        sort_order="asc",
    )

    rows = data["list"]
    summary = data["summary"]
    unit_label = "天" if unit == "day" else "小时"

    wb = Workbook()
    ws = wb.active
    ws.title = f"{year}年请假数据"

    # ---- Header row ----
    headers = ["员工姓名", "部门"]
    for m in range(1, 13):
        headers.append(f"{m}月")
    headers.append(f"合计({unit_label})")

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # ---- Data rows ----
    for row_idx, row_data in enumerate(rows, start=2):
        # Name
        cell = ws.cell(row=row_idx, column=1, value=row_data["name"])
        cell.font = DATA_FONT
        cell.alignment = LEFT_ALIGN
        cell.border = THIN_BORDER

        # Department
        cell = ws.cell(row=row_idx, column=2, value=row_data["dept"])
        cell.font = DATA_FONT
        cell.alignment = LEFT_ALIGN
        cell.border = THIN_BORDER

        # Monthly values
        for m_idx, val in enumerate(row_data["months"]):
            cell = ws.cell(row=row_idx, column=3 + m_idx, value=val if val else None)
            cell.font = DATA_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER
            cell.number_format = "0.0"

        # Total column (highlighted)
        cell = ws.cell(row=row_idx, column=15, value=row_data["total"])
        cell.font = Font(name="Microsoft YaHei", bold=True, size=11)
        cell.fill = TOTAL_COL_FILL
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        cell.number_format = "0.0"

    # ---- Summary row ----
    summary_row = len(rows) + 2
    cell = ws.cell(row=summary_row, column=1, value="合计")
    cell.fill = SUMMARY_FILL
    cell.font = SUMMARY_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

    cell = ws.cell(row=summary_row, column=2, value=f"{summary['personCount']}人")
    cell.fill = SUMMARY_FILL
    cell.font = SUMMARY_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

    for m_idx, val in enumerate(summary["months"]):
        cell = ws.cell(row=summary_row, column=3 + m_idx, value=val if val else None)
        cell.fill = SUMMARY_FILL
        cell.font = SUMMARY_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        cell.number_format = "0.0"

    cell = ws.cell(row=summary_row, column=15, value=summary["total"])
    cell.fill = PatternFill(start_color="BFDBFE", end_color="BFDBFE", fill_type="solid")
    cell.font = SUMMARY_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER
    cell.number_format = "0.0"

    # ---- Column widths ----
    ws.column_dimensions["A"].width = 14  # Name
    ws.column_dimensions["B"].width = 14  # Department
    for col in range(3, 15):
        ws.column_dimensions[get_column_letter(col)].width = 10  # Month cols
    ws.column_dimensions["O"].width = 12  # Total column

    # ---- Freeze panes (freeze header + first 2 columns) ----
    ws.freeze_panes = "C2"

    # ---- Write to BytesIO ----
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    logger.info(
        "Exported Excel: year=%d, dept_id=%s, rows=%d",
        year, dept_id, len(rows),
    )
    return output
