# 外出/出差功能集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add business trip (出差) and out-of-office (外出) data sync, statistics, and export to the DingtalkFriday system as a separate Tab page.

**Architecture:** New data flows through DingTalk `getupdatedata` API → `trip_sync.py` service (with partitioned caching) → SQLite `trip_record` table → FastAPI query endpoints → Vue3 frontend Tab page. All new code lives in dedicated files, existing code modified only for navigation integration and router registration.

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic, httpx, APScheduler, Vue 3, TailwindCSS, openpyxl

**Spec:** `docs/superpowers/specs/2026-04-02-trip-integration-design.md`

---

## File Map

### Backend — Create

| File | Responsibility |
|------|---------------|
| `backend/app/services/trip_sync.py` | Sync trip records from DingTalk with partitioned caching |
| `backend/app/services/trip.py` | Query trip data (monthly summary, daily detail, today, stats) |
| `backend/app/services/dept_utils.py` | Shared department utility (extract `_get_descendant_dept_ids`) |
| `backend/app/routers/trip.py` | REST API endpoints for trip data |

### Backend — Modify

| File | Change |
|------|--------|
| `backend/app/models.py` | Add `TripRecord` and `TripSyncCursor` models |
| `backend/app/schemas.py` | Add trip-related Pydantic schemas |
| `backend/app/config.py` | Add `TRIP_SYNC_*` settings |
| `backend/app/dingtalk/attendance.py` | Add `get_update_data()` wrapper |
| `backend/app/services/export.py` | Add `export_trip_excel()` function |
| `backend/app/services/leave.py` | Replace local `_get_descendant_dept_ids` with import from `dept_utils` |
| `backend/app/main.py` | Register trip router + trip sync scheduler |

### Frontend — Create

| File | Responsibility |
|------|---------------|
| `frontend/src/composables/useTripData.js` | Trip data state management and API calls |
| `frontend/src/components/TripStatsCards.vue` | 4 stat cards (total count, total days, today trip, today outing) |
| `frontend/src/components/TripFilterPanel.vue` | Filters: department, type (出差/外出), year, name |
| `frontend/src/components/TripDataTable.vue` | Monthly summary table |
| `frontend/src/components/TripDailyStats.vue` | Daily heatmap + detail list |
| `frontend/src/components/TripTodayModal.vue` | Today trip/outing detail modal |

### Frontend — Modify

| File | Change |
|------|--------|
| `frontend/src/api/index.js` | Add trip API methods |
| `frontend/src/components/AppHeader.vue` | Add "外出/出差" nav tab (desktop + mobile) |
| `frontend/src/views/MainView.vue` | Add trip page, import components, wire up data |
| `frontend/src/components/StatsCards.vue` | Add 6th card "今日外出/出差", adjust grid |

---

## Task 1: Data Models

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add TripRecord model**

First, update the import line at the top of `backend/app/models.py`. Find the existing SQLAlchemy import and add `Float` and `Index`:

```python
from sqlalchemy import (
    Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint,
)
```

Then add after the `LeaveRecord` class:

```python
class TripRecord(Base):
    """Business trip / out-of-office records from getupdatedata API."""
    __tablename__ = "trip_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(String, nullable=False, comment="DingTalk user ID")
    work_date = Column(String, nullable=False, comment="Work date YYYY-MM-DD")
    tag_name = Column(String, nullable=False, comment="出差 or 外出")
    sub_type = Column(String, nullable=True, comment="Sub-type name")
    begin_time = Column(String, nullable=False, comment="Approval begin time")
    end_time = Column(String, nullable=False, comment="Approval end time")
    duration_hours = Column(Float, nullable=False, default=0, comment="Hours for this work_date (8=full day)")
    proc_inst_id = Column(String, nullable=False, comment="Approval instance ID")
    last_synced_at = Column(DateTime, nullable=False, comment="Last sync timestamp")
    created_at = Column(DateTime, default=datetime.utcnow, comment="Record creation time")

    __table_args__ = (
        UniqueConstraint("userid", "work_date", "proc_inst_id", name="uq_trip_record"),
        Index("ix_trip_work_date_tag", "work_date", "tag_name"),
    )
```

Note: Add `Index` to the imports from `sqlalchemy` at the top of the file. Also add `Float` to the imports if not already present.

- [ ] **Step 2: Add TripSyncCursor model**

Add after `TripRecord` in the same file:

```python
class TripSyncCursor(Base):
    """Tracks which (userid, work_date) pairs have been synced."""
    __tablename__ = "trip_sync_cursor"

    userid = Column(String, primary_key=True, comment="DingTalk user ID")
    work_date = Column(String, primary_key=True, comment="Date YYYY-MM-DD")
    last_synced_at = Column(DateTime, nullable=False, comment="Last sync timestamp")
```

- [ ] **Step 3: Verify DB tables auto-create**

Run:
```bash
cd backend && python -c "
import asyncio
from app.database import engine, Base
from app.models import TripRecord, TripSyncCursor
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables created OK')
asyncio.run(init())
"
```

Expected: `Tables created OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add TripRecord and TripSyncCursor data models"
```

---

## Task 2: Config Settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add trip sync settings**

Add these fields to the `Settings` class in `backend/app/config.py`:

```python
    # Trip (business trip / out-of-office) sync settings
    trip_sync_enabled: bool = True
    trip_sync_cron: str = "30 2 * * *"
    trip_hot_days_past: int = 3
    trip_hot_days_future: int = 7
    trip_warm_days_future: int = 90
    trip_sync_concurrency: int = 10
    trip_sync_retry_count: int = 3
    trip_sync_fail_threshold: int = 50
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add trip sync configuration settings"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add trip response schemas**

First, update the `typing` import at the top of `backend/app/schemas.py` to include `Dict`:

```python
from typing import Dict, List, Optional
```

Then add at the end of the file:

```python
# ---------------------------------------------------------------------------
# Trip (business trip / out-of-office) schemas
# ---------------------------------------------------------------------------

class TripStats(BaseModel):
    totalCount: int = Field(description="Total person-trips (distinct proc_inst_id per user)")
    totalDays: float = Field(description="Total days (sum of duration_hours / 8)")
    todayTripCount: int = Field(description="Today's business trip headcount")
    todayOutingCount: int = Field(description="Today's out-of-office headcount")


class TripEmployeeRow(BaseModel):
    employeeId: str
    employeeName: str
    deptName: Optional[str] = None
    tripDays: float = Field(description="Business trip total days")
    outingDays: float = Field(description="Out-of-office total days")
    totalDays: float = Field(description="Combined total days")
    tripCount: int = Field(description="Business trip count (distinct)")
    outingCount: int = Field(description="Out-of-office count (distinct)")
    months: Dict[str, float] = Field(description="Per-month days: {'1': 2.5, '2': 0, ...}")


class TripSummaryRow(BaseModel):
    tripDays: float = 0
    outingDays: float = 0
    totalDays: float = 0
    months: Dict[str, float] = Field(default_factory=dict)


class TripMonthlySummaryResponse(BaseModel):
    stats: TripStats
    list: List[TripEmployeeRow]
    summary: TripSummaryRow
    pagination: PaginationInfo


class TripDayRecord(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    tagName: str = Field(description="出差 or 外出")
    durationHours: float
    beginTime: str
    endTime: str


class TripDailyDetailResponse(BaseModel):
    employeeName: str
    records: List[TripDayRecord]


class TripTodayItem(BaseModel):
    employeeId: str
    employeeName: str
    deptName: Optional[str] = None
    tagName: str
    beginTime: str
    endTime: str
    durationHours: float


class TripTodayResponse(BaseModel):
    list: List[TripTodayItem]


class TripExportRequest(BaseModel):
    year: int
    deptId: Optional[int] = None
    tripType: Optional[str] = None
    employeeName: Optional[str] = None


class TripSyncRequest(BaseModel):
    month: Optional[str] = Field(default=None, description="YYYY-MM format, optional")


# Alias for router response_model consistency
TripStatsResponse = TripStats
```

Note: Check that `PaginationInfo` already has a `totalPages` field. If not, add it:

```python
class PaginationInfo(BaseModel):
    page: int
    pageSize: int
    total: int
    totalPages: int = 0  # Add this field if missing
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: add Pydantic schemas for trip API responses"
```

---

## Task 4: DingTalk API Wrapper

**Files:**
- Modify: `backend/app/dingtalk/attendance.py`

- [ ] **Step 1: Add get_update_data function**

Add at the end of `backend/app/dingtalk/attendance.py`:

```python
async def get_update_data(userid: str, work_date: str) -> Dict[str, Any]:
    """
    Query a user's attendance data for a specific date.

    POST /topapi/attendance/getupdatedata
    Body: { userid, work_date }

    Returns the full response dict containing:
    - approve_list: list of approval records with biz_type, tag_name, etc.
    - check_record_list: clock-in records
    - attendance_result_list: attendance results
    """
    data = await dingtalk_client.post(
        "/topapi/attendance/getupdatedata",
        json_body={
            "userid": userid,
            "work_date": work_date,
        },
    )
    return data.get("result", {})
```

- [ ] **Step 2: Verify API wrapper works**

Run (replace with a real userid from your DB):
```bash
cd backend && python -c "
import asyncio
from app.dingtalk.attendance import get_update_data
async def test():
    # Use a known userid - adjust as needed
    from app.database import async_session
    from sqlalchemy import select
    from app.models import Employee
    async with async_session() as session:
        row = await session.execute(select(Employee.userid).limit(1))
        uid = row.scalar_one_or_none()
    if uid:
        result = await get_update_data(uid, '2026-04-02')
        print('approve_list count:', len(result.get('approve_list', [])))
        for item in result.get('approve_list', []):
            print(f'  biz_type={item.get(\"biz_type\")}, tag_name={item.get(\"tag_name\")}, duration={item.get(\"duration\")}')
    else:
        print('No employee found in DB, run sync first')
asyncio.run(test())
"
```

Expected: Either records or empty list, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/dingtalk/attendance.py
git commit -m "feat: add get_update_data DingTalk API wrapper"
```

---

## Task 5: Trip Sync Service

**Files:**
- Create: `backend/app/services/trip_sync.py`

- [ ] **Step 1: Create trip_sync.py with sync logic**

Create `backend/app/services/trip_sync.py`:

```python
"""
Trip (business trip / out-of-office) sync service.

Syncs data from DingTalk getupdatedata API into trip_record table
using a partitioned caching strategy (hot/warm/cold zones).
"""

import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import async_session
from app.models import Employee, TripRecord, TripSyncCursor, SyncLog
from app.dingtalk.attendance import get_update_data
from app.config import settings

logger = logging.getLogger(__name__)


async def _create_sync_log(sync_type: str = "trip_record") -> int:
    async with async_session() as session:
        log = SyncLog(
            sync_type=sync_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log.id


async def _finish_sync_log(log_id: int, status: str, message: str = "") -> None:
    async with async_session() as session:
        result = await session.execute(select(SyncLog).where(SyncLog.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            log.status = status
            log.message = message
            log.finished_at = datetime.now(timezone.utc)
            await session.commit()


def _build_date_list(
    hot_past: int,
    hot_future: int,
    warm_future: int,
    include_warm: bool,
) -> List[date]:
    """Build the list of dates to sync based on zone configuration."""
    today = date.today()
    dates = set()

    # Hot zone: always included
    for delta in range(-hot_past, hot_future + 1):
        dates.add(today + timedelta(days=delta))

    # Warm zone: only on designated days (e.g., Monday)
    if include_warm:
        for delta in range(hot_future + 1, warm_future + 1):
            dates.add(today + timedelta(days=delta))

    return sorted(dates)


def _build_force_month_dates(month_str: str) -> List[date]:
    """Build date list for a specific month (YYYY-MM)."""
    year, month = int(month_str[:4]), int(month_str[5:7])
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    dates = []
    d = first_day
    while d <= last_day:
        dates.append(d)
        d += timedelta(days=1)
    return dates


async def _should_skip(userid: str, work_date: str, zone: str) -> bool:
    """Check if a (userid, work_date) should be skipped based on zone."""
    if zone == "hot":
        return False  # Hot zone always syncs

    async with async_session() as session:
        result = await session.execute(
            select(TripSyncCursor).where(
                TripSyncCursor.userid == userid,
                TripSyncCursor.work_date == work_date,
            )
        )
        cursor = result.scalar_one_or_none()

    if cursor is None:
        return False  # Never synced, don't skip

    # Warm zone: skip if synced within 7 days
    age = datetime.now(timezone.utc) - cursor.last_synced_at.replace(tzinfo=timezone.utc)
    return age.total_seconds() < 7 * 86400


async def _sync_one(userid: str, work_date_str: str, semaphore: asyncio.Semaphore) -> int:
    """Sync trip records for one user on one date. Returns count of records upserted."""
    async with semaphore:
        await asyncio.sleep(0.05)  # 50ms throttle

        data = await get_update_data(userid, work_date_str)
        approve_list = data.get("approve_list", [])

        # Filter biz_type=2 (trip/outing)
        trip_items = [a for a in approve_list if a.get("biz_type") == 2]

        now = datetime.now(timezone.utc)

        # Delete existing records for this userid + work_date, then insert fresh
        async with async_session() as session:
            await session.execute(
                delete(TripRecord).where(
                    TripRecord.userid == userid,
                    TripRecord.work_date == work_date_str,
                )
            )

            for item in trip_items:
                proc_inst_id = item.get("procInst_id") or item.get("proc_inst_id", "")
                if not proc_inst_id:
                    continue

                tag_name = item.get("tag_name", "")
                # Determine duration_hours for this day
                duration_raw = item.get("duration")
                duration_unit = item.get("duration_unit", "")
                if duration_raw is not None:
                    try:
                        dur = float(duration_raw)
                        # If unit is in days, convert to hours
                        if "day" in duration_unit.lower() or "天" in duration_unit:
                            duration_hours = dur * 8
                        else:
                            duration_hours = dur
                        # Cap at 8 hours per day
                        duration_hours = min(duration_hours, 8.0)
                    except (ValueError, TypeError):
                        duration_hours = 8.0
                else:
                    duration_hours = 8.0  # Default full day

                session.add(TripRecord(
                    userid=userid,
                    work_date=work_date_str,
                    tag_name=tag_name,
                    sub_type=item.get("sub_type"),
                    begin_time=str(item.get("begin_time", "")),
                    end_time=str(item.get("end_time", "")),
                    duration_hours=duration_hours,
                    proc_inst_id=proc_inst_id,
                    last_synced_at=now,
                    created_at=now,
                ))

            # Update sync cursor
            stmt = sqlite_insert(TripSyncCursor).values(
                userid=userid,
                work_date=work_date_str,
                last_synced_at=now,
            ).on_conflict_do_update(
                index_elements=["userid", "work_date"],
                set_={"last_synced_at": now},
            )
            await session.execute(stmt)
            await session.commit()

        return len(trip_items)


async def sync_trip_records(force_month: Optional[str] = None) -> str:
    """
    Main sync entry point.

    Args:
        force_month: If provided (YYYY-MM), sync that entire month ignoring cache.
    """
    log_id = await _create_sync_log()
    try:
        # Get all employee userids
        async with async_session() as session:
            result = await session.execute(select(Employee.userid))
            all_userids = [row[0] for row in result.fetchall()]

        if not all_userids:
            msg = "No employees found, skipping trip sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Build date list
        if force_month:
            dates = _build_force_month_dates(force_month)
            # Clear cursors for the forced month
            async with async_session() as session:
                for d in dates:
                    await session.execute(
                        delete(TripSyncCursor).where(
                            TripSyncCursor.work_date == d.isoformat(),
                        )
                    )
                await session.commit()
            zone = "force"
        else:
            is_monday = date.today().weekday() == 0
            dates = _build_date_list(
                hot_past=settings.trip_hot_days_past,
                hot_future=settings.trip_hot_days_future,
                warm_future=settings.trip_warm_days_future,
                include_warm=is_monday,
            )
            zone = "hot"  # Default zone for skip check

        today = date.today()
        hot_start = today - timedelta(days=settings.trip_hot_days_past)
        hot_end = today + timedelta(days=settings.trip_hot_days_future)

        semaphore = asyncio.Semaphore(settings.trip_sync_concurrency)
        total_records = 0
        total_skipped = 0
        consecutive_failures = 0

        for d in dates:
            work_date_str = d.isoformat()

            # Determine zone for non-forced syncs
            if not force_month:
                zone = "hot" if hot_start <= d <= hot_end else "warm"

            tasks = []
            for uid in all_userids:
                # Skip check for warm/cold zones
                if zone != "hot" and zone != "force":
                    should_skip = await _should_skip(uid, work_date_str, zone)
                    if should_skip:
                        total_skipped += 1
                        continue
                tasks.append((uid, work_date_str))

            # Execute with actual concurrency via asyncio.gather
            # Process in batches to allow failure threshold checking
            batch_size = settings.trip_sync_concurrency * 5  # ~50 concurrent tasks per batch
            for batch_start in range(0, len(tasks), batch_size):
                if consecutive_failures >= settings.trip_sync_fail_threshold:
                    msg = f"Aborted: {consecutive_failures} consecutive failures"
                    await _finish_sync_log(log_id, "failed", msg)
                    return msg

                batch = tasks[batch_start: batch_start + batch_size]

                async def _sync_with_retry(uid, wds):
                    nonlocal total_records, consecutive_failures
                    for attempt in range(settings.trip_sync_retry_count + 1):
                        try:
                            count = await _sync_one(uid, wds, semaphore)
                            total_records += count
                            consecutive_failures = 0
                            return
                        except Exception as e:
                            if attempt >= settings.trip_sync_retry_count:
                                consecutive_failures += 1
                                logger.warning(
                                    "Failed to sync trip for %s on %s after %d retries: %s",
                                    uid, wds, settings.trip_sync_retry_count, e,
                                )
                                return
                            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s

                await asyncio.gather(
                    *[_sync_with_retry(uid, wds) for uid, wds in batch]
                )

        # Cleanup old cursors (> 1 year)
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        async with async_session() as session:
            await session.execute(
                delete(TripSyncCursor).where(TripSyncCursor.last_synced_at < cutoff)
            )
            await session.commit()

        msg = (
            f"Trip sync done: {total_records} records across "
            f"{len(all_userids)} employees, {len(dates)} dates, "
            f"{total_skipped} skipped"
        )
        await _finish_sync_log(log_id, "success", msg)
        logger.info(msg)
        return msg

    except Exception as e:
        msg = f"Trip sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise
```

- [ ] **Step 2: Verify module imports**

```bash
cd backend && python -c "from app.services.trip_sync import sync_trip_records; print('Import OK')"
```

Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/trip_sync.py
git commit -m "feat: add trip sync service with partitioned caching"
```

---

## Task 6: Shared Dept Utility + Trip Query Service

**Files:**
- Create: `backend/app/services/dept_utils.py`
- Create: `backend/app/services/trip.py`
- Modify: `backend/app/services/leave.py`

- [ ] **Step 1: Extract shared dept utility**

Create `backend/app/services/dept_utils.py`:

```python
"""Shared department utilities used by leave and trip services."""

from typing import Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department


async def get_descendant_dept_ids(session: AsyncSession, dept_id: int) -> Set[int]:
    """Get all descendant department IDs including the given one."""
    result = {dept_id}
    queue = [dept_id]
    while queue:
        parent = queue.pop()
        rows = await session.execute(
            select(Department.dept_id).where(Department.parent_id == parent)
        )
        for (child_id,) in rows:
            if child_id not in result:
                result.add(child_id)
                queue.append(child_id)
    return result
```

- [ ] **Step 2: Update leave.py to use shared utility**

In `backend/app/services/leave.py`, replace the local `_get_descendant_dept_ids` function with an import:

```python
from app.services.dept_utils import get_descendant_dept_ids
```

Then find-and-replace all calls from `_get_descendant_dept_ids(` to `get_descendant_dept_ids(` in the file.

- [ ] **Step 3: Create trip.py query service**

Create `backend/app/services/trip.py`:

```python
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
```

- [ ] **Step 4: Verify imports**

```bash
cd backend && python -c "from app.services.trip import get_trip_monthly_summary; print('Import OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dept_utils.py backend/app/services/trip.py backend/app/services/leave.py
git commit -m "refactor: extract dept_utils; add trip query service"
```

---

## Task 7: Trip Export

**Files:**
- Modify: `backend/app/services/export.py`

- [ ] **Step 1: Add export_trip_excel function**

Add at the end of `backend/app/services/export.py`:

```python
async def export_trip_excel(
    year: int,
    dept_id: Optional[int] = None,
    trip_type: Optional[str] = None,
    employee_name: Optional[str] = None,
) -> io.BytesIO:
    """Export trip data as Excel file."""
    from app.services.trip import get_trip_monthly_summary

    data = await get_trip_monthly_summary(
        year=year,
        dept_id=dept_id,
        trip_type=trip_type,
        employee_name=employee_name,
        page=1,
        page_size=999999,
    )

    rows = data["list"]
    summary = data["summary"]

    wb = Workbook()
    ws = wb.active
    ws.title = f"{year}年外出出差统计"

    # Header row
    headers = ["姓名", "部门", "出差(天)", "外出(天)"]
    headers += [f"{m}月" for m in range(1, 13)]
    headers.append("合计(天)")

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # Data rows
    for row_idx, row in enumerate(rows, 2):
        values = [
            row["employeeName"],
            row.get("deptName", ""),
            row["tripDays"],
            row["outingDays"],
        ]
        for m in range(1, 13):
            values.append(row["months"].get(str(m), 0))
        values.append(row["totalDays"])

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

    # Summary row
    sum_row = len(rows) + 2
    sum_values = [
        "合计", "",
        summary["tripDays"],
        summary["outingDays"],
    ]
    for m in range(1, 13):
        sum_values.append(summary["months"].get(str(m), 0))
    sum_values.append(summary["totalDays"])

    for col, val in enumerate(sum_values, 1):
        cell = ws.cell(row=sum_row, column=col, value=val)
        cell.fill = SUMMARY_FILL
        cell.font = Font(name="Microsoft YaHei", bold=True, size=11)
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # Column widths
    from openpyxl.utils import get_column_letter
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 10
    for i in range(5, 17):
        ws.column_dimensions[get_column_letter(i)].width = 8
    ws.column_dimensions[get_column_letter(17)].width = 10

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
```

Note: Ensure `Optional` and `List` are imported from `typing`. The style constants (`HEADER_FILL`, `HEADER_FONT`, `SUMMARY_FILL`, `CENTER_ALIGN`, `THIN_BORDER`) are already defined in this file.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/export.py
git commit -m "feat: add trip Excel export function"
```

---

## Task 8: API Router + Registration

**Files:**
- Create: `backend/app/routers/trip.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create trip router**

Create `backend/app/routers/trip.py`:

```python
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
    employeeId: str = Query(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    _user=Depends(get_current_user),
):
    return await get_trip_daily_detail(employeeId, year, month)


@router.get("/today", response_model=TripTodayResponse)
async def today_list(
    deptId: Optional[int] = Query(default=None),
    tripType: Optional[str] = Query(default=None),
    employeeName: Optional[str] = Query(default=None),
    _user=Depends(get_current_user),
):
    return await get_trip_today(dept_id=deptId, trip_type=tripType, employee_name=employeeName)


@router.get("/stats", response_model=TripStatsResponse)
async def stats(
    year: int = Query(...),
    deptId: Optional[int] = Query(default=None),
    tripType: Optional[str] = Query(default=None),
    employeeName: Optional[str] = Query(default=None),
    _user=Depends(get_current_user),
):
    data = await get_trip_monthly_summary(
        year=year, dept_id=deptId, trip_type=tripType,
        employee_name=employeeName, page=1, page_size=1,
    )
    return data["stats"]


@router.get("/daily-count")
async def daily_count(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    deptId: Optional[int] = Query(default=None),
    tripType: Optional[str] = Query(default=None),
    employeeName: Optional[str] = Query(default=None),
    _user=Depends(get_current_user),
):
    return await get_trip_daily_count(year, month, deptId, tripType, employeeName)


@router.post("/export")
async def export_excel(
    request: TripExportRequest,
    _user=Depends(get_current_user),
):
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
    if _trip_sync_lock.locked():
        return MessageResponse(message="Trip sync is already running", success=False)
    month = request.month if request else None
    background_tasks.add_task(_run_trip_sync, month)
    return MessageResponse(message="Trip sync started", success=True)
```

- [ ] **Step 2: Register router in main.py**

Add to `backend/app/main.py` imports:

```python
from app.routers import admin, analytics, auth, departments, export, leave, sync, trip
```

Add after the last `app.include_router(...)` line:

```python
app.include_router(trip.router)
```

- [ ] **Step 3: Add trip sync scheduler in main.py**

Add a new `_setup_trip_scheduler()` function after the existing `_setup_scheduler()` function in `backend/app/main.py`:

```python
def _setup_trip_scheduler():
    """Set up APScheduler for trip sync if enabled."""
    global _scheduler
    if not settings.trip_sync_enabled:
        logger.info("Trip sync disabled")
        return
    cron_expr = settings.trip_sync_cron.strip()
    if not cron_expr:
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        if _scheduler is None:
            _scheduler = AsyncIOScheduler()

        trigger = CronTrigger.from_crontab(cron_expr)

        async def scheduled_trip_sync():
            logger.info("Scheduled trip sync triggered by cron: %s", cron_expr)
            try:
                from app.services.trip_sync import sync_trip_records
                await sync_trip_records()
            except Exception as e:
                logger.exception("Scheduled trip sync failed: %s", e)

        _scheduler.add_job(scheduled_trip_sync, trigger, id="trip_sync", replace_existing=True)
        if not _scheduler.running:
            _scheduler.start()
        logger.info("Trip sync scheduled: %s", cron_expr)
    except Exception as e:
        logger.exception("Failed to setup trip scheduler: %s", e)
```

Then in the `lifespan` function, add after `_setup_scheduler()`:

```python
    _setup_trip_scheduler()
```

- [ ] **Step 4: Verify server starts**

```bash
cd backend && python -c "from app.main import app; print('App loaded OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/trip.py backend/app/main.py
git commit -m "feat: add trip API router and register in app"
```

---

## Task 9: Frontend API Client

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add trip API methods**

Add these methods to the default export object in `frontend/src/api/index.js`:

```javascript
  // Trip (business trip / out-of-office)
  getTripMonthlySummary(params) {
    return api.get('/trip/monthly-summary', {
      params: {
        year: params.year,
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
        page: params.page || 1,
        pageSize: params.pageSize || 10,
        sortBy: params.sortBy || undefined,
        sortOrder: params.sortOrder || 'desc',
      }
    })
  },
  getTripDailyDetail(params) {
    return api.get('/trip/daily-detail', {
      params: { employeeId: params.employeeId, year: params.year, month: params.month }
    })
  },
  getTripToday(params = {}) {
    return api.get('/trip/today', {
      params: {
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
      }
    })
  },
  getTripStats(params) {
    return api.get('/trip/stats', {
      params: {
        year: params.year,
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
      }
    })
  },
  getTripDailyCount(params) {
    return api.get('/trip/daily-count', {
      params: {
        year: params.year, month: params.month,
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
      }
    })
  },
  exportTripExcel(params) {
    return api.post('/trip/export', {
      year: params.year,
      deptId: params.deptId || null,
      tripType: params.tripType || null,
      employeeName: params.employeeName || null,
    }, { responseType: 'blob' })
  },
  triggerTripSync(month) {
    return api.post('/trip/sync', { month: month || null })
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat: add trip API client methods"
```

---

## Task 10: useTripData Composable

**Files:**
- Create: `frontend/src/composables/useTripData.js`

- [ ] **Step 1: Create useTripData composable**

Create `frontend/src/composables/useTripData.js`:

```javascript
import { ref, reactive, computed } from 'vue'
import api from '../api/index.js'

export function useTripData() {
  // Filters
  const filters = reactive({
    dept1: null,
    dept2: null,
    tripType: '',  // '' = all, '出差', '外出'
    year: new Date().getFullYear(),
    employeeName: '',
    unit: 'day',
  })

  // Department options (reuse same API as leave)
  const departments1 = ref([])
  const departments2 = ref([])

  // Data
  const tableData = ref([])
  const summaryRow = ref({})
  const stats = ref({ totalCount: 0, totalDays: 0, todayTripCount: 0, todayOutingCount: 0 })
  const pagination = ref({ page: 1, pageSize: 10, total: 0, totalPages: 0 })
  const sortBy = ref('')
  const sortOrder = ref('desc')
  const loading = ref(false)

  // Daily stats
  const dailyTripMonth = ref({ year: new Date().getFullYear(), month: new Date().getMonth() + 1 })
  const dailyTripData = ref({ days: {} })
  const dailyTripLoading = ref(false)

  // Today modal
  const todayTripVisible = ref(false)
  const todayTripDetail = ref([])
  const todayTripLoading = ref(false)
  const todayTripType = ref('')  // which card was clicked: '出差' or '外出' or ''

  // Calendar modal (detail for one employee)
  const calendarVisible = ref(false)
  const calendarData = ref({ employeeName: '', records: [] })
  const calendarLoading = ref(false)
  const selectedCell = ref(null)

  // Sync
  const syncing = ref(false)

  // Year options
  const currentYear = new Date().getFullYear()
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i)

  // Load departments (same as leave)
  async function loadDepartments1() {
    try {
      const res = await api.getDepartments()
      departments1.value = res.departments || []
    } catch (e) { console.error('Failed to load departments1', e) }
  }

  async function loadDepartments2(parentId) {
    if (!parentId) { departments2.value = []; return }
    try {
      const res = await api.getDepartments(parentId)
      departments2.value = res.departments || []
    } catch (e) { console.error('Failed to load departments2', e) }
  }

  // Fetch main data
  async function fetchData() {
    loading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripMonthlySummary({
        year: filters.year,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
        page: pagination.value.page,
        pageSize: pagination.value.pageSize,
        sortBy: sortBy.value || undefined,
        sortOrder: sortOrder.value,
      })
      stats.value = res.stats
      tableData.value = res.list
      summaryRow.value = res.summary
      pagination.value = res.pagination
    } catch (e) {
      console.error('Failed to fetch trip data', e)
    } finally {
      loading.value = false
    }
  }

  // Fetch daily count (heatmap)
  async function fetchDailyTripCount() {
    dailyTripLoading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripDailyCount({
        year: dailyTripMonth.value.year,
        month: dailyTripMonth.value.month,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
      })
      dailyTripData.value = res
    } catch (e) {
      console.error('Failed to fetch daily trip count', e)
    } finally {
      dailyTripLoading.value = false
    }
  }

  function setDailyTripMonth(year, month) {
    dailyTripMonth.value = { year, month }
    fetchDailyTripCount()
  }

  // Fetch daily detail for one employee
  async function fetchDailyDetail(employeeId, employeeName, year, month) {
    selectedCell.value = { employeeId, employeeName, year, month }
    calendarVisible.value = true
    calendarLoading.value = true
    try {
      const res = await api.getTripDailyDetail({ employeeId, year, month })
      calendarData.value = res
    } catch (e) {
      console.error('Failed to fetch trip daily detail', e)
    } finally {
      calendarLoading.value = false
    }
  }

  function closeCalendar() {
    calendarVisible.value = false
    calendarData.value = { employeeName: '', records: [] }
    selectedCell.value = null
  }

  // Today detail
  async function fetchTodayTripDetail(type = '') {
    todayTripType.value = type
    todayTripVisible.value = true
    todayTripLoading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripToday({
        deptId,
        tripType: type || undefined,
        employeeName: filters.employeeName || undefined,
      })
      todayTripDetail.value = res.list
    } catch (e) {
      console.error('Failed to fetch today trip detail', e)
    } finally {
      todayTripLoading.value = false
    }
  }

  function closeTodayTrip() {
    todayTripVisible.value = false
    todayTripDetail.value = []
  }

  // Search / reset
  function search() {
    pagination.value.page = 1
    fetchData()
    fetchDailyTripCount()
  }

  function resetFilters() {
    filters.dept1 = null
    filters.dept2 = null
    filters.tripType = ''
    filters.employeeName = ''
    departments2.value = []
    search()
  }

  // Pagination
  function goToPage(p) {
    pagination.value.page = p
    fetchData()
  }

  function setPageSize(size) {
    pagination.value.pageSize = size
    pagination.value.page = 1
    fetchData()
  }

  // Sort
  function toggleSort(field) {
    if (sortBy.value === field) {
      sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
    } else {
      sortBy.value = field
      sortOrder.value = 'desc'
    }
    fetchData()
  }

  // Sync
  async function triggerTripSync(month) {
    syncing.value = true
    try {
      await api.triggerTripSync(month)
    } catch (e) {
      console.error('Failed to trigger trip sync', e)
    } finally {
      setTimeout(() => { syncing.value = false }, 3000)
    }
  }

  // Export
  async function exportTripExcel() {
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const blob = await api.exportTripExcel({
        year: filters.year,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
      })
      const { saveAs } = await import('file-saver')
      saveAs(blob, `外出出差统计_${filters.year}.xlsx`)
    } catch (e) {
      console.error('Failed to export trip excel', e)
    }
  }

  return {
    filters, departments1, departments2,
    tableData, summaryRow, stats, pagination, sortBy, sortOrder, loading,
    dailyTripMonth, dailyTripData, dailyTripLoading,
    todayTripVisible, todayTripDetail, todayTripLoading, todayTripType,
    calendarVisible, calendarData, calendarLoading, selectedCell,
    syncing, yearOptions,
    loadDepartments1, loadDepartments2,
    fetchData, fetchDailyTripCount, setDailyTripMonth,
    fetchDailyDetail, closeCalendar,
    fetchTodayTripDetail, closeTodayTrip,
    search, resetFilters, goToPage, setPageSize, toggleSort,
    triggerTripSync, exportTripExcel,
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useTripData.js
git commit -m "feat: add useTripData composable for trip state management"
```

---

## Task 11: TripStatsCards + TripFilterPanel Components

**Files:**
- Create: `frontend/src/components/TripStatsCards.vue`
- Create: `frontend/src/components/TripFilterPanel.vue`

- [ ] **Step 1: Create TripStatsCards.vue**

Create `frontend/src/components/TripStatsCards.vue` — follow the exact pattern from `StatsCards.vue` (4 cards, same spacing/sizing, same Tailwind classes):

```vue
<script setup>
import { Briefcase, MapPin, CalendarDays, Users } from 'lucide-vue-next'

const props = defineProps({
  stats: {
    type: Object,
    default: () => ({ totalCount: 0, totalDays: 0, todayTripCount: 0, todayOutingCount: 0 })
  }
})

const emit = defineEmits(['todayTripClick', 'todayOutingClick'])
</script>

<template>
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
    <!-- Card 1: Total count -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">总人次</span>
        <div class="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center">
          <Users :size="18" class="text-accent" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-text-primary leading-none">
          {{ stats.totalCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人次</span>
      </div>
    </div>

    <!-- Card 2: Total days -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">总天数</span>
        <div class="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">
          <CalendarDays :size="18" class="text-green-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-accent leading-none">
          {{ stats.totalDays }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">天</span>
      </div>
    </div>

    <!-- Card 3: Today trip (clickable) -->
    <div
      class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 cursor-pointer hover:border-accent/40 hover:shadow-sm transition-all"
      @click="emit('todayTripClick')"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">今日出差</span>
        <div class="w-9 h-9 rounded-lg bg-orange-50 flex items-center justify-center">
          <Briefcase :size="18" class="text-orange-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-orange-600 leading-none">
          {{ stats.todayTripCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人</span>
      </div>
    </div>

    <!-- Card 4: Today outing (clickable) -->
    <div
      class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 cursor-pointer hover:border-accent/40 hover:shadow-sm transition-all"
      @click="emit('todayOutingClick')"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">今日外出</span>
        <div class="w-9 h-9 rounded-lg bg-purple-50 flex items-center justify-center">
          <MapPin :size="18" class="text-purple-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-purple-600 leading-none">
          {{ stats.todayOutingCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人</span>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Create TripFilterPanel.vue**

Create `frontend/src/components/TripFilterPanel.vue` — follow the exact pattern from `FilterPanel.vue` but replace leave type multi-select with a segmented control (全部/出差/外出):

```vue
<script setup>
import { Search, RotateCcw } from 'lucide-vue-next'

const props = defineProps({
  filters: { type: Object, required: true },
  departments1: { type: Array, default: () => [] },
  departments2: { type: Array, default: () => [] },
  yearOptions: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:filters', 'dept1Change', 'search', 'reset'
])

const tripTypeOptions = [
  { label: '全部', value: '' },
  { label: '出差', value: '出差' },
  { label: '外出', value: '外出' },
]

function onDept1Change(val) {
  emit('update:filters', { ...props.filters, dept1: val || null, dept2: null })
  emit('dept1Change', val)
}

function onDept2Change(val) {
  emit('update:filters', { ...props.filters, dept2: val || null })
}

function onTripTypeChange(val) {
  emit('update:filters', { ...props.filters, tripType: val })
}

function onYearChange(val) {
  emit('update:filters', { ...props.filters, year: Number(val) })
}

function onNameChange(val) {
  emit('update:filters', { ...props.filters, employeeName: val })
}
</script>

<template>
  <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
    <div class="flex flex-wrap items-end gap-3 sm:gap-4">
      <!-- Department 1 -->
      <div class="w-full sm:w-auto">
        <label class="block text-[12px] font-medium text-text-secondary mb-1">一级部门</label>
        <select
          class="h-9 w-full sm:w-40 rounded-lg border border-border-default bg-white px-3 text-[13px] text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 outline-none"
          :value="filters.dept1"
          @change="onDept1Change($event.target.value ? Number($event.target.value) : null)"
        >
          <option :value="null">全部部门</option>
          <option v-for="d in departments1" :key="d.dept_id" :value="d.dept_id">{{ d.name }}</option>
        </select>
      </div>

      <!-- Department 2 -->
      <div v-if="departments2.length > 0" class="w-full sm:w-auto">
        <label class="block text-[12px] font-medium text-text-secondary mb-1">二级部门</label>
        <select
          class="h-9 w-full sm:w-40 rounded-lg border border-border-default bg-white px-3 text-[13px] text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 outline-none"
          :value="filters.dept2"
          @change="onDept2Change($event.target.value ? Number($event.target.value) : null)"
        >
          <option :value="null">全部</option>
          <option v-for="d in departments2" :key="d.dept_id" :value="d.dept_id">{{ d.name }}</option>
        </select>
      </div>

      <!-- Trip type segmented control -->
      <div class="w-full sm:w-auto">
        <label class="block text-[12px] font-medium text-text-secondary mb-1">类型</label>
        <div class="inline-flex rounded-lg border border-border-default overflow-hidden">
          <button
            v-for="opt in tripTypeOptions"
            :key="opt.value"
            class="h-9 px-3 text-[13px] font-medium transition-colors"
            :class="filters.tripType === opt.value
              ? 'bg-accent text-white'
              : 'bg-white text-text-secondary hover:bg-surface-secondary'"
            @click="onTripTypeChange(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <!-- Year -->
      <div class="w-full sm:w-auto">
        <label class="block text-[12px] font-medium text-text-secondary mb-1">年份</label>
        <select
          class="h-9 w-full sm:w-24 rounded-lg border border-border-default bg-white px-3 text-[13px] text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 outline-none"
          :value="filters.year"
          @change="onYearChange($event.target.value)"
        >
          <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>

      <!-- Employee name -->
      <div class="w-full sm:w-auto">
        <label class="block text-[12px] font-medium text-text-secondary mb-1">员工姓名</label>
        <input
          type="text"
          class="h-9 w-full sm:w-32 rounded-lg border border-border-default bg-white px-3 text-[13px] text-text-primary placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent/30 outline-none"
          placeholder="搜索姓名"
          :value="filters.employeeName"
          @input="onNameChange($event.target.value)"
          @keyup.enter="emit('search')"
        />
      </div>

      <!-- Buttons -->
      <div class="flex gap-2">
        <button
          class="h-9 px-4 rounded-lg bg-accent text-white text-[13px] font-medium hover:bg-accent/90 transition-colors flex items-center gap-1.5"
          :disabled="loading"
          @click="emit('search')"
        >
          <Search :size="14" />
          查询
        </button>
        <button
          class="h-9 px-4 rounded-lg border border-border-default text-[13px] font-medium text-text-secondary hover:bg-surface-secondary transition-colors flex items-center gap-1.5"
          @click="emit('reset')"
        >
          <RotateCcw :size="14" />
          重置
        </button>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TripStatsCards.vue frontend/src/components/TripFilterPanel.vue
git commit -m "feat: add TripStatsCards and TripFilterPanel components"
```

---

## Task 12: TripDataTable + TripTodayModal + TripDailyStats

**Files:**
- Create: `frontend/src/components/TripDataTable.vue`
- Create: `frontend/src/components/TripTodayModal.vue`
- Create: `frontend/src/components/TripDailyStats.vue`

- [ ] **Step 1: Create TripDataTable.vue**

Create `frontend/src/components/TripDataTable.vue` following the exact pattern of `DataTable.vue` (same table styles, pagination, sort headers). Key differences: columns are 姓名, 部门, 出差(天), 外出(天), 1月~12月, 合计. Read `DataTable.vue` fully before writing to match style exactly.

The component should:
- Accept props: `tableData`, `summaryRow`, `pagination`, `sortBy`, `sortOrder`, `loading`
- Emit: `sort`, `page-change`, `page-size-change`, `cell-click`
- Render monthly columns from `row.months` dict
- Reuse `Pagination.vue` component for pagination
- Make employee name clickable (emits `cell-click` with employeeId, month)

- [ ] **Step 2: Create TripTodayModal.vue**

Create `frontend/src/components/TripTodayModal.vue` following the pattern of `TodayLeaveModal.vue`. Key differences: show `tagName` (出差/外出) column instead of leave type, show `beginTime`~`endTime` range. Read `TodayLeaveModal.vue` fully before writing to match style exactly.

- [ ] **Step 3: Create TripDailyStats.vue**

Create `frontend/src/components/TripDailyStats.vue` following the pattern of `DailyLeaveStats.vue`. Same heatmap grid + detail list layout. Read `DailyLeaveStats.vue` fully before writing. Uses `dailyTripData.days` for heatmap colors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TripDataTable.vue frontend/src/components/TripTodayModal.vue frontend/src/components/TripDailyStats.vue
git commit -m "feat: add TripDataTable, TripTodayModal, TripDailyStats components"
```

---

## Task 13: AppHeader Navigation Update

**Files:**
- Modify: `frontend/src/components/AppHeader.vue`

- [ ] **Step 1: Add trip nav tab to desktop navigation**

In the desktop `<nav>` section of `AppHeader.vue`, add a new button after the "数据导出" button and before the "数据分析" button:

```vue
      <button
        class="px-3 py-1.5 text-[13px] rounded-md transition-colors"
        :class="activePage === 'trip'
          ? 'bg-highlight text-accent font-semibold'
          : 'text-text-secondary font-medium hover:text-text-primary'"
        @click="emit('page-change', 'trip')"
      >
        外出/出差
      </button>
```

- [ ] **Step 2: Add trip nav tab to mobile bottom bar**

In the mobile bottom tab bar section, add a new tab between "数据导出" and "数据分析". Import `Briefcase` from lucide-vue-next. Use the same pattern as existing tabs:

```vue
      <button
        class="flex-1 flex flex-col items-center justify-center gap-0.5 py-2"
        :class="activePage === 'trip' ? 'text-accent' : 'text-text-tertiary'"
        @click="emit('page-change', 'trip')"
      >
        <Briefcase :size="20" />
        <span class="text-[10px] font-medium">外出/出差</span>
      </button>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AppHeader.vue
git commit -m "feat: add trip tab to desktop and mobile navigation"
```

---

## Task 14: MainView Integration

**Files:**
- Modify: `frontend/src/views/MainView.vue`

- [ ] **Step 1: Import trip components and composable**

Add imports at the top of `MainView.vue`:

```javascript
import { useTripData } from '../composables/useTripData.js'
import TripFilterPanel from '../components/TripFilterPanel.vue'
import TripStatsCards from '../components/TripStatsCards.vue'
import TripDataTable from '../components/TripDataTable.vue'
import TripDailyStats from '../components/TripDailyStats.vue'
import TripTodayModal from '../components/TripTodayModal.vue'
```

- [ ] **Step 2: Destructure useTripData**

After the existing `useLeaveData()` destructure block, add:

```javascript
const {
  filters: tripFilters,
  departments1: tripDepts1,
  departments2: tripDepts2,
  tableData: tripTableData,
  summaryRow: tripSummaryRow,
  stats: tripStats,
  pagination: tripPagination,
  sortBy: tripSortBy,
  sortOrder: tripSortOrder,
  loading: tripLoading,
  dailyTripMonth, dailyTripData, dailyTripLoading,
  todayTripVisible, todayTripDetail, todayTripLoading, todayTripType,
  calendarVisible: tripCalendarVisible,
  calendarData: tripCalendarData,
  calendarLoading: tripCalendarLoading,
  selectedCell: tripSelectedCell,
  syncing: tripSyncing,
  yearOptions: tripYearOptions,
  loadDepartments1: loadTripDepts1,
  loadDepartments2: loadTripDepts2,
  fetchData: fetchTripData,
  fetchDailyTripCount, setDailyTripMonth,
  fetchDailyDetail: fetchTripDailyDetail,
  closeCalendar: closeTripCalendar,
  fetchTodayTripDetail, closeTodayTrip,
  search: tripSearch,
  resetFilters: tripResetFilters,
  goToPage: tripGoToPage,
  setPageSize: tripSetPageSize,
  toggleSort: tripToggleSort,
  triggerTripSync, exportTripExcel,
} = useTripData()
```

- [ ] **Step 3: Add trip tab state**

Add after the existing `activeTab` ref:

```javascript
const activeTripTab = ref('table')
```

- [ ] **Step 4: Initialize trip data on mount**

In the existing `onMounted` callback, add:

```javascript
  loadTripDepts1()
  fetchTripData()
  fetchDailyTripCount()
```

- [ ] **Step 5: Add trip page template section**

In the template, after the existing export page section (`v-if="activePage === 'export'"`) and before the analytics section, add the trip page:

```vue
    <!-- Trip Page -->
    <div v-if="activePage === 'trip'" class="space-y-4 sm:space-y-6">
      <div>
        <h2 class="text-lg sm:text-xl font-bold text-text-primary">外出/出差统计</h2>
        <p class="text-[13px] text-text-secondary mt-1">查看员工出差和外出记录统计</p>
      </div>

      <TripFilterPanel
        :filters="tripFilters"
        :departments1="tripDepts1"
        :departments2="tripDepts2"
        :yearOptions="tripYearOptions"
        :loading="tripLoading"
        @update:filters="Object.assign(tripFilters, $event)"
        @dept1Change="loadTripDepts2"
        @search="tripSearch"
        @reset="tripResetFilters"
      />

      <TripStatsCards
        :stats="tripStats"
        @todayTripClick="fetchTodayTripDetail('出差')"
        @todayOutingClick="fetchTodayTripDetail('外出')"
      />

      <!-- Tab switcher -->
      <div class="flex gap-1 bg-surface-secondary rounded-lg p-1 w-fit">
        <button
          class="px-4 py-1.5 rounded-md text-[13px] font-medium transition-colors"
          :class="activeTripTab === 'table' ? 'bg-white text-accent shadow-sm' : 'text-text-secondary hover:text-text-primary'"
          @click="activeTripTab = 'table'"
        >
          出差/外出列表
        </button>
        <button
          class="px-4 py-1.5 rounded-md text-[13px] font-medium transition-colors"
          :class="activeTripTab === 'daily' ? 'bg-white text-accent shadow-sm' : 'text-text-secondary hover:text-text-primary'"
          @click="activeTripTab = 'daily'; fetchDailyTripCount()"
        >
          每日统计
        </button>
      </div>

      <TripDataTable
        v-if="activeTripTab === 'table'"
        :tableData="tripTableData"
        :summaryRow="tripSummaryRow"
        :pagination="tripPagination"
        :sortBy="tripSortBy"
        :sortOrder="tripSortOrder"
        :loading="tripLoading"
        @sort="tripToggleSort"
        @page-change="tripGoToPage"
        @page-size-change="tripSetPageSize"
        @cell-click="(empId, name, month) => fetchTripDailyDetail(empId, name, tripFilters.year, month)"
      />

      <TripDailyStats
        v-if="activeTripTab === 'daily'"
        :dailyData="dailyTripData"
        :month="dailyTripMonth"
        :loading="dailyTripLoading"
        @month-change="setDailyTripMonth"
      />

      <TripTodayModal
        :visible="todayTripVisible"
        :detail="todayTripDetail"
        :loading="todayTripLoading"
        :tripType="todayTripType"
        @close="closeTodayTrip"
      />
    </div>
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/MainView.vue
git commit -m "feat: integrate trip page into MainView with full data flow"
```

---

## Task 15: StatsCards Enhancement (6th Card)

**Files:**
- Modify: `frontend/src/components/StatsCards.vue`
- Modify: `frontend/src/views/MainView.vue`

- [ ] **Step 1: Add todayTripCount prop and 6th card to StatsCards**

In `StatsCards.vue`, add a new prop:

```javascript
  todayTripCount: {
    type: Number,
    default: 0
  }
```

Add a new emit:

```javascript
const emit = defineEmits(['todayLeaveClick', 'todayTripClick'])
```

Change the grid class from `grid-cols-2 sm:grid-cols-3 lg:grid-cols-5` to `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6`.

Add a 6th card at the end of the grid:

```vue
    <!-- Card 6: Today trip/outing -->
    <div
      class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 cursor-pointer hover:border-accent/40 hover:shadow-sm transition-all"
      @click="emit('todayTripClick')"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">今日外出/出差</span>
        <div class="w-9 h-9 rounded-lg bg-orange-50 flex items-center justify-center">
          <Briefcase :size="18" class="text-orange-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-orange-600 leading-none">
          {{ todayTripCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人</span>
      </div>
    </div>
```

Import `Briefcase` from lucide-vue-next.

- [ ] **Step 2: Wire up in MainView**

In `MainView.vue`, where `<StatsCards>` is used, add the new props and event:

```vue
      <StatsCards
        :stats="stats"
        :unit="filters.unit"
        :todayLeaveCount="todayLeaveCount"
        :todayTripCount="(tripStats.todayTripCount || 0) + (tripStats.todayOutingCount || 0)"
        @todayLeaveClick="fetchTodayLeaveDetail"
        @todayTripClick="activePage = 'trip'"
      />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StatsCards.vue frontend/src/views/MainView.vue
git commit -m "feat: add today trip/outing card to leave StatsCards"
```

---

## Task 16: End-to-End Verification

- [ ] **Step 1: Start backend**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

Verify: No import errors, server starts cleanly.

- [ ] **Step 2: Test trip API endpoints**

```bash
# Test stats (should return zeros if no data synced yet)
curl -s http://localhost:8000/api/trip/stats?year=2026 -H "Authorization: Bearer <token>" | python -m json.tool

# Test monthly summary
curl -s "http://localhost:8000/api/trip/monthly-summary?year=2026" -H "Authorization: Bearer <token>" | python -m json.tool

# Test today
curl -s http://localhost:8000/api/trip/today -H "Authorization: Bearer <token>" | python -m json.tool
```

- [ ] **Step 3: Trigger trip sync (small test)**

```bash
# Trigger sync for current month only
curl -s -X POST http://localhost:8000/api/trip/sync -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"month":"2026-04"}'
```

Check backend logs for sync progress.

- [ ] **Step 4: Start frontend and verify UI**

```bash
cd frontend && npm run dev
```

Verify:
- "外出/出差" tab appears in header nav (desktop + mobile)
- Clicking it shows the trip page with filter panel, stats cards, table
- Stats cards show data (after sync completes)
- "数据导出" page has 6th card "今日外出/出差"

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete trip/outing integration - sync, API, and frontend"
```
