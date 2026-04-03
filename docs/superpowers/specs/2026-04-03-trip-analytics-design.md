# Trip Analytics Integration Design

**Date:** 2026-04-03
**Scope:** Add trip/outing analytics section below existing leave analytics on the data analysis page (Option B - same page, not tab-based).

## Overview

The current analytics page (`AnalyticsView.vue`) only analyzes leave data across 5 charts. Trip data exists in `trip_record` with fields `tag_name` (出差/外出), `work_date`, `duration_hours`, but has no analytics visualization. This design adds a mirrored set of 5 charts for trip/outing data below the leave section.

## Backend

### New Files

- `backend/app/services/trip_analytics.py` — analytics aggregation queries against `trip_record`
- `backend/app/routers/trip_analytics.py` — 5 API endpoints under `/api/analytics/trip`

### API Endpoints

| Endpoint | Response | Description |
|----------|----------|-------------|
| `GET /api/analytics/trip/monthly-trend?year=` | `TripMonthlyTrendResponse` | Monthly days by type (trip line + outing line) |
| `GET /api/analytics/trip/type-distribution?year=` | `LeaveTypeDistributionResponse` (reused) | Trip vs outing days ratio (donut chart) |
| `GET /api/analytics/trip/department-comparison?year=&metric=` | `DepartmentComparisonResponse` (reused) | Per-department total/avg days |
| `GET /api/analytics/trip/weekday-distribution?year=` | `WeekdayDistributionResponse` (reused) | Trip occurrences by weekday (Mon-Fri) |
| `GET /api/analytics/trip/employee-ranking?year=&limit=` | `EmployeeRankingResponse` (reused) | Top N employees with trip+outing breakdown |

### New Schema

```python
class TripTrendLine(BaseModel):
    month: int
    days: float

class TripMonthlyTrendResponse(BaseModel):
    trip: List[TripTrendLine]      # 出差 monthly days
    outing: List[TripTrendLine]    # 外出 monthly days
```

Other endpoints reuse existing analytics schemas (`LeaveTypeDistributionResponse`, `DepartmentComparisonResponse`, `WeekdayDistributionResponse`, `EmployeeRankingResponse`) since the data shapes are identical.

### Query Logic

All queries operate on the `trip_record` table:
- **Filter:** `work_date` within the target year (`YYYY-01-01` to `YYYY-12-31`)
- **Duration conversion:** `duration_hours / 8.0` → days (8 hours = 1 full day)
- **Type split:** `tag_name` is either `'出差'` or `'外出'`
- **Employee/dept join:** Join `employee` table on `userid` for name and `dept_name`
- No cross-year proration needed (unlike leave records, trip records are stored per `work_date`)

### Router Registration

Add to `main.py`:
```python
from app.routers import trip_analytics
app.include_router(trip_analytics.router)
```

## Frontend

### New Files

- `frontend/src/composables/useTripAnalyticsData.js` — state management + 5 concurrent API fetches
- `frontend/src/components/TripAnalyticsSection.vue` — self-contained component with 5 ECharts charts

### API Client Additions (`api/index.js`)

```javascript
getTripMonthlyTrend(year)
getTripTypeDistribution(year)
getTripDepartmentComparison(year, metric = 'total')
getTripWeekdayDistribution(year)
getTripEmployeeRanking(year, limit = 10)
```

### TripAnalyticsSection.vue

**Props:** `year: Number` (synced with page-level year switcher)

**Charts (5 total, same layout grid as leave section):**

1. **月度出差趋势** (line chart, Row 1 left)
   - Two smooth lines: 出差 (blue `#2563EB`, solid) and 外出 (green `#059669`, solid)
   - Area fill under 出差 line
   - Tooltip shows both values per month

2. **出差/外出占比** (donut chart, Row 1 right, 380px wide)
   - Two segments: 出差 blue, 外出 green
   - Center label: total days
   - Custom legend below with days + percentage

3. **部门出差对比** (horizontal bar, Row 2 left)
   - Toggle: 总天数 / 人均
   - Mean line marker
   - Dynamic height based on department count

4. **出差星期分布** (vertical bar, Row 2 right, 380px wide)
   - Monday and Friday highlighted (same pattern as leave)

5. **出差排行 Top 10** (stacked horizontal bar, Row 3 full width)
   - Two-color stack: 出差 blue + 外出 green
   - Tooltip shows per-type days + total

**Watch:** Re-fetch and re-render when `year` prop changes.

### Integration in AnalyticsView.vue

After the employee ranking chart section, add:

```html
<div class="border-t border-border-default pt-6 mt-2">
  <div class="mb-6">
    <h1 class="text-2xl font-semibold text-text-primary">出差分析</h1>
    <p class="text-sm text-text-secondary mt-1">可视化展示员工出差与外出数据统计</p>
  </div>
  <TripAnalyticsSection :year="year" />
</div>
```

No other changes to `AnalyticsView.vue` — chart logic, resize handling, and lifecycle are self-contained in `TripAnalyticsSection`.

## Implementation Notes

- **Auth:** All 5 new endpoints use `Depends(get_current_user)`, consistent with existing analytics endpoints.
- **Loading state:** `TripAnalyticsSection` manages its own loading indicator independently from the leave section.
- **Weekday distribution:** Only count Mon-Fri (weekday 0-4), skip any weekend dates that may exist in `trip_record`. Consistent with leave analytics behavior.
- **No year-over-year comparison** for monthly trend — intentional. Trip data may not have prior-year history, and the two-line (出差 vs 外出) split is more useful than same-type YoY comparison.

## File Summary

| Action | File |
|--------|------|
| Create | `backend/app/services/trip_analytics.py` |
| Create | `backend/app/routers/trip_analytics.py` |
| Create | `frontend/src/composables/useTripAnalyticsData.js` |
| Create | `frontend/src/components/TripAnalyticsSection.vue` |
| Modify | `backend/app/schemas.py` (add `TripTrendLine`, `TripMonthlyTrendResponse`) |
| Modify | `backend/app/main.py` (register `trip_analytics.router`) |
| Modify | `frontend/src/api/index.js` (add 5 API methods) |
| Modify | `frontend/src/components/AnalyticsView.vue` (import + embed `TripAnalyticsSection`) |
