# 今日请假详情弹窗 — 设计文档

## 概述

在"今日请假"统计卡片上增加点击交互，弹出右侧滑出面板，展示每位请假员工的详细信息，包括姓名、头像、部门、假期类型、具体时间段（如 09:00-14:00）、时长（如 5小时）和审批状态。

## 需求

- 点击"今日请假"卡片弹出详情面板
- 每条记录展示：头像、姓名、部门、假期类型（颜色编码）、时间段、时长、审批状态
- 右侧滑出面板风格，与现有 LeaveCalendarModal 一致
- 移动端全屏适配
- 纯展示，列表项不可点击

## 后端 API

### `GET /api/leave/today-detail`

**权限**：普通用户（`get_current_user`）

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| deptId | int | 否 | 部门 ID |
| leaveTypes | string | 否 | 假期类型，逗号分隔 |
| employeeName | string | 否 | 员工姓名模糊搜索 |

**响应**：

```json
{
  "count": 11,
  "records": [
    {
      "userid": "xxx",
      "name": "Abby 周玉丹",
      "avatar": "https://...",
      "deptName": "BBC 垂直平台事业部",
      "leaveType": "FSH法定年假",
      "leaveCode": "annual",
      "startTime": 1743573600000,
      "endTime": 1743591600000,
      "durationPercent": 500,
      "durationUnit": "percent_hour",
      "durationDisplay": "5小时",
      "timeDisplay": "09:00 - 14:00",
      "status": "已审批"
    }
  ]
}
```

**设计要点**：

- `durationDisplay` 和 `timeDisplay` 由后端计算，避免前端处理时区和单位换算
- 同一人可能有多条记录（如上午事假 + 下午年假），每条独立返回
- 查询逻辑：`start_time < 今日结束` AND `end_time > 今日开始`（overlap 判断）
- JOIN Employee 表获取 name、avatar、dept_name

## 前端组件

### TodayLeaveModal.vue（新建）

**面板骨架**（复用 LeaveCalendarModal 模式）：

- `<Teleport to="body">` + 遮罩（`bg-black/40`）+ 右侧滑出（`w-full sm:w-[480px]`）
- fade + slide transition 动画

**面板布局**：

```
┌──────────────────────────┐
│  今日请假详情    11人   ✕  │  头部：标题 + 人数 + 关闭按钮
├──────────────────────────┤
│  ┌─────────────────────┐ │
│  │ [头像] Abby 周玉丹   │ │  头像(32px圆形) + 姓名
│  │ BBC 垂直平台事业部    │ │  部门
│  │ [年假] 09:00 - 14:00 │ │  假期类型标签 + 时间段
│  │        5小时   已审批  │ │  时长 + 审批状态
│  └─────────────────────┘ │
│  ┌─────────────────────┐ │
│  │ [头像] Alan 顾奇帆   │ │
│  │ IBU 信息技术事业部    │ │
│  │ [事假] 09:00 - 18:00 │ │
│  │        1天     已审批  │ │
│  └─────────────────────┘ │
│  ... 可滚动 ...           │
├──────────────────────────┤
│  共 11 人请假             │  底部统计栏
└──────────────────────────┘
```

**列表项样式**：

- 每项 `rounded-xl border-[1.5px] border-border-default` 卡片
- 头像 32px 圆形，姓名 `text-text-primary font-medium`
- 部门 `text-text-tertiary text-[13px]`
- 假期类型颜色编码（年假蓝、事假黄、病假红、调休绿，复用 tailwind.config.js 中定义的颜色）
- 时间段 `text-text-primary`，时长 `text-text-secondary`
- 审批状态：已审批=绿色、审批中=橙色、已驳回=红色

**状态处理**：

- Loading：3 个骨架屏占位卡片
- Empty：居中图标 + "今日无人请假" 文字
- Error：重试按钮

### StatsCards.vue（修改）

- "今日请假"卡片增加 `cursor-pointer`
- hover 效果：`hover:border-accent hover:shadow-sm transition-all`
- 点击 emit `todayLeaveClick` 事件

### MainView.vue（修改）

- 引入 TodayLeaveModal 组件
- 管理 `showTodayLeaveModal` 状态
- 将当前筛选参数（deptId、leaveTypes、employeeName）传递给 TodayLeaveModal

### api/index.js（修改）

- 新增 `getTodayLeaveDetail(params)` 方法

## 数据流

```
用户点击"今日请假"卡片
  → StatsCards emit('todayLeaveClick')
  → MainView 设置 showTodayLeaveModal = true
  → TodayLeaveModal mounted 时调用 GET /api/leave/today-detail
  → 展示列表（带 loading 态）
  → 关闭面板时清空数据
```

筛选参数透传当前 FilterPanel 选中状态，确保弹窗数据与卡片数字一致。

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/routers/leave.py` | 修改 | 新增 `today-detail` 端点 |
| `backend/app/services/leave.py` | 修改 | 新增 `get_today_leave_detail()` 服务函数 |
| `backend/app/schemas.py` | 修改 | 新增 response/record schema |
| `frontend/src/api/index.js` | 修改 | 新增 `getTodayLeaveDetail()` |
| `frontend/src/components/TodayLeaveModal.vue` | 新建 | 右侧滑出面板组件 |
| `frontend/src/components/StatsCards.vue` | 修改 | 卡片加 click + hover |
| `frontend/src/views/MainView.vue` | 修改 | 引入 Modal，管理状态 |

## 不变更

- `backend/app/models.py` — 数据库已有完整字段，无需新增
- `LeaveCalendarModal.vue` — 不受影响
- `DailyLeaveStats.vue` — 不受影响
