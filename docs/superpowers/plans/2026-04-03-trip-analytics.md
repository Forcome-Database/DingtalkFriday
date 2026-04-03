# Trip Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 trip/outing analytics charts below existing leave analytics on the data analysis page.

**Architecture:** New backend service + router (`trip_analytics.py`) query `trip_record` table, new frontend component (`TripAnalyticsSection.vue`) + composable render 5 ECharts charts. Embedded in existing `AnalyticsView.vue` via import.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, ECharts, TailwindCSS

**Spec:** `docs/superpowers/specs/2026-04-03-trip-analytics-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/schemas.py` | Add `TripTrendLine`, `TripMonthlyTrendResponse` |
| Create | `backend/app/services/trip_analytics.py` | 5 aggregation functions querying `trip_record` |
| Create | `backend/app/routers/trip_analytics.py` | 5 GET endpoints under `/api/analytics/trip` |
| Modify | `backend/app/main.py` | Register `trip_analytics.router` |
| Modify | `frontend/src/api/index.js` | Add 5 API client methods |
| Create | `frontend/src/composables/useTripAnalyticsData.js` | State management + concurrent data fetching |
| Create | `frontend/src/components/TripAnalyticsSection.vue` | Self-contained 5-chart component |
| Modify | `frontend/src/components/AnalyticsView.vue` | Import and embed `TripAnalyticsSection` |

---

### Task 1: Add Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add TripTrendLine and TripMonthlyTrendResponse to schemas.py**

At the end of the Analytics schemas section (after `EmployeeRankingResponse`, around line 310), add:

```python
# ---------------------------------------------------------------------------
# Trip Analytics schemas
# ---------------------------------------------------------------------------

class TripTrendLine(BaseModel):
    """Single month data point for the trip monthly trend chart."""
    month: int = Field(description="Month number (1-12)")
    days: float = Field(description="Total trip/outing days in this month")


class TripMonthlyTrendResponse(BaseModel):
    """Response for GET /api/analytics/trip/monthly-trend."""
    trip: List[TripTrendLine] = Field(description="Business trip monthly days")
    outing: List[TripTrendLine] = Field(description="Out-of-office monthly days")
```

- [ ] **Step 2: Verify import**

Run: `cd E:/Project/DingtalkFriday/backend && python -c "from app.schemas import TripMonthlyTrendResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(analytics): add trip analytics schemas"
```

---

### Task 2: Create Trip Analytics Service

**Files:**
- Create: `backend/app/services/trip_analytics.py`

- [ ] **Step 1: Create trip_analytics.py with all 5 service functions**

```python
"""
Trip analytics data service.

Provides aggregation queries for trip/outing dashboard analytics:
- Monthly trip trend (出差 vs 外出 dual lines)
- Trip type distribution (出差 vs 外出 ratio)
- Department comparison
- Weekday distribution
- Employee trip ranking
"""

import logging
from collections import defaultdict
from typing import Dict, List

from sqlalchemy import select, and_, extract

from app.database import async_session
from app.models import Employee, TripRecord

logger = logging.getLogger(__name__)

WEEKDAY_LABELS = {
    0: "周一",
    1: "周二",
    2: "周三",
    3: "周四",
    4: "周五",
}


async def _load_year_trip_records(year: int) -> List[TripRecord]:
    """Load all trip records whose work_date falls within the given year."""
    async with async_session() as session:
        result = await session.execute(
            select(TripRecord).where(
                and_(
                    TripRecord.work_date >= f"{year}-01-01",
                    TripRecord.work_date <= f"{year}-12-31",
                )
            )
        )
        return list(result.scalars().all())


async def _load_employees() -> Dict[str, Employee]:
    """Load all employees as a {userid: Employee} map."""
    async with async_session() as session:
        result = await session.execute(select(Employee))
        return {e.userid: e for e in result.scalars().all()}


def _hours_to_days(hours: float) -> float:
    """Convert duration_hours to days (8 hours = 1 day)."""
    return hours / 8.0


# ---------------------------------------------------------------------------
# 1. Monthly trend (出差 vs 外出 dual lines)
# ---------------------------------------------------------------------------

async def get_trip_monthly_trend(year: int) -> dict:
    records = await _load_year_trip_records(year)

    trip_monthly: Dict[int, float] = {m: 0.0 for m in range(1, 13)}
    outing_monthly: Dict[int, float] = {m: 0.0 for m in range(1, 13)}

    for rec in records:
        month = int(rec.work_date[5:7])
        days = _hours_to_days(rec.duration_hours)
        if rec.tag_name == "出差":
            trip_monthly[month] += days
        else:
            outing_monthly[month] += days

    return {
        "trip": [{"month": m, "days": round(trip_monthly[m], 1)} for m in range(1, 13)],
        "outing": [{"month": m, "days": round(outing_monthly[m], 1)} for m in range(1, 13)],
    }


# ---------------------------------------------------------------------------
# 2. Trip type distribution (出差 vs 外出)
# ---------------------------------------------------------------------------

async def get_trip_type_distribution(year: int) -> dict:
    records = await _load_year_trip_records(year)

    type_days: Dict[str, float] = defaultdict(float)
    for rec in records:
        type_days[rec.tag_name] += _hours_to_days(rec.duration_hours)

    total = sum(type_days.values())
    items = []
    for tag_name, days in sorted(type_days.items(), key=lambda x: -x[1]):
        ratio = round(days / total * 100, 1) if total > 0 else 0.0
        items.append({"type": tag_name, "days": round(days, 1), "ratio": ratio})

    return {"total": round(total, 1), "items": items}


# ---------------------------------------------------------------------------
# 3. Department comparison
# ---------------------------------------------------------------------------

async def get_trip_department_comparison(year: int, metric: str = "total") -> dict:
    records = await _load_year_trip_records(year)
    emp_map = await _load_employees()

    dept_headcount: Dict[str, int] = defaultdict(int)
    for emp in emp_map.values():
        dept_headcount[emp.dept_name or "未分配"] += 1

    dept_days: Dict[str, float] = defaultdict(float)
    for rec in records:
        emp = emp_map.get(rec.userid)
        if not emp:
            continue
        dept_name = emp.dept_name or "未分配"
        dept_days[dept_name] += _hours_to_days(rec.duration_hours)

    departments = []
    for dept_name, headcount in dept_headcount.items():
        total_days = dept_days.get(dept_name, 0.0)
        avg_days = total_days / headcount if headcount > 0 else 0.0
        departments.append({
            "name": dept_name,
            "totalDays": round(total_days, 1),
            "avgDays": round(avg_days, 1),
            "headcount": headcount,
        })

    sort_key = "avgDays" if metric == "avg" else "totalDays"
    departments.sort(key=lambda d: d[sort_key], reverse=True)

    avg = 0.0
    if departments:
        avg = sum(d[sort_key] for d in departments) / len(departments)

    return {"departments": departments, "average": round(avg, 1)}


# ---------------------------------------------------------------------------
# 4. Weekday distribution
# ---------------------------------------------------------------------------

async def get_trip_weekday_distribution(year: int) -> dict:
    records = await _load_year_trip_records(year)

    from datetime import date as date_type
    weekday_counts: Dict[int, int] = {i: 0 for i in range(5)}

    for rec in records:
        parts = rec.work_date.split("-")
        d = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        wd = d.weekday()
        if wd in weekday_counts:
            weekday_counts[wd] += 1

    weekdays = [
        {"day": wd + 1, "label": WEEKDAY_LABELS[wd], "count": weekday_counts[wd]}
        for wd in range(5)
    ]
    return {"weekdays": weekdays}


# ---------------------------------------------------------------------------
# 5. Employee trip ranking
# ---------------------------------------------------------------------------

async def get_trip_employee_ranking(year: int, limit: int = 10) -> dict:
    records = await _load_year_trip_records(year)
    emp_map = await _load_employees()

    # { userid: { tag_name: total_days } }
    emp_type_days: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for rec in records:
        if rec.userid not in emp_map:
            continue
        emp_type_days[rec.userid][rec.tag_name] += _hours_to_days(rec.duration_hours)

    ranked = []
    for uid, type_days in emp_type_days.items():
        emp = emp_map.get(uid)
        if not emp:
            continue
        total = sum(type_days.values())
        breakdown = [
            {"type": t, "days": round(d, 1)}
            for t, d in sorted(type_days.items(), key=lambda x: -x[1])
        ]
        ranked.append({
            "name": emp.name,
            "dept": emp.dept_name or "",
            "total": round(total, 1),
            "breakdown": breakdown,
        })

    ranked.sort(key=lambda r: r["total"], reverse=True)
    ranked = ranked[:limit]

    return {"employees": ranked}
```

- [ ] **Step 2: Verify import**

Run: `cd E:/Project/DingtalkFriday/backend && python -c "from app.services.trip_analytics import get_trip_monthly_trend; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/trip_analytics.py
git commit -m "feat(analytics): add trip analytics service with 5 aggregation functions"
```

---

### Task 3: Create Trip Analytics Router + Register

**Files:**
- Create: `backend/app/routers/trip_analytics.py`
- Modify: `backend/app/main.py:194`

- [ ] **Step 1: Create trip_analytics.py router**

```python
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
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, after line 194 (`app.include_router(trip.router)`), add:

```python
app.include_router(trip_analytics.router)
```

Also add the import at the top where other router imports are (around line 10-15):

```python
from app.routers import trip_analytics
```

- [ ] **Step 3: Verify server starts**

Run: `cd E:/Project/DingtalkFriday/backend && python -c "from app.main import app; print('Routes:', [r.path for r in app.routes if 'trip/monthly-trend' in getattr(r, 'path', '')])"` 
Expected: Shows the `/api/analytics/trip/monthly-trend` route

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/trip_analytics.py backend/app/main.py
git commit -m "feat(analytics): add trip analytics router with 5 endpoints"
```

---

### Task 4: Add Frontend API Client Methods

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add 5 trip analytics API methods**

After the existing analytics API methods (around line 248, after `getEmployeeRanking`), add:

```javascript
  // --- Trip Analytics API ---

  getTripMonthlyTrend(year) {
    return api.get('/analytics/trip/monthly-trend', { params: { year } })
  },

  getTripTypeDistribution(year) {
    return api.get('/analytics/trip/type-distribution', { params: { year } })
  },

  getTripDepartmentComparison(year, metric = 'total') {
    return api.get('/analytics/trip/department-comparison', { params: { year, metric } })
  },

  getTripWeekdayDistribution(year) {
    return api.get('/analytics/trip/weekday-distribution', { params: { year } })
  },

  getTripEmployeeRanking(year, limit = 10) {
    return api.get('/analytics/trip/employee-ranking', { params: { year, limit } })
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat(analytics): add trip analytics API client methods"
```

---

### Task 5: Create Trip Analytics Composable

**Files:**
- Create: `frontend/src/composables/useTripAnalyticsData.js`

- [ ] **Step 1: Create useTripAnalyticsData.js**

```javascript
import { ref, watch } from 'vue'
import api from '../api/index.js'

/**
 * Composable for managing trip analytics dashboard data.
 * Provides year-based data fetching for all trip analytics charts.
 */
export function useTripAnalyticsData(yearRef) {
  const loading = ref(false)

  // Chart data refs
  const monthlyTrend = ref(null)
  const typeDistribution = ref(null)
  const departmentComparison = ref(null)
  const weekdayDistribution = ref(null)
  const employeeRanking = ref(null)

  async function fetchAll(targetYear) {
    loading.value = true
    try {
      const [trendData, typeData, deptData, weekdayData, rankingData] = await Promise.all([
        api.getTripMonthlyTrend(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch monthly trend:', err)
          return null
        }),
        api.getTripTypeDistribution(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch type distribution:', err)
          return null
        }),
        api.getTripDepartmentComparison(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch department comparison:', err)
          return null
        }),
        api.getTripWeekdayDistribution(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch weekday distribution:', err)
          return null
        }),
        api.getTripEmployeeRanking(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch employee ranking:', err)
          return null
        }),
      ])

      monthlyTrend.value = trendData
      typeDistribution.value = typeData
      departmentComparison.value = deptData
      weekdayDistribution.value = weekdayData
      employeeRanking.value = rankingData
    } catch (err) {
      console.error('[TripAnalytics] Unexpected error in fetchAll:', err)
      monthlyTrend.value = null
      typeDistribution.value = null
      departmentComparison.value = null
      weekdayDistribution.value = null
      employeeRanking.value = null
    } finally {
      loading.value = false
    }
  }

  // Watch year prop changes and re-fetch
  watch(yearRef, (newYear) => {
    fetchAll(newYear)
  })

  return {
    loading,
    monthlyTrend,
    typeDistribution,
    departmentComparison,
    weekdayDistribution,
    employeeRanking,
    fetchAll,
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useTripAnalyticsData.js
git commit -m "feat(analytics): add trip analytics composable"
```

---

### Task 6: Create TripAnalyticsSection Component

**Files:**
- Create: `frontend/src/components/TripAnalyticsSection.vue`

This is the largest task. The component contains 5 ECharts chart renderers following the same patterns as `AnalyticsView.vue`.

- [ ] **Step 1: Create TripAnalyticsSection.vue**

```vue
<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick, toRef } from 'vue'
import { useTripAnalyticsData } from '../composables/useTripAnalyticsData.js'
import apiClient from '../api/index.js'

import * as echarts from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, PieChart, BarChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
  CanvasRenderer
])

const props = defineProps({
  year: { type: Number, required: true }
})

// --- Color constants ---
const TRIP_COLOR = '#2563EB'
const OUTING_COLOR = '#059669'

// --- Data ---
const {
  loading,
  monthlyTrend,
  typeDistribution,
  departmentComparison,
  weekdayDistribution,
  employeeRanking,
  fetchAll,
} = useTripAnalyticsData(toRef(props, 'year'))

// --- Department metric toggle ---
const deptMetric = ref('total')

// --- Chart DOM refs ---
const trendChartRef = ref(null)
const pieChartRef = ref(null)
const deptChartRef = ref(null)
const weekdayChartRef = ref(null)
const rankingChartRef = ref(null)

// --- Chart instances ---
let trendChart = null
let pieChart = null
let deptChart = null
let weekdayChart = null
let rankingChart = null

// --- Computed ---
const pieTotal = computed(() => typeDistribution.value?.total || 0)

// --- Chart helpers ---
function ensureChartInstance(instance, domRef) {
  if (instance && instance.getDom() !== domRef.value) {
    instance.dispose()
    instance = null
  }
  if (!instance) {
    instance = echarts.init(domRef.value)
  }
  return instance
}

function getTypeColor(typeName) {
  return typeName === '出差' ? TRIP_COLOR : OUTING_COLOR
}

// --- 1. Monthly trend (dual lines: 出差 vs 外出) ---
function renderTrendChart() {
  if (!trendChartRef.value) return
  trendChart = ensureChartInstance(trendChart, trendChartRef)

  const data = monthlyTrend.value
  const tripData = data?.trip?.map(i => i.days) || Array(12).fill(0)
  const outingData = data?.outing?.map(i => i.days) || Array(12).fill(0)
  const months = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#E4E4E7',
      borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      valueFormatter: (value) => `${value}天`
    },
    legend: {
      data: ['出差', '外出'],
      top: 0, right: 0,
      textStyle: { fontSize: 12, color: '#71717A' },
      itemWidth: 16, itemHeight: 2
    },
    grid: { top: 36, left: 12, right: 12, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category', data: months, boundaryGap: false,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    series: [
      {
        name: '出差', type: 'line', data: tripData,
        smooth: true, symbol: 'circle', symbolSize: 6, showSymbol: false,
        itemStyle: { color: TRIP_COLOR },
        lineStyle: { width: 2.5, color: TRIP_COLOR },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(37, 99, 235, 0.15)' },
            { offset: 1, color: 'rgba(37, 99, 235, 0.01)' }
          ])
        }
      },
      {
        name: '外出', type: 'line', data: outingData,
        smooth: true, symbol: 'circle', symbolSize: 6, showSymbol: false,
        itemStyle: { color: OUTING_COLOR },
        lineStyle: { width: 2.5, color: OUTING_COLOR }
      }
    ]
  }, true)
}

// --- 2. Type distribution (donut: 出差 vs 外出) ---
function renderPieChart() {
  if (!pieChartRef.value) return
  pieChart = ensureChartInstance(pieChart, pieChartRef)

  const raw = typeDistribution.value
  const data = raw?.items || []
  const total = pieTotal.value

  pieChart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: '#fff', borderColor: '#E4E4E7', borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      formatter: (params) => `${params.name}: ${params.value}天 (${params.percent}%)`
    },
    graphic: [
      {
        id: 'pie-total-value', type: 'text', left: 'center', top: '42%',
        style: { text: `${total}`, textAlign: 'center', fill: '#18181B', fontSize: 22, fontWeight: 600 }
      },
      {
        id: 'pie-total-label', type: 'text', left: 'center', top: '55%',
        style: { text: '总天数', textAlign: 'center', fill: '#A1A1AA', fontSize: 12 }
      }
    ],
    series: [{
      type: 'pie', radius: ['65%', '88%'], center: ['50%', '50%'],
      avoidLabelOverlap: false, label: { show: false }, labelLine: { show: false },
      data: data.map(item => ({
        name: item.type, value: item.days,
        itemStyle: { color: getTypeColor(item.type) }
      }))
    }]
  }, true)
}

// --- 3. Department comparison (horizontal bar) ---
function renderDeptChart() {
  if (!deptChartRef.value) return
  deptChart = ensureChartInstance(deptChart, deptChartRef)

  const raw = departmentComparison.value
  const items = raw?.departments || []
  const sortKey = deptMetric.value === 'avg' ? 'avgDays' : 'totalDays'
  const top = [...items].sort((a, b) => b[sortKey] - a[sortKey]).slice(0, 10)
  const sorted = [...top].reverse()
  const depts = sorted.map(d => d.name)
  const values = sorted.map(d => d[sortKey])
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0

  const chartHeight = Math.max(250, sorted.length * 32 + 60)
  deptChartRef.value.style.height = `${chartHeight}px`
  deptChart.resize()

  deptChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: '#fff', borderColor: '#E4E4E7', borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      valueFormatter: (value) => `${value}天`
    },
    grid: { top: 36, left: 12, right: 50, bottom: 4, containLabel: true },
    xAxis: {
      type: 'value',
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    yAxis: {
      type: 'category', data: depts,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#71717A', fontSize: 12, width: 120, overflow: 'truncate', ellipsis: '...' }
    },
    series: [{
      type: 'bar', data: values, barMaxWidth: 22, barMinWidth: 12,
      itemStyle: { color: TRIP_COLOR, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: '#71717A', fontSize: 11, formatter: '{c}天' },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: '#F59E0B', type: 'dashed', width: 1.5 },
        label: {
          position: 'insideEndTop',
          formatter: `均值: ${Math.round(avg * 10) / 10}天`,
          fontSize: 11, color: '#F59E0B', padding: [2, 6]
        },
        data: [{ xAxis: avg }]
      }
    }]
  }, true)
}

// --- 4. Weekday distribution (vertical bar) ---
function renderWeekdayChart() {
  if (!weekdayChartRef.value) return
  weekdayChart = ensureChartInstance(weekdayChart, weekdayChartRef)

  const data = weekdayDistribution.value?.weekdays || []
  const weekdays = data.map(d => d.label)
  const values = data.map(d => d.count)

  weekdayChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: '#fff', borderColor: '#E4E4E7', borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      valueFormatter: (value) => `${value}次`
    },
    grid: { top: 24, left: 12, right: 12, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category', data: weekdays,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#71717A', fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    series: [{
      type: 'bar',
      data: values.map((v, i) => ({
        value: v,
        itemStyle: {
          color: (i === 0 || i === 4) ? TRIP_COLOR : '#93BBFD',
          borderRadius: [4, 4, 0, 0]
        }
      })),
      barWidth: 32,
      label: { show: true, position: 'top', color: '#71717A', fontSize: 11, formatter: '{c}次' }
    }]
  }, true)
}

// --- 5. Employee ranking (stacked horizontal bar) ---
function renderRankingChart() {
  if (!rankingChartRef.value) return
  rankingChart = ensureChartInstance(rankingChart, rankingChartRef)

  const data = employeeRanking.value?.employees || []
  const reversed = [...data].reverse()
  const names = reversed.map(d => d.name)

  const typeSet = new Set()
  data.forEach(d => d.breakdown?.forEach(b => typeSet.add(b.type)))
  const types = [...typeSet]

  const series = types.map(type => ({
    name: type, type: 'bar', stack: 'total',
    barMaxWidth: 22, barMinWidth: 12,
    itemStyle: { color: getTypeColor(type), borderRadius: 0 },
    label: { show: false },
    data: reversed.map(d => {
      const item = d.breakdown?.find(b => b.type === type)
      return item ? item.days : 0
    })
  }))

  rankingChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: '#fff', borderColor: '#E4E4E7', borderWidth: 1,
      textStyle: { color: '#18181B', fontSize: 12 },
      formatter: (params) => {
        let result = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        let total = 0
        params.forEach(p => {
          if (p.value > 0) {
            result += `<div style="display:flex;align-items:center;gap:6px;margin:2px 0">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
              ${p.seriesName}: ${p.value}天
            </div>`
          }
          total += p.value
        })
        result += `<div style="margin-top:4px;font-weight:600">合计: ${Math.round(total * 10) / 10}天</div>`
        return result
      }
    },
    legend: {
      data: types, bottom: 0, left: 'center', type: 'scroll',
      textStyle: { fontSize: 12, color: '#71717A' },
      itemWidth: 12, itemHeight: 12, itemGap: 16
    },
    grid: { top: 12, left: 12, right: 50, bottom: 36, containLabel: true },
    xAxis: {
      type: 'value',
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#F4F4F5', type: 'dashed' } },
      axisLabel: { color: '#A1A1AA', fontSize: 11 }
    },
    yAxis: {
      type: 'category', data: names,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        color: '#71717A', fontSize: 12,
        formatter: (value) => `{avatar|} ${value}`,
        rich: { avatar: { width: 20, height: 20, borderRadius: 10, backgroundColor: '#E4E4E7' } }
      }
    },
    series
  }, true)
}

// --- Render all ---
function renderAllCharts() {
  renderTrendChart()
  renderPieChart()
  renderDeptChart()
  renderWeekdayChart()
  renderRankingChart()
}

function handleResize() {
  trendChart?.resize()
  pieChart?.resize()
  deptChart?.resize()
  weekdayChart?.resize()
  rankingChart?.resize()
}

async function handleDeptMetricChange(metric) {
  deptMetric.value = metric
  try {
    departmentComparison.value = await apiClient.getTripDepartmentComparison(props.year, metric)
  } catch (err) {
    console.error('[TripAnalytics] Failed to refresh department comparison:', err)
  }
}

// --- Watchers ---
watch(monthlyTrend, () => nextTick(renderTrendChart))
watch(typeDistribution, () => nextTick(renderPieChart))
watch(departmentComparison, () => nextTick(renderDeptChart))
watch(weekdayDistribution, () => nextTick(renderWeekdayChart))
watch(employeeRanking, () => nextTick(renderRankingChart))

// --- Lifecycle ---
onMounted(() => {
  fetchAll(props.year)
  nextTick(renderAllCharts)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  pieChart?.dispose()
  deptChart?.dispose()
  weekdayChart?.dispose()
  rankingChart?.dispose()
  trendChart = null
  pieChart = null
  deptChart = null
  weekdayChart = null
  rankingChart = null
})
</script>

<template>
  <div class="space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="flex items-center gap-3 text-text-secondary">
        <svg class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span class="text-sm">加载中...</span>
      </div>
    </div>

    <template v-else>
      <!-- Row 1: Monthly trend + Type distribution -->
      <div class="flex flex-col lg:flex-row gap-4">
        <div class="flex-1 bg-white rounded-xl border border-border-default p-6">
          <h2 class="text-sm font-semibold text-text-primary mb-4">月度出差趋势</h2>
          <div ref="trendChartRef" class="w-full" style="height: 280px"></div>
        </div>
        <div class="w-full lg:w-[380px] bg-white rounded-xl border border-border-default p-6">
          <h2 class="text-sm font-semibold text-text-primary mb-4">出差/外出占比</h2>
          <div class="flex flex-col items-center">
            <div ref="pieChartRef" class="w-full" style="height: 180px"></div>
            <div class="w-full mt-4 space-y-2">
              <div
                v-for="item in (typeDistribution?.items || [])"
                :key="item.type"
                class="flex items-center justify-between text-sm"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="inline-block w-2.5 h-2.5 rounded-full"
                    :style="{ backgroundColor: getTypeColor(item.type) }"
                  />
                  <span class="text-text-secondary">{{ item.type }}</span>
                </div>
                <div class="flex items-center gap-3">
                  <span class="font-medium text-text-primary">{{ item.days }}天</span>
                  <span class="text-text-tertiary text-xs w-10 text-right">{{ item.ratio }}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Row 2: Department comparison + Weekday distribution -->
      <div class="flex flex-col lg:flex-row gap-4">
        <div class="flex-1 bg-white rounded-xl border border-border-default p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-text-primary">部门出差对比</h2>
            <div class="flex items-center gap-1 bg-surface rounded-md p-0.5">
              <button
                class="px-2.5 py-1 text-xs font-medium rounded transition-colors"
                :class="deptMetric === 'total'
                  ? 'bg-white text-text-primary shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'"
                @click="handleDeptMetricChange('total')"
              >总天数</button>
              <button
                class="px-2.5 py-1 text-xs font-medium rounded transition-colors"
                :class="deptMetric === 'avg'
                  ? 'bg-white text-text-primary shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'"
                @click="handleDeptMetricChange('avg')"
              >人均</button>
            </div>
          </div>
          <div ref="deptChartRef" class="w-full" style="min-height: 250px"></div>
        </div>
        <div class="w-full lg:w-[380px] bg-white rounded-xl border border-border-default p-6">
          <h2 class="text-sm font-semibold text-text-primary mb-4">出差星期分布</h2>
          <div ref="weekdayChartRef" class="w-full" style="height: 250px"></div>
        </div>
      </div>

      <!-- Row 3: Employee ranking -->
      <div class="bg-white rounded-xl border border-border-default p-6">
        <h2 class="text-sm font-semibold text-text-primary mb-4">出差排行 Top 10</h2>
        <div ref="rankingChartRef" class="w-full" style="height: 380px"></div>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TripAnalyticsSection.vue
git commit -m "feat(analytics): add TripAnalyticsSection component with 5 charts"
```

---

### Task 7: Integrate into AnalyticsView

**Files:**
- Modify: `frontend/src/components/AnalyticsView.vue`

- [ ] **Step 1: Add import**

In the `<script setup>` section, after the existing imports (around line 4), add:

```javascript
import TripAnalyticsSection from './TripAnalyticsSection.vue'
```

- [ ] **Step 2: Add TripAnalyticsSection to template**

After the employee ranking chart section (the `</div>` closing the `bg-white rounded-xl` div around line 703), before `</template>` (the v-else template closing), add:

```html
      <!-- Trip Analytics Section -->
      <div class="border-t border-border-default pt-6 mt-2">
        <div class="mb-6">
          <h1 class="text-2xl font-semibold text-text-primary">出差分析</h1>
          <p class="text-sm text-text-secondary mt-1">可视化展示员工出差与外出数据统计</p>
        </div>
        <TripAnalyticsSection :year="year" />
      </div>
```

- [ ] **Step 3: Verify build**

Run: `cd E:/Project/DingtalkFriday/frontend && npx vue-tsc --noEmit 2>/dev/null; echo "done"`
Or simply: `cd E:/Project/DingtalkFriday/frontend && npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AnalyticsView.vue
git commit -m "feat(analytics): integrate trip analytics section into analytics page"
```

---

### Task 8: Manual Smoke Test

- [ ] **Step 1: Start backend**

Run: `cd E:/Project/DingtalkFriday/backend && python -m uvicorn app.main:app --reload --port 8000`

- [ ] **Step 2: Start frontend**

Run: `cd E:/Project/DingtalkFriday/frontend && npm run dev`

- [ ] **Step 3: Verify in browser**

1. Open http://localhost:5173, log in
2. Navigate to "数据分析" page
3. Scroll down past leave analytics section
4. Verify 5 trip charts render below (may show zeros if no trip data for selected year)
5. Switch year — verify both leave and trip sections update
6. Test department comparison metric toggle (总天数/人均)

- [ ] **Step 4: Final commit if any fixes needed**
