"""
Pydantic request/response schemas for all API endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Department schemas
# ---------------------------------------------------------------------------

class DepartmentOut(BaseModel):
    """Single department in the department list response."""
    dept_id: int
    name: str
    parent_id: Optional[int] = None
    hasChildren: bool = False


# ---------------------------------------------------------------------------
# Leave type schemas
# ---------------------------------------------------------------------------

class LeaveTypeOut(BaseModel):
    """Single leave type."""
    leave_code: str
    leave_name: str
    leave_view_unit: Optional[str] = None
    hours_in_per_day: int = 800


# ---------------------------------------------------------------------------
# Monthly summary schemas
# ---------------------------------------------------------------------------

class LeaveStats(BaseModel):
    """Aggregated statistics for the filtered leave data."""
    totalCount: int = Field(description="Total leave record count (person-times)")
    totalDays: float = Field(description="Total leave days")
    avgDays: float = Field(description="Average leave days per person")
    annualRatio: float = Field(description="Annual leave ratio as percentage")
    annualDays: float = Field(description="Total annual leave days")


class MonthlyRow(BaseModel):
    """One employee row in the monthly summary table."""
    employeeId: str
    name: str
    dept: str
    avatar: Optional[str] = None
    months: List[float] = Field(description="12-element list, one per month")
    total: float = Field(description="Full-year total")


class SummaryRow(BaseModel):
    """Bottom summary row of the monthly table."""
    personCount: int
    months: List[float] = Field(description="12-element list, monthly sums")
    total: float


class PaginationInfo(BaseModel):
    """Pagination metadata."""
    page: int
    pageSize: int
    total: int


class MonthlySummaryResponse(BaseModel):
    """Full response for GET /api/leave/monthly-summary."""
    stats: LeaveStats
    list: List[MonthlyRow]
    summary: SummaryRow
    pagination: PaginationInfo


# ---------------------------------------------------------------------------
# Daily detail schemas
# ---------------------------------------------------------------------------

class EmployeeBrief(BaseModel):
    """Brief employee info shown in the daily detail panel."""
    name: str
    dept: str
    avatar: Optional[str] = None


class DailyRecord(BaseModel):
    """Single leave record for a specific day."""
    date: str = Field(description="Date string YYYY-MM-DD")
    startTime: str = Field(description="Start time HH:mm")
    endTime: str = Field(description="End time HH:mm")
    hours: float = Field(description="Duration in hours")
    leaveType: str = Field(description="Leave type name")
    status: str = Field(description="Approval status")


class DailySummary(BaseModel):
    """Monthly summary in the daily detail panel."""
    totalDays: float
    totalHours: float


class DailyDetailResponse(BaseModel):
    """Full response for GET /api/leave/daily-detail."""
    employee: EmployeeBrief
    records: List[DailyRecord]
    summary: DailySummary


# ---------------------------------------------------------------------------
# Daily leave count schemas (per-day headcount)
# ---------------------------------------------------------------------------

class DayLeaveEmployee(BaseModel):
    """An employee on leave for a specific day."""
    name: str
    dept: str
    leaveType: str


class DayLeaveCount(BaseModel):
    """Leave headcount for a single day."""
    date: str = Field(description="Date string YYYY-MM-DD")
    count: int = Field(description="Number of employees on leave")
    employees: List[DayLeaveEmployee]


class DailyLeaveCountResponse(BaseModel):
    """Full response for GET /api/leave/daily-leave-count."""
    todayCount: int = Field(description="Today's leave count (0 if not in queried month)")
    days: List[DayLeaveCount]
    maxCount: int = Field(description="Max daily count (for heatmap color scale)")


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    """Request body for POST /api/leave/export."""
    year: int
    deptId: Optional[int] = None
    leaveTypes: Optional[List[str]] = None
    employeeName: Optional[str] = None
    unit: str = "day"


# ---------------------------------------------------------------------------
# Sync schemas
# ---------------------------------------------------------------------------

class SyncTriggerRequest(BaseModel):
    """Request body for POST /api/sync."""
    year: Optional[int] = None


class SyncStatusOut(BaseModel):
    """Single sync log entry."""
    id: int
    sync_type: str
    status: str
    message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class SyncStatusResponse(BaseModel):
    """Response for GET /api/sync/status."""
    logs: List[SyncStatusOut]


# ---------------------------------------------------------------------------
# Analytics schemas
# ---------------------------------------------------------------------------

class MonthlyTrendItem(BaseModel):
    """Single month data point for the monthly trend chart."""
    month: int = Field(description="Month number (1-12)")
    days: float = Field(description="Total leave days in this month")


class MonthlyTrendResponse(BaseModel):
    """Response for GET /api/analytics/monthly-trend."""
    currentYear: List[MonthlyTrendItem]
    previousYear: List[MonthlyTrendItem]


class LeaveTypeDistributionItem(BaseModel):
    """Single leave type in the distribution chart."""
    type: str = Field(description="Leave type name")
    days: float = Field(description="Total leave days for this type")
    ratio: float = Field(description="Percentage of total leave days")


class LeaveTypeDistributionResponse(BaseModel):
    """Response for GET /api/analytics/leave-type-distribution."""
    total: float = Field(description="Grand total leave days")
    items: List[LeaveTypeDistributionItem]


class DepartmentComparisonItem(BaseModel):
    """Single department in the comparison chart."""
    name: str = Field(description="Department name")
    totalDays: float = Field(description="Total leave days for the department")
    avgDays: float = Field(description="Average leave days per employee")
    headcount: int = Field(description="Number of employees in the department")


class DepartmentComparisonResponse(BaseModel):
    """Response for GET /api/analytics/department-comparison."""
    departments: List[DepartmentComparisonItem]
    average: float = Field(description="Overall average across all departments")


class WeekdayDistributionItem(BaseModel):
    """Single weekday in the distribution chart."""
    day: int = Field(description="ISO weekday number (1=Monday, 5=Friday)")
    label: str = Field(description="Weekday label in Chinese")
    count: int = Field(description="Number of leave occurrences on this weekday")


class WeekdayDistributionResponse(BaseModel):
    """Response for GET /api/analytics/weekday-distribution."""
    weekdays: List[WeekdayDistributionItem]


class EmployeeLeaveBreakdown(BaseModel):
    """Leave breakdown by type for a single employee."""
    type: str = Field(description="Leave type name")
    days: float = Field(description="Leave days for this type")


class EmployeeRankingItem(BaseModel):
    """Single employee in the ranking chart."""
    name: str = Field(description="Employee name")
    dept: str = Field(description="Department name")
    total: float = Field(description="Total leave days")
    breakdown: List[EmployeeLeaveBreakdown]


class EmployeeRankingResponse(BaseModel):
    """Response for GET /api/analytics/employee-ranking."""
    employees: List[EmployeeRankingItem]


# ---------------------------------------------------------------------------
# Generic response wrapper
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True
