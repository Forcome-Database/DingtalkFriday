# 员工请假数据导出系统 - 详细开发设计方案

## 一、架构概述

### 技术栈
- **后端**: Python 3.11+ / FastAPI / SQLAlchemy / SQLite
- **前端**: Vue 3 + Vite + TailwindCSS + Lucide Icons
- **部署**: Docker Compose (前端Nginx + 后端Uvicorn)
- **数据源**: 钉钉开放平台 API

### 目录结构
```
DingtalkFriday/
├── backend/                   # 后端项目
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI入口
│   │   ├── config.py         # 配置（钉钉AppKey等）
│   │   ├── database.py       # SQLite数据库连接
│   │   ├── models.py         # SQLAlchemy模型
│   │   ├── schemas.py        # Pydantic响应模型
│   │   ├── dingtalk/         # 钉钉API封装
│   │   │   ├── __init__.py
│   │   │   ├── client.py     # 钉钉HTTP客户端（token管理）
│   │   │   ├── department.py # 部门相关API
│   │   │   ├── user.py       # 用户相关API
│   │   │   └── attendance.py # 考勤/请假API
│   │   ├── services/         # 业务逻辑层
│   │   │   ├── __init__.py
│   │   │   ├── sync.py       # 数据同步服务
│   │   │   ├── leave.py      # 请假数据查询服务
│   │   │   └── export.py     # Excel导出服务
│   │   └── routers/          # API路由
│   │       ├── __init__.py
│   │       ├── departments.py
│   │       ├── leave.py
│   │       └── export.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                  # 前端项目
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── api/              # API调用封装
│   │   │   └── index.js
│   │   ├── components/       # 组件
│   │   │   ├── AppHeader.vue
│   │   │   ├── FilterPanel.vue
│   │   │   ├── StatsCards.vue
│   │   │   ├── DataTable.vue
│   │   │   ├── LeaveCalendarModal.vue
│   │   │   └── Pagination.vue
│   │   └── composables/      # 组合式函数
│   │       └── useLeaveData.js
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── docs/
```

## 二、钉钉API对接方案

### 核心接口

| 接口 | 用途 | 频率限制 |
|------|------|---------|
| `GET /gettoken` | 获取access_token | 缓存2h |
| `POST /topapi/v2/department/listsub` | 获取子部门列表 | 按需 |
| `POST /topapi/v2/department/listsubid` | 获取子部门ID列表 | 按需 |
| `POST /topapi/user/listsimple` | 获取部门用户列表 | cursor分页,每页100 |
| `POST /topapi/attendance/getleavestatus` | 查询请假状态(含未来) | 最多180天,100人/批,分页20 |
| `POST /topapi/attendance/vacation/type/list` | 查询假期类型列表 | 按需 |

### 数据同步策略

由于 `getleavestatus` 接口限制单次最多查询180天，全年需分两次：
- 第一次: 1月1日 ~ 6月30日
- 第二次: 7月1日 ~ 12月31日

**包含未来请假**: `getleavestatus` 返回的是指定时间段内每天的请假状态，已审批但尚未发生的请假也会包含在内。

### Token管理
- 使用内存缓存access_token，有效期2小时
- 过期前5分钟自动刷新
- 并发请求共享同一token

## 三、数据模型 (SQLite)

```sql
-- 部门表
CREATE TABLE department (
    dept_id INTEGER PRIMARY KEY,     -- 钉钉部门ID
    name TEXT NOT NULL,
    parent_id INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 员工表
CREATE TABLE employee (
    userid TEXT PRIMARY KEY,          -- 钉钉用户ID
    name TEXT NOT NULL,
    dept_id INTEGER NOT NULL,
    dept_name TEXT,
    avatar TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 请假记录表（从getleavestatus同步）
CREATE TABLE leave_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid TEXT NOT NULL,
    start_time INTEGER NOT NULL,       -- Unix毫秒时间戳
    end_time INTEGER NOT NULL,
    duration_percent INTEGER NOT NULL,  -- 时长*100
    duration_unit TEXT NOT NULL,        -- percent_day | percent_hour
    leave_type TEXT DEFAULT '请假',     -- 假期类型名称
    leave_code TEXT,                    -- 假期类型编码
    status TEXT DEFAULT '已审批',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(userid, start_time, end_time)
);

-- 假期类型表
CREATE TABLE leave_type (
    leave_code TEXT PRIMARY KEY,
    leave_name TEXT NOT NULL,
    leave_view_unit TEXT,              -- day | halfDay | hour
    hours_in_per_day INTEGER,          -- 每天工时*100
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 同步记录表
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,           -- department | employee | leave
    status TEXT NOT NULL,              -- running | success | failed
    message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);
```

## 四、后端API设计

### 4.1 部门接口
```
GET /api/departments?parentId={id}
→ 从本地DB查询，不存在则同步钉钉数据
Response: [{ dept_id, name, parent_id, hasChildren }]
```

### 4.2 请假月度汇总
```
GET /api/leave/monthly-summary
Params: year, deptId, leaveTypes[], employeeName, unit(day|hour), page, pageSize, sortBy, sortOrder
Response: {
  stats: { totalCount, totalDays, avgDays, annualRatio, annualDays },
  list: [{ employeeId, name, dept, avatar, months[12], total }],
  summary: { personCount, months[12], total },
  pagination: { page, pageSize, total }
}
```

### 4.3 日历明细
```
GET /api/leave/daily-detail?employeeId={id}&year={y}&month={m}
Response: {
  employee: { name, dept, avatar },
  records: [{ date, startTime, endTime, hours, leaveType, status }],
  summary: { totalDays, totalHours }
}
```

### 4.4 导出Excel
```
POST /api/leave/export
Body: { year, deptId, leaveTypes[], employeeName, unit }
Response: xlsx文件流
```

### 4.5 数据同步
```
POST /api/sync              # 触发全量同步
GET  /api/sync/status       # 查询同步状态
```

## 五、前端组件设计

### 5.1 AppHeader.vue
- 左侧：Lucide calendar-days图标 + 系统标题
- 右侧：用户图标 + 姓名 + 导出Excel按钮 + 同步数据按钮

### 5.2 FilterPanel.vue
- 部门联动下拉：一级→二级，支持"全部"
- 员工姓名输入框：防抖300ms
- 年份选择器：近5年下拉
- 请假类型多选标签：年假(蓝)、事假(黄)、病假(红)、调休(绿) + 全部按钮
- 查询/重置按钮

### 5.3 StatsCards.vue
- 4张统计卡片：请假总人次、请假总天数、人均请假、年假占比
- 带图标和颜色区分

### 5.4 DataTable.vue
- 固定列：姓名(90px)、部门(90px)
- 动态列：1-12月（自适应）
- 固定列：合计(60px，蓝底高亮)
- 单元格：有数据加粗+类型颜色，无数据灰色"-"
- 底部合计行：蓝底
- 天/小时切换分段控件
- 合计列排序
- 分页组件

### 5.5 LeaveCalendarModal.vue
- 抽屉/弹窗形式
- 头部：员工信息 + 年月
- 月度日历网格：全天蓝色实底、不足全天蓝色虚线、无请假无背景
- 请假记录列表：日期、时段、时长、类型标签、审批状态
- 底部汇总：天数 + 小时数

## 六、多Agent开发分工

### Agent 1: 后端开发 (Backend Agent)
负责内容：
1. 项目初始化（FastAPI + SQLite + 依赖）
2. 钉钉API客户端封装（token管理、部门、用户、考勤接口）
3. 数据模型和数据库初始化
4. 数据同步服务（部门→员工→请假数据）
5. 业务查询服务（月度汇总、日历明细、统计计算）
6. Excel导出服务（openpyxl）
7. API路由和接口实现
8. .env配置和Dockerfile

### Agent 2: 前端开发 (Frontend Agent)
负责内容：
1. Vue3 + Vite项目初始化 + TailwindCSS配置
2. 参照.pen UI文档开发所有组件
3. API调用层封装（axios）
4. 页面布局和响应式适配
5. 交互逻辑（筛选、分页、排序、弹窗）
6. Dockerfile + nginx.conf

### Agent 3: 接口联调 (Integration Agent)
在前后端完成后：
1. 验证所有API接口响应格式匹配
2. 修复前后端数据格式不一致问题
3. 测试筛选→查询→明细→导出完整流程
4. 处理跨域、错误处理、loading状态

### Agent 4: 测试 (Testing Agent)
1. 后端单元测试（pytest）
2. API接口测试
3. 前端组件检查
4. docker-compose集成测试
5. 验收测试（对照需求文档逐项检查）

## 七、开发顺序

1. **Phase 1** [并行]: 后端Agent + 前端Agent 同时开发
2. **Phase 2** [串行]: 联调Agent 整合前后端
3. **Phase 3** [串行]: 测试Agent 验证
4. **Phase 4**: docker-compose.yml 和最终集成
