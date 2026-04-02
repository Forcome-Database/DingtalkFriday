# 外出/出差功能集成设计

## 概述

在现有 DingtalkFriday 请假数据导出系统中，新增外出和出差数据的同步、统计、导出功能。作为独立 Tab 页与现有"数据导出"并列，复用现有 UI 风格和组件模式。

## 数据来源

通过钉钉 `POST /topapi/attendance/getupdatedata` 接口获取考勤数据。该接口返回 `approve_list` 字段，其中 `biz_type=2` 对应出差/外出记录，`tag_name` 区分"出差"与"外出"。

接口特性：
- 每次查询 1 个用户 × 1 天
- 复用现有 access_token 认证，无需额外权限
- 返回字段：`proc_inst_id`、`tag_name`、`sub_type`、`begin_time`、`end_time`、`duration`、`duration_unit`、`biz_type`、`gmt_finished`

## 数据模型

### 新增表 `trip_record`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 主键 |
| userid | TEXT NOT NULL | 员工ID |
| work_date | TEXT NOT NULL | 工作日期 YYYY-MM-DD |
| tag_name | TEXT NOT NULL | "出差" 或 "外出" |
| sub_type | TEXT | 子类型名称 |
| begin_time | TEXT NOT NULL | 该审批单的整体开始时间 |
| end_time | TEXT NOT NULL | 该审批单的整体结束时间 |
| duration_hours | REAL NOT NULL DEFAULT 0 | 该 work_date 当天占用时长（小时），每天固定为企业工时（默认8h），半天按4h |
| proc_inst_id | TEXT NOT NULL | 审批实例ID（来自API，用于去重和聚合） |
| last_synced_at | DATETIME NOT NULL | 最后同步时间 |
| created_at | DATETIME | 创建时间 |

唯一约束：`UNIQUE(userid, work_date, proc_inst_id)`

**设计决策 — 多天出差的数据建模**：

一个出差审批（如 4/1~4/5）会在 `getupdatedata` 中每天返回一条记录，因此 `trip_record` 天然按 `work_date` 拆分存储。每行的 `duration_hours` 表示**该天**的占用时长（整天=8h，半天=4h），而 `begin_time`/`end_time` 保留审批单的整体时间范围供参考。

聚合规则：
- **总天数**：`SUM(duration_hours) / 8`（按工时折算）
- **总人次**：`COUNT(DISTINCT proc_inst_id)` per userid（同一审批单不论跨几天只算 1 次）
- **月度明细**：按 `work_date` 的月份分组 SUM

### 新增表 `trip_sync_cursor`

| 字段 | 类型 | 说明 |
|------|------|------|
| userid | TEXT NOT NULL | 员工ID |
| work_date | TEXT NOT NULL | 日期 YYYY-MM-DD |
| last_synced_at | DATETIME NOT NULL | 最后同步时间 |

主键：`PK(userid, work_date)`

用途：记录每个 (userid, work_date) 是否已同步，包括"已查询但无数据"的情况，避免反复拉取空数据。

清理策略：每次 trip 定时同步任务执行时，删除 1 年前的 cursor 记录。手动同步（force_month）时，先删除目标月的 cursor 记录再重新拉取。

### 索引

- `trip_record` 额外添加 `INDEX(work_date, tag_name)` — 加速今日查询和按日期筛选

## 同步策略：分区缓存

### 日期分区

| 分区 | 范围 | 同步频率 | cursor 行为 |
|------|------|----------|-------------|
| 热区 | 过去 3 天 ~ 未来 7 天 | 每天 | **忽略 cursor，始终重新拉取** |
| 温区 | 未来 8 ~ 90 天 | 每周一次 | 检查 cursor，7 天内已同步则跳过 |
| 冷区 | 3 天前更早 | 不自动同步 | 始终跳过（除非手动触发） |

### 同步流程

```
sync_trip_records(force_month=None):
  1. 确定日期范围：
     - 日常: 热区(始终) + 温区(仅周一)
     - 手动: force_month 指定月份，先清除该月 cursor，全量拉取
  2. 获取所有员工 userid
  3. 对每个 (userid, date):
     a. 热区 → 直接拉取（不检查 cursor）
     b. 温区 → 查 cursor，7天内已同步则跳过
     c. 调用 get_update_data(userid, date)
     d. 从 approve_list 筛选 biz_type=2
     e. 对每条记录：设置 duration_hours（整天=8h，半天=4h，API 按 work_date 返回每天一条）
     f. UPSERT 到 trip_record（DELETE 该 userid+work_date 旧数据后 INSERT）
     g. UPSERT trip_sync_cursor
  4. 并发控制 + 限流（见下文）
```

### 限流与重试策略

钉钉 API 限流约 20 次/秒。策略：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 并发信号量 | 10 | `asyncio.Semaphore(10)`，保守低于限流阈值 |
| 请求间隔 | 50ms | 每个协程在请求后 sleep 50ms |
| 重试次数 | 3 | 遇到限流(errcode)或网络错误时重试 |
| 退避策略 | 指数退避 | 1s → 2s → 4s |
| 失败阈值 | 连续 50 次失败 | 触发后中止本次同步，记录 sync_log |
| 单次失败 | 跳过并记录 | 不更新 cursor，下次自动重试 |

**预估同步耗时**（100 人）：

| 场景 | API 调用量 | 耗时 |
|------|-----------|------|
| 日常热区（10天） | 1,000 | ~2 分钟 |
| 周一 + 温区（93天） | 9,300 | ~16 分钟 |
| 手动同步 1 个月 | 3,000 | ~5 分钟 |

### 定时任务

- 每日凌晨 2:30 执行 `sync_trip_records()`
- 复用现有 APScheduler 配置
- **独立于 `full_sync()`**，作为单独的定时任务运行（避免拖长 full_sync 时间）
- `full_sync()` 不包含 trip 同步，但手动"同步"按钮可同时触发两者

### Sync Log

使用 `sync_type="trip_record"` 记录到现有 `sync_log` 表。

## 后端 API

### 钉钉 API Wrapper

`app/dingtalk/attendance.py` 新增：

```python
async def get_update_data(userid: str, work_date: str) -> Dict[str, Any]:
    """POST /topapi/attendance/getupdatedata
    Returns: { approve_list: [...], check_record_list: [...], ... }
    """
```

### 同步服务

新建 `app/services/trip_sync.py`，包含 `sync_trip_records()` 函数。

### 查询服务

新建 `app/services/trip.py`，包含月度汇总、每日明细、今日统计等查询逻辑。

### API 路由与响应 Schema

新建 `app/routers/trip.py`：

#### `GET /api/trip/monthly-summary`

查询参数：`year, deptId, tripType (出差|外出|空=全部), employeeName, page, pageSize, sortBy, sortOrder`

```python
class TripMonthlySummaryResponse:
    stats: TripStats
    list: List[TripEmployeeRow]   # 每行一个员工
    summary: TripSummaryRow       # 合计行
    pagination: Pagination

class TripEmployeeRow:
    employeeId: str
    employeeName: str
    deptName: str
    tripDays: float       # 出差总天数
    outingDays: float     # 外出总天数
    totalDays: float      # 合计
    tripCount: int        # 出差次数（按 proc_inst_id 去重）
    outingCount: int      # 外出次数
    months: Dict[str, float]  # {"1": 2.5, "2": 0, ...} 每月天数
```

#### `GET /api/trip/daily-detail`

查询参数：`employeeId, year, month`

```python
class TripDailyDetailResponse:
    employeeName: str
    records: List[TripDayRecord]

class TripDayRecord:
    date: str             # "2026-04-01"
    tagName: str          # "出差" 或 "外出"
    durationHours: float  # 当天时长
    beginTime: str        # 审批单整体开始时间
    endTime: str          # 审批单整体结束时间
```

#### `GET /api/trip/today`

```python
class TripTodayResponse:
    list: List[TripTodayItem]

class TripTodayItem:
    employeeId: str
    employeeName: str
    deptName: str
    tagName: str          # "出差" 或 "外出"
    beginTime: str
    endTime: str
    durationHours: float
```

#### `GET /api/trip/stats`

```python
class TripStatsResponse:
    totalCount: int       # 总人次（proc_inst_id 去重）
    totalDays: float      # 总天数
    todayTripCount: int   # 今日出差人数
    todayOutingCount: int # 今日外出人数
```

#### `POST /api/trip/export`

请求体：`{ year, deptId?, tripType?, employeeName? }`
响应：Excel 文件流

#### `POST /api/trip/sync`

请求体：`{ month?: "2026-04" }`（可选，指定月份强制同步）
响应：`MessageResponse { message: str }`
权限：admin

### 导出服务

`app/services/export.py` 新增 `export_trip_excel()` 函数，复用现有 openpyxl 导出逻辑。

## 前端设计

### 导航变化

顶部导航新增 Tab：`数据导出 | 外出/出差 | 数据分析 | 管理`

移动端底部 Tab 栏同步更新。由于增加到 4 个 Tab（管理员 5 个），使用更紧凑的图标+文字布局，保持可用性。

### 页面结构

"外出/出差"页面复用"数据导出"的布局模式：

1. **筛选面板 TripFilterPanel** — 复用部门二级联动逻辑，类型筛选使用分段控制器（全部/出差/外出），不用多选标签（因为只有 2 种类型）
2. **统计卡片 TripStatsCards** (4 张，`grid-cols-2 sm:grid-cols-4`) — 总人次、总天数、今日出差(可点击)、今日外出(可点击)
3. **Tab 切换** — "出差/外出列表" | "每日统计"
4. **数据表 TripDataTable** — 月度汇总，列：姓名、部门、出差天数、外出天数、各月明细、合计
5. **每日统计 TripDailyStats** — 热力图 + 当日详情列表
6. **弹窗 TripTodayModal** — 今日出差/外出详情

### 现有页面增强

"数据导出"的 StatsCards 从 5 张 → 6 张，grid 改为 `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6`。末尾新增"今日外出/出差"卡片，点击切换 `activePage` 到 `'trip'`。

### 组件复用策略

| 新组件 | 复用来源 | 复用方式 |
|--------|----------|----------|
| TripFilterPanel | FilterPanel | 复用部门联动逻辑，类型改为分段控制器 |
| TripStatsCards | StatsCards | 参考样式，4 张卡片 |
| TripDataTable | DataTable | 参考表格结构，调整列定义 |
| TripDailyStats | DailyLeaveStats | 参考热力图+详情布局 |
| TripTodayModal | TodayLeaveModal | 参考弹窗结构 |
| useTripData.js | useLeaveData.js | 参考状态管理和 API 调用模式 |

所有新组件使用相同的 TailwindCSS 类名和设计 token，确保视觉风格统一。

## 配置变更

`app/config.py` 新增：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TRIP_SYNC_ENABLED` | true | 是否启用外出/出差同步 |
| `TRIP_SYNC_CRON` | "30 2 * * *" | 定时同步 cron 表达式 |
| `TRIP_HOT_DAYS_PAST` | 3 | 热区回溯天数 |
| `TRIP_HOT_DAYS_FUTURE` | 7 | 热区前瞻天数 |
| `TRIP_WARM_DAYS_FUTURE` | 90 | 温区前瞻天数 |
| `TRIP_SYNC_CONCURRENCY` | 10 | API 并发数（保守低于钉钉 20次/秒限流） |
| `TRIP_SYNC_RETRY_COUNT` | 3 | API 失败重试次数 |
| `TRIP_SYNC_FAIL_THRESHOLD` | 50 | 连续失败中止阈值 |

## 不做的事

- 不查询出差/外出的目的地、事由（不需要）
- 不修改现有请假模块的任何逻辑
- 不新增 OA 审批权限
- 不处理加班数据（biz_type=1）
- trip 同步不纳入 full_sync（独立定时任务）
