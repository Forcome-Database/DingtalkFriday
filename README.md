# DingtalkFriday

员工请假数据管理系统，对接钉钉开放平台 API，支持请假数据同步、查询、统计分析与 Excel 导出。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | Vue 3 + TailwindCSS + ECharts |
| 部署 | Docker Compose (Nginx + Uvicorn) |

## 功能

- 钉钉免登 / 手机号登录，JWT 鉴权
- 一键同步部门、人员、请假数据（支持定时同步）
- 按部门/人员/日期/假期类型 筛选查询
- 请假统计分析图表
- 导出 Excel
- 管理员后台（同步管理、用户管理）

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入钉钉应用凭证等配置
```

关键配置项：

| 变量 | 说明 |
|------|------|
| `DINGTALK_APP_KEY` | 钉钉应用 AppKey |
| `DINGTALK_APP_SECRET` | 钉钉应用 AppSecret |
| `DINGTALK_CORP_ID` | 企业 CorpId |
| `ROOT_DEPT_ID` | 根部门 ID |
| `ADMIN_PHONES` | 管理员手机号（逗号分隔） |
| `JWT_SECRET` | JWT 签名密钥 |
| `SYNC_CRON` | 定时同步 cron 表达式（留空则不启用） |
| `DINGTALK_STREAM_ENABLED` | 开启审批、通讯录事件增量同步，默认 false |
| `DINGTALK_STREAM_COMPENSATION_ENABLED` | 真实审批事件投递验收后启用已知日期补偿，默认 false |
| `LEAVE_SYNC_VERIFY_VACATION` | 对请假状态进行流水复核，默认 true |
| `DINGTALK_REQUEST_INTERVAL` | 全局接口请求启动间隔，默认 0.05 秒 |

### 2. Docker 部署（推荐）

```bash
docker-compose up -d
```

前端访问 `http://localhost` ，API 通过 Nginx 反向代理到后端。

### Stream 与补偿同步

在钉钉开发者后台启用 Stream，订阅 `bpms_instance_change` 和通讯录变更事件，并开通 `Workflow.Instance.Read`。发布应用配置后设置 `DINGTALK_STREAM_ENABLED=true`，重建后端容器。

事件先写入 SQLite inbox，再确认接收；重复事件合并，失败持久化重试。审批变化刷新原日期和新日期，请假按受影响员工与年份刷新。审批详情无读取权限时，退回该员工已有历史日期及配置扫描窗口，保留数据覆盖，但请求数更多。`/api/sync/status` 返回事件连接、积压和权限状态。

人工全量同步和指定月份刷新保留。仅开启 Stream 时仍保留原每日完整扫描，同时处理事件增量。真实审批变更自动投递、详情解析及日期刷新验收后，再设置 `DINGTALK_STREAM_COMPENSATION_ENABLED=true`：出差定时任务每天校验已知日期，每周一完整扫描配置窗口；启动、明显断连或当前未连接时恢复完整扫描。请假原定时全量任务保留，未确认来源的记录标记为 `待复核`，统计不把它们计为已审批。

### 历史出差工时修复

部署新后端后，可先预览再应用。默认仅处理缺少源时长字段的既有记录，不新增或删除历史日期；结果列出无法解析的审批与跳过原因。

执行前先定点确认考勤接口的历史查询边界，再传入 `--minimum-work-date`。2026-09-30 本企业实测最早可查询日期为 `2026-04-04`，更早返回 `850002`；该日期仅是本次实测示例，后续运行应重新核对。不可查询的历史库存保留并报告，不反复重试。

```bash
docker compose exec backend python scripts/repair_trip_durations.py --year 2026 --minimum-work-date 2026-04-04
docker compose exec backend python scripts/repair_trip_durations.py --year 2026 --minimum-work-date 2026-04-04 --apply
```

已包含源时长但仍需重新核验时添加 `--all-records`。执行前使用 SQLite backup API 创建一致备份。日分配沿用现有日历和工作窗口，源总时长保持不变；企业真实排班未接入，非标准班次仍需按企业规则核验。

### 3. 本地开发

```bash
# 后端
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
DingtalkFriday/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── config.py         # 配置管理
│   │   ├── models.py         # 数据模型
│   │   ├── auth.py           # JWT 认证
│   │   ├── dingtalk/         # 钉钉 API 封装
│   │   ├── routers/          # 路由 (auth, sync, leave, export, analytics, admin)
│   │   └── services/         # 业务逻辑
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/            # 页面 (Login, Main)
│   │   ├── components/       # 组件
│   │   ├── api/              # 接口封装
│   │   └── router/           # 路由配置
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```
