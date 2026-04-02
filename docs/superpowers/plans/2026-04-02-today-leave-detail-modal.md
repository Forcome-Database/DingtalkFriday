# 今日请假详情弹窗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点击"今日请假"卡片弹出右侧滑出面板，展示每人请假具体时间段（头像、姓名、部门、假期类型、时间段、时长、审批状态）

**Architecture:** 新增后端 API 端点 `GET /api/leave/today-detail`，返回今日请假人员详情列表。新建前端 `TodayLeaveModal.vue` 右侧滑出面板组件，复用 LeaveCalendarModal 的面板骨架和动画。通过 StatsCards emit 事件触发，MainView 管理弹窗状态。

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic, Vue 3 (Composition API), TailwindCSS, lucide-vue-next

---

### Task 1: 后端 Schema 定义

**Files:**
- Modify: `backend/app/schemas.py` (在文件末尾 `MessageResponse` 之前添加)

- [ ] **Step 1: 添加 TodayLeaveRecord 和 TodayLeaveDetailResponse schema**

在 `backend/app/schemas.py` 的 `# Generic response wrapper` 注释之前添加：

```python
# ---------------------------------------------------------------------------
# Today leave detail schemas
# ---------------------------------------------------------------------------

class TodayLeaveRecord(BaseModel):
    """Single leave record for today's leave detail."""
    userid: str
    name: str
    avatar: Optional[str] = None
    deptName: str
    leaveType: str
    leaveCode: Optional[str] = None
    startTime: int = Field(description="Start time (Unix ms)")
    endTime: int = Field(description="End time (Unix ms)")
    durationPercent: int
    durationUnit: str
    durationDisplay: str = Field(description="e.g. '5小时' or '1天'")
    timeDisplay: str = Field(description="e.g. '09:00 - 14:00'")
    status: str


class TodayLeaveDetailResponse(BaseModel):
    """Response for GET /api/leave/today-detail."""
    count: int = Field(description="Distinct person count on leave today")
    records: List[TodayLeaveRecord]
```

- [ ] **Step 2: 验证 schema 无语法错误**

Run: `cd E:/Project/DingtalkFriday/backend && python -c "from app.schemas import TodayLeaveDetailResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: add TodayLeaveDetailResponse schema"
```

---

### Task 2: 后端 Service 函数

**Files:**
- Modify: `backend/app/services/leave.py` (在文件末尾添加新函数)

- [ ] **Step 1: 添加 `get_today_leave_detail()` 函数**

在 `backend/app/services/leave.py` 文件末尾添加：

```python
# ---------------------------------------------------------------------------
# Today leave detail
# ---------------------------------------------------------------------------

async def get_today_leave_detail(
    dept_id: Optional[int] = None,
    leave_types: Optional[List[str]] = None,
    employee_name: Optional[str] = None,
) -> dict:
    """
    Get detailed leave records for today.

    Returns a dict matching TodayLeaveDetailResponse schema:
    {
        count: int (distinct person count),
        records: [{ userid, name, avatar, deptName, leaveType, ... }]
    }
    """
    today = date_type.today()
    today_start_ms = int(datetime(today.year, today.month, today.day, 0, 0, 0).timestamp() * 1000)
    today_end_ms = int(datetime(today.year, today.month, today.day, 23, 59, 59).timestamp() * 1000)

    async with async_session() as session:
        # ---- Employee filter (same logic as get_daily_leave_count) ----
        emp_conditions = []
        if dept_id is not None:
            all_dept_ids = await _get_descendant_dept_ids(session, dept_id)
            emp_conditions.append(Employee.dept_id.in_(all_dept_ids))
        if employee_name:
            emp_conditions.append(Employee.name.contains(employee_name))

        emp_query = select(Employee)
        if emp_conditions:
            emp_query = emp_query.where(and_(*emp_conditions))

        emp_result = await session.execute(emp_query)
        employees = emp_result.scalars().all()
        emp_map = {e.userid: e for e in employees}
        emp_userids = set(emp_map.keys())

        if not emp_userids:
            return {"count": 0, "records": []}

        # ---- Overlap query: records that intersect with today ----
        lr_conditions = [
            LeaveRecord.end_time >= today_start_ms,
            LeaveRecord.start_time <= today_end_ms,
            LeaveRecord.userid.in_(emp_userids),
        ]
        if leave_types:
            lr_conditions.append(LeaveRecord.leave_type.in_(leave_types))

        lr_query = select(LeaveRecord).where(and_(*lr_conditions)).order_by(LeaveRecord.start_time)
        lr_result = await session.execute(lr_query)
        records = lr_result.scalars().all()

    # ---- Build response records ----
    type_map = await _get_leave_type_map()
    result_records = []
    person_ids = set()

    for rec in records:
        uid = rec.userid
        if uid not in emp_userids:
            continue

        emp = emp_map.get(uid)
        if not emp:
            continue

        # Check if this day should count (workday check for non-calendar-day leave)
        calendar_day_leave = _is_calendar_day_leave(rec.leave_type)
        if not calendar_day_leave and not _is_workday(today):
            continue

        person_ids.add(uid)

        start_dt = _ms_to_datetime(rec.start_time)
        end_dt = _ms_to_datetime(rec.end_time)

        # Build timeDisplay
        rec_start_date = start_dt.date()
        rec_end_date = end_dt.date()

        if rec_start_date == rec_end_date:
            # Same day record
            time_display = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
        elif rec_start_date == today:
            # Today is the start day
            time_display = f"{start_dt.strftime('%H:%M')} - 18:00"
        elif rec_end_date == today:
            # Today is the end day
            time_display = f"09:00 - {end_dt.strftime('%H:%M')}"
        else:
            # Today is a middle day of a multi-day leave
            time_display = "09:00 - 18:00"

        # Build durationDisplay
        hpd = 800
        if rec.leave_code and rec.leave_code in type_map:
            hpd = type_map[rec.leave_code].hours_in_per_day or 800

        if rec.duration_unit == "percent_hour":
            hours = rec.duration_percent / 100.0
            if hours == int(hours):
                duration_display = f"{int(hours)}小时"
            else:
                duration_display = f"{hours}小时"
        else:
            days = rec.duration_percent / 100.0
            if days == int(days):
                duration_display = f"{int(days)}天"
            else:
                duration_display = f"{days}天"

        result_records.append({
            "userid": uid,
            "name": emp.name,
            "avatar": emp.avatar,
            "deptName": emp.dept_name or "",
            "leaveType": rec.leave_type or "请假",
            "leaveCode": rec.leave_code,
            "startTime": rec.start_time,
            "endTime": rec.end_time,
            "durationPercent": rec.duration_percent,
            "durationUnit": rec.duration_unit,
            "durationDisplay": duration_display,
            "timeDisplay": time_display,
            "status": rec.status or "已审批",
        })

    # Sort by name for consistent display
    result_records.sort(key=lambda r: r["name"])

    return {
        "count": len(person_ids),
        "records": result_records,
    }
```

- [ ] **Step 2: 验证 service 可导入**

Run: `cd E:/Project/DingtalkFriday/backend && python -c "from app.services.leave import get_today_leave_detail; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/leave.py
git commit -m "feat: add get_today_leave_detail service function"
```

---

### Task 3: 后端 Router 端点

**Files:**
- Modify: `backend/app/routers/leave.py`

- [ ] **Step 1: 添加 import 和端点**

在 `backend/app/routers/leave.py` 中：

1) 更新 schemas import（第19-24行），添加 `TodayLeaveDetailResponse`：

```python
from app.schemas import (
    DailyDetailResponse,
    DailyLeaveCountResponse,
    LeaveTypeOut,
    MonthlySummaryResponse,
    TodayLeaveDetailResponse,
)
```

2) 更新 services import（第25行），添加 `get_today_leave_detail`：

```python
from app.services.leave import get_daily_detail, get_daily_leave_count, get_monthly_summary, get_today_leave_detail
```

3) 在 `leave_types` 端点之前（`daily_leave_count` 端点之后）添加新端点：

```python
@router.get("/today-detail", response_model=TodayLeaveDetailResponse)
async def today_detail(
    deptId: Optional[int] = Query(default=None, description="Department ID filter"),
    leaveTypes: Optional[str] = Query(
        default=None,
        description="Comma-separated leave type names",
    ),
    employeeName: Optional[str] = Query(
        default=None, description="Employee name keyword"
    ),
    _user=Depends(get_current_user),
):
    """
    Get detailed leave records for today with employee info.
    """
    leave_type_list: Optional[List[str]] = None
    if leaveTypes:
        leave_type_list = [t.strip() for t in leaveTypes.split(",") if t.strip()]

    result = await get_today_leave_detail(
        dept_id=deptId,
        leave_types=leave_type_list,
        employee_name=employeeName,
    )
    return result
```

- [ ] **Step 2: 验证后端启动无错误**

Run: `cd E:/Project/DingtalkFriday/backend && python -c "from app.routers.leave import router; print('Routes:', [r.path for r in router.routes])"`
Expected: 输出包含 `/today-detail`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/leave.py
git commit -m "feat: add GET /api/leave/today-detail endpoint"
```

---

### Task 4: 前端 API 方法

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: 添加 `getTodayLeaveDetail` 方法**

在 `frontend/src/api/index.js` 的 `getDailyLeaveCount` 方法之后（约第159行后）添加：

```javascript
  /**
   * Get today's leave detail (list of employees on leave with time info)
   */
  getTodayLeaveDetail(params) {
    return api.get('/leave/today-detail', {
      params: {
        deptId: params.deptId || undefined,
        leaveTypes: params.leaveTypes?.length ? params.leaveTypes.join(',') : undefined,
        employeeName: params.employeeName || undefined
      }
    })
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat: add getTodayLeaveDetail API method"
```

---

### Task 5: 前端 Composable 扩展

**Files:**
- Modify: `frontend/src/composables/useLeaveData.js`

- [ ] **Step 1: 添加 today detail 状态变量**

在 `useLeaveData.js` 的 `todayLeaveCount` 状态声明附近（约第248行后）添加：

```javascript
  // --- Today leave detail modal state ---
  const todayLeaveVisible = ref(false)
  const todayLeaveDetail = ref(null)
  const todayLeaveLoading = ref(false)
```

- [ ] **Step 2: 添加 `fetchTodayLeaveDetail` 和 `closeTodayLeave` 方法**

在 `fetchTodayLeaveCount` 函数之后添加：

```javascript
  /**
   * Fetch today's leave detail for the modal
   */
  async function fetchTodayLeaveDetail() {
    if (todayLeaveLoading.value) return
    todayLeaveLoading.value = true
    todayLeaveVisible.value = true

    try {
      const effectiveDeptId = filters.deptId2 || filters.deptId
      const params = {
        deptId: effectiveDeptId,
        leaveTypes: filters.leaveTypes,
        employeeName: filters.employeeName
      }

      if (USE_MOCK) {
        await new Promise(resolve => setTimeout(resolve, 300))
        todayLeaveDetail.value = {
          count: 3,
          records: [
            { userid: 'U001', name: '张三', avatar: '', deptName: '研发部', leaveType: '年假', leaveCode: 'annual', startTime: 0, endTime: 0, durationPercent: 800, durationUnit: 'percent_hour', durationDisplay: '8小时', timeDisplay: '09:00 - 18:00', status: '已审批' },
            { userid: 'U002', name: '李四', avatar: '', deptName: '产品部', leaveType: '事假', leaveCode: 'personal', startTime: 0, endTime: 0, durationPercent: 400, durationUnit: 'percent_hour', durationDisplay: '4小时', timeDisplay: '14:00 - 18:00', status: '已审批' },
            { userid: 'U003', name: '王五', avatar: '', deptName: '设计部', leaveType: '病假', leaveCode: 'sick', startTime: 0, endTime: 0, durationPercent: 800, durationUnit: 'percent_hour', durationDisplay: '8小时', timeDisplay: '09:00 - 18:00', status: '审批中' }
          ]
        }
      } else {
        todayLeaveDetail.value = await api.getTodayLeaveDetail(params)
      }
    } catch (e) {
      console.error('Failed to fetch today leave detail:', e)
      todayLeaveDetail.value = null
    } finally {
      todayLeaveLoading.value = false
    }
  }

  /**
   * Close the today leave detail modal
   */
  function closeTodayLeave() {
    todayLeaveVisible.value = false
    todayLeaveDetail.value = null
  }
```

- [ ] **Step 3: 在 return 对象中导出新的状态和方法**

在 return 对象的 State 部分添加：
```javascript
    todayLeaveVisible,
    todayLeaveDetail,
    todayLeaveLoading,
```

在 return 对象的 Methods 部分添加：
```javascript
    fetchTodayLeaveDetail,
    closeTodayLeave,
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useLeaveData.js
git commit -m "feat: add today leave detail state and methods to useLeaveData"
```

---

### Task 6: 新建 TodayLeaveModal 组件

**Files:**
- Create: `frontend/src/components/TodayLeaveModal.vue`

- [ ] **Step 1: 创建完整组件**

创建 `frontend/src/components/TodayLeaveModal.vue`：

```vue
<script setup>
import { X, Clock, CheckCircle, AlertCircle, XCircle, UserMinus } from 'lucide-vue-next'

const props = defineProps({
  /** Whether the modal is visible */
  visible: {
    type: Boolean,
    default: false
  },
  /** Today leave detail data from API */
  data: {
    type: Object,
    default: null
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  },
  /** Leave type color options from useLeaveData */
  leaveTypeOptions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close'])

/** Status badge configuration (reuse from LeaveCalendarModal) */
const statusConfig = {
  '已审批': { icon: CheckCircle, class: 'text-green-600 bg-green-50' },
  '审批中': { icon: AlertCircle, class: 'text-yellow-600 bg-yellow-50' },
  '已驳回': { icon: XCircle, class: 'text-red-600 bg-red-50' }
}

/** Fallback color for unknown leave types */
const fallbackColor = { bgColor: 'bg-gray-100', textColor: 'text-gray-600' }

/**
 * Get the first character of a name for the avatar fallback
 */
function getInitial(name) {
  return name ? name.charAt(0) : '?'
}

/**
 * Get color config for a leave type using the dynamic color mapping
 */
function getTypeColor(typeName) {
  const opt = props.leaveTypeOptions.find(t => t.name === typeName)
  return opt || fallbackColor
}

/**
 * Get status badge config
 */
function getStatusConfig(status) {
  return statusConfig[status] || statusConfig['已审批']
}

/**
 * Close modal when clicking the overlay
 */
function onOverlayClick(event) {
  if (event.target === event.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <!-- Overlay -->
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 bg-black/40 z-50"
        @click="onOverlayClick"
      >
        <!-- Slide-in panel -->
        <Transition name="slide">
          <div
            v-if="visible"
            class="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] max-w-full bg-white shadow-2xl flex flex-col"
            @click.stop
          >
            <!-- Panel header -->
            <div class="flex items-center justify-between p-4 sm:p-6 pb-4 border-b border-border-default">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center flex-shrink-0">
                  <UserMinus :size="20" class="text-red-500" />
                </div>
                <div>
                  <div class="text-base font-semibold text-text-primary">
                    今日请假详情
                  </div>
                  <div class="text-[13px] text-text-secondary mt-0.5">
                    共 <span class="font-medium text-text-primary">{{ data?.count ?? 0 }}</span> 人请假
                  </div>
                </div>
              </div>
              <!-- Close button -->
              <button
                class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                @click="emit('close')"
              >
                <X :size="20" />
              </button>
            </div>

            <!-- Panel body (scrollable) -->
            <div class="flex-1 overflow-y-auto p-4 sm:p-6">
              <!-- Loading state: skeleton cards -->
              <div v-if="loading" class="space-y-3">
                <div v-for="i in 3" :key="i" class="rounded-xl border-[1.5px] border-border-default p-4 animate-pulse">
                  <div class="flex items-center gap-3 mb-3">
                    <div class="w-8 h-8 rounded-full bg-gray-200" />
                    <div class="flex-1">
                      <div class="h-4 bg-gray-200 rounded w-24 mb-1.5" />
                      <div class="h-3 bg-gray-100 rounded w-32" />
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-5 bg-gray-100 rounded w-12" />
                    <div class="h-4 bg-gray-100 rounded w-28" />
                  </div>
                </div>
              </div>

              <!-- Data loaded -->
              <template v-else-if="data">
                <!-- Empty state -->
                <div
                  v-if="data.records && data.records.length === 0"
                  class="flex flex-col items-center justify-center py-16 text-text-tertiary"
                >
                  <UserMinus :size="48" class="mb-3 opacity-30" />
                  <span class="text-sm">今日无人请假</span>
                </div>

                <!-- Records list -->
                <div v-else class="space-y-3">
                  <div
                    v-for="(record, idx) in data.records"
                    :key="idx"
                    class="rounded-xl border-[1.5px] border-border-default p-3 sm:p-4"
                  >
                    <!-- Row 1: Avatar + Name + Status -->
                    <div class="flex items-start justify-between mb-2">
                      <div class="flex items-center gap-2.5">
                        <!-- Avatar -->
                        <img
                          v-if="record.avatar"
                          :src="record.avatar"
                          :alt="record.name"
                          class="w-8 h-8 rounded-full object-cover flex-shrink-0"
                        />
                        <div
                          v-else
                          class="w-8 h-8 rounded-full bg-accent text-white text-sm font-semibold flex items-center justify-center flex-shrink-0"
                        >
                          {{ getInitial(record.name) }}
                        </div>
                        <div>
                          <div class="text-sm font-medium text-text-primary">{{ record.name }}</div>
                          <div class="text-[12px] text-text-tertiary">{{ record.deptName }}</div>
                        </div>
                      </div>
                      <!-- Status badge -->
                      <div
                        class="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium flex-shrink-0"
                        :class="getStatusConfig(record.status).class"
                      >
                        <component :is="getStatusConfig(record.status).icon" :size="12" />
                        {{ record.status }}
                      </div>
                    </div>

                    <!-- Row 2: Leave type tag + Time + Duration -->
                    <div class="flex items-center gap-2 flex-wrap">
                      <!-- Leave type tag -->
                      <span
                        class="inline-flex items-center px-2 py-0.5 rounded text-[12px] font-medium"
                        :class="[getTypeColor(record.leaveType).bgColor, getTypeColor(record.leaveType).textColor]"
                      >
                        {{ record.leaveType }}
                      </span>
                      <!-- Time display -->
                      <div class="flex items-center gap-1 text-[13px] text-text-secondary">
                        <Clock :size="13" class="text-text-tertiary" />
                        <span>{{ record.timeDisplay }}</span>
                      </div>
                      <!-- Duration -->
                      <span class="text-[13px] text-text-tertiary">
                        {{ record.durationDisplay }}
                      </span>
                    </div>
                  </div>
                </div>
              </template>
            </div>

            <!-- Panel footer -->
            <div
              v-if="data && data.records && data.records.length > 0"
              class="border-t border-border-default px-4 sm:px-6 py-4 bg-surface"
            >
              <div class="flex items-center justify-between">
                <span class="text-[13px] font-medium text-text-secondary">今日请假</span>
                <span class="text-sm font-semibold text-text-primary">
                  共 {{ data.count }} 人 · {{ data.records.length }} 条记录
                </span>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TodayLeaveModal.vue
git commit -m "feat: add TodayLeaveModal component"
```

---

### Task 7: 修改 StatsCards 添加点击交互

**Files:**
- Modify: `frontend/src/components/StatsCards.vue`

- [ ] **Step 1: 添加 emit 声明和点击事件**

在 `StatsCards.vue` 中：

1) 在 `</script>` 之前添加 emit 声明：
```javascript
const emit = defineEmits(['todayLeaveClick'])
```

2) 替换 Card 5（今日请假卡片，约第97-112行）的容器 div，添加 `cursor-pointer`、hover 效果和 click 事件：

将：
```html
<div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
```
（Card 5 的那个）替换为：
```html
<div
  class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 cursor-pointer hover:border-accent hover:shadow-sm transition-all"
  @click="emit('todayLeaveClick')"
>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/StatsCards.vue
git commit -m "feat: add click interaction to today leave card"
```

---

### Task 8: 修改 MainView 集成弹窗

**Files:**
- Modify: `frontend/src/views/MainView.vue`

- [ ] **Step 1: 添加 import 和状态绑定**

在 `MainView.vue` 中：

1) 在 import 区域添加 TodayLeaveModal：
```javascript
import TodayLeaveModal from '../components/TodayLeaveModal.vue'
```

2) 在 `useLeaveData()` 解构中添加新的状态和方法（约第18-59行的解构块），在 State 部分添加：
```javascript
  todayLeaveVisible,
  todayLeaveDetail,
  todayLeaveLoading,
```
在 Methods 部分添加：
```javascript
  fetchTodayLeaveDetail,
  closeTodayLeave,
```

3) 在 StatsCards 组件上添加事件监听（约第158行）：
```html
<StatsCards
  :stats="stats"
  :unit="filters.unit"
  :today-leave-count="todayLeaveCount"
  @today-leave-click="fetchTodayLeaveDetail"
/>
```

4) 在 LeaveCalendarModal 之后（约第233行后）添加 TodayLeaveModal：
```html
<!-- Today leave detail modal -->
<TodayLeaveModal
  :visible="todayLeaveVisible"
  :data="todayLeaveDetail"
  :loading="todayLeaveLoading"
  :leave-type-options="leaveTypeOptions"
  @close="closeTodayLeave"
/>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/MainView.vue
git commit -m "feat: integrate TodayLeaveModal into MainView"
```

---

### Task 9: 端到端验证

- [ ] **Step 1: 启动后端服务**

确认后端服务运行正常，API 端点可访问：
Run: 访问 `http://localhost:8000/docs` 确认 `/api/leave/today-detail` 端点存在

- [ ] **Step 2: 前端验证**

在浏览器中 `http://localhost:5173/`：
1. 确认"今日请假"卡片有 hover 效果（鼠标悬停时蓝色边框 + 阴影）
2. 点击卡片，确认右侧滑出面板弹出
3. 确认面板显示：头像/首字符、姓名、部门、假期类型（颜色标签）、时间段、时长、审批状态
4. 确认点击遮罩或关闭按钮可关闭面板
5. 移动端：F12 切换到手机视图，确认面板全屏显示

- [ ] **Step 3: 最终 commit**

如果有修复，统一提交：
```bash
git add -A
git commit -m "feat: 今日请假详情弹窗完整实现"
```
