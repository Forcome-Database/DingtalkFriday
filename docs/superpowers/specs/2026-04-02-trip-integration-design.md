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
| biz_type | INTEGER NOT NULL | 2=出差/外出 |
| tag_name | TEXT NOT NULL | "出差" 或 "外出" |
| sub_type | TEXT | 子类型名称 |
| begin_time | TEXT NOT NULL | 审批开始时间 |
| end_time | TEXT NOT NULL | 审批结束时间 |
| duration | REAL | 时长（小时） |
| duration_unit | TEXT | 时长单位 |
| proc_inst_id | TEXT | 审批实例ID |
| last_synced_at | DATETIME NOT NULL | 最后同步时间 |
| created_at | DATETIME | 创建时间 |

唯一约束：`UNIQUE(userid, work_date, proc_inst_id)`

### 新增表 `trip_sync_cursor`

| 字段 | 类型 | 说明 |
|------|------|------|
| userid | TEXT NOT NULL | 员工ID |
| work_date | TEXT NOT NULL | 日期 YYYY-MM-DD |
| last_synced_at | DATETIME NOT NULL | 最后同步时间 |

主键：`PK(userid, work_date)`

用途：记录每个 (userid, work_date) 是否已同步，避免对"无数据"的日期反复调用 API。

## 同步策略：分区缓存

### 日期分区

| 分区 | 范围 | 同步频率 | 说明 |
|------|------|----------|------|
| 热区 | 过去 3 天 ~ 未来 7 天 | 每天 | 审批变动集中区 |
| 温区 | 未来 8 ~ 90 天 | 每周一次 | 提前报批的出差 |
| 冷区 | 3 天前更早 | 不自动同步 | 已定型数据 |

### 同步流程

```
sync_trip_records(force_month=None):
  1. 确定日期范围：
     - 日常: 热区 + 温区(周同步日)
     - 手动: force_month 指定月份全量
  2. 获取所有员工 userid
  3. 对每个 (userid, date):
     a. 查 trip_sync_cursor，冷区已同步则跳过
     b. 调用 get_update_data(userid, date)
     c. 从 approve_list 筛选 biz_type=2
     d. UPSERT 到 trip_record
     e. 更新 trip_sync_cursor
  4. 并发控制：asyncio.Semaphore(20)
```

### 定时任务

- 每日凌晨 2:30 执行 `sync_trip_records()`
- 复用现有 APScheduler 配置
- 集成到 `full_sync()` 末尾

### 手动同步

- `POST /api/trip/sync`（admin）可指定月份强制全量拉取，绕过缓存

## 后端 API

### 钉钉 API Wrapper

`app/dingtalk/attendance.py` 新增：

```python
async def get_update_data(userid: str, work_date: str) -> Dict[str, Any]:
    """POST /topapi/attendance/getupdatedata"""
```

### 同步服务

新建 `app/services/trip_sync.py`，包含 `sync_trip_records()` 函数。

### 查询服务

新建 `app/services/trip.py`，包含月度汇总、每日明细、今日统计等查询逻辑。

### API 路由

新建 `app/routers/trip.py`：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/trip/monthly-summary` | GET | 月度统计表，支持 year、deptId、type、employeeName 筛选 |
| `/api/trip/daily-detail` | GET | 某员工某月逐日明细 |
| `/api/trip/today` | GET | 今日出差/外出人员列表 |
| `/api/trip/stats` | GET | 统计卡片数据 |
| `/api/trip/export` | POST | Excel 导出 |
| `/api/trip/sync` | POST | 手动同步（admin） |

### 导出服务

`app/services/export.py` 新增 `export_trip_excel()` 函数，复用现有 openpyxl 导出逻辑。

## 前端设计

### 导航变化

顶部导航新增 Tab：`数据导出 | 外出/出差 | 数据分析 | 管理`

### 页面结构

"外出/出差"页面复用"数据导出"的布局模式：

1. **筛选面板 TripFilterPanel** — 复用部门二级联动逻辑，假期类型替换为"全部/出差/外出"
2. **统计卡片 TripStatsCards** (4 张) — 总人次、总天数、今日出差(可点击)、今日外出(可点击)
3. **Tab 切换** — "出差/外出列表" | "每日统计"
4. **数据表 TripDataTable** — 月度汇总，列：姓名、部门、出差天数、外出天数、各月明细、合计
5. **每日统计 TripDailyStats** — 热力图 + 当日详情列表
6. **弹窗 TripTodayModal** — 今日出差/外出详情

### 现有页面增强

"数据导出"的 StatsCards 新增第 6 张卡片"今日外出/出差"，点击跳转到"外出/出差"Tab。

### 组件复用策略

| 新组件 | 复用来源 | 复用方式 |
|--------|----------|----------|
| TripFilterPanel | FilterPanel | 复用部门联动逻辑，替换类型选项 |
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
| `TRIP_SYNC_CONCURRENCY` | 20 | API 并发数 |

## 不做的事

- 不查询出差/外出的目的地、事由（不需要）
- 不修改现有请假模块的任何逻辑
- 不新增 OA 审批权限
- 不处理加班数据（biz_type=1）
