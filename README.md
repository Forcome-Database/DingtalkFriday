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

### 2. Docker 部署（推荐）

```bash
docker-compose up -d
```

前端访问 `http://localhost` ，API 通过 Nginx 反向代理到后端。

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
