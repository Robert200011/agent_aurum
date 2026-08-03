# Aurum Agent

> 项目介绍与运行说明，统一归档于 `project_introduction/`。

Aurum Agent 是面向个人财务、存款收支和投资知识问答的智能应用。当前已完成阶段一至
阶段五：安全与租户底座、个人财务账本、知识库入库与 Hybrid Retrieval、可信引用 RAG，
以及受控编排的只读个人财务 Agent。PDF、DOCX、Markdown、TXT、CSV、XLSX 均已接入
异步解析、确定性分块、Embedding、pgvector 和原子发布；聊天链路支持 SSE、加密
Checkpoint、财务证据、知识引用、风险提示和历史恢复。阶段五最终图版本为
`finance-agent-p5.6-v1`，当前加固图版本为 `finance-agent-p6.3-v1`。阶段六 P6.1～P6.5
工程开发与本地发布/回滚演练已经完成，正式公网发布保留候选环境操作门禁。

后端采用根目录 `app/` 包布局，不再使用 `src/aurum_agent/`。现有代码按 API、Agent、
RAG、Finance、Provider、Database、Service、Worker、Observability 和 Security
边界组织，后续阶段可直接在对应领域目录内扩展。

## 项目里程碑

| 里程碑 | 状态 | 完成日期 |
| --- | --- | --- |
| 阶段一：架构和安全底座 | 已完成 | 2026-07-23 |
| 阶段二：个人财务数据基础 | 已完成 | 2026-07-24 |
| 阶段一、二配套 Web 前端 | 已完成 | 2026-07-24 |
| 阶段二收尾与四项安全审计整改 | 已完成 | 2026-07-24 |
| 阶段三：知识库管理 | 已完成 | 2026-07-29 |
| 阶段四：基础 RAG 问答 | 已完成 | 2026-07-31 |
| 阶段五：个人财务 Agent | 已完成 | 2026-08-02 |
| 阶段六 P6.1：日志脱敏与可观测性 | 已完成 | 2026-08-02 |
| 阶段六 P6.2：配额与最小安全缓存 | 已完成 | 2026-08-02 |
| 阶段六 P6.3：RAG、安全与性能回归门禁 | 已完成 | 2026-08-02 |
| 阶段六 P6.4：备份、恢复与数据保留 | 已完成 | 2026-08-02 |
| 阶段六 P6.5：生产部署、灰度发布与回滚 | 已完成 | 2026-08-02 |

完整范围、验收结果和后续阶段见
[总体技术方案](./aurum-agent-initial-design.md#0-项目里程碑与当前状态)。阶段三已固定使用
DashScope `text-embedding-v4`（1024 维）、MinIO、Celery 和显式项目—知识库绑定。
阶段六的开发批次、边界与验收标准见
[阶段六企业级加固开发方案](./aurum-agent-phase-6-plan.md)。
阶段六首批实现结果见
[P6.1 日志脱敏与可观测性验收报告](./aurum-agent-phase-6-p6.1-acceptance.md)。
P6.2 的配额、并发租约和已发布检索缓存结果见
[P6.2 用户/模型配额与最小安全缓存验收报告](./aurum-agent-phase-6-p6.2-acceptance.md)。
P6.3 的版本化 RAG/Injection 数据集、统一门禁和两档负载基线见
[P6.3 RAG、安全与性能回归门禁验收报告](./aurum-agent-phase-6-p6.3-acceptance.md)。
P6.4 的加密备份、隔离恢复和保留策略见
[P6.4 备份、恢复与数据保留验收报告](./aurum-agent-phase-6-p6.4-acceptance.md)。
P6.5 的单机生产资产、蓝绿发布与故障回滚结果见
[P6.5 生产部署、灰度发布与回滚验收报告](./aurum-agent-phase-6-p6.5-acceptance.md)，阶段汇总见
[阶段六验收汇总](./aurum-agent-phase-6-acceptance.md)。

## 阶段一已包含

- FastAPI 分层应用骨架：API、Service、Repository、Provider；
- PostgreSQL 16、pgvector 和 Redis 开发环境；
- `identity`、`finance`、`rag`、`chat`、`audit`、`agent` 数据库 schema；
- 用户注册、用户名或邮箱登录、个人资料查询和修改密码；
- Argon2id 密码哈希；
- 短期 JWT Access Token；
- 只保存 SHA-256 摘要的 Refresh Token、轮换和重用检测；
- Redis 登录失败限流和 Access Token 即时撤销；
- 可选的初始管理员幂等创建，密码必须通过环境变量显式注入且首次登录必须修改；
- 个人财务、检索日志和会话表的 PostgreSQL Row Level Security；
- 迁移所有者与最小权限 API 数据库角色分离；
- 请求 ID、安全响应头、CORS 白名单、统一错误格式和审计日志。

## 阶段二已包含

- 账户创建、查询、修改和归档；
- 收入/支出流水 CRUD、搜索、分页和账户余额联动；
- 预算 CRUD、日期范围校验、重叠预算防护和预算执行统计；
- 投资账户、持仓、买卖记录、加权成本和已实现收益计算；
- 管理员写入、登录用户读取的不可变行情快照；
- 账户余额、现金流、预算和投资组合确定性汇总；
- CSV/XLSX 流水导入、逐行错误报告和重复提交幂等；
- 应用层 `user_id` 过滤与 PostgreSQL RLS 双重用户隔离；
- 金额、数量、币种、时区和跨用户访问测试。

## 当前前端已包含

- 登录、注册、令牌自动续期、退出登录和强制修改初始密码；
- 自适应桌面端与移动端的应用框架、侧边导航和用户菜单；
- 财务总览、账户管理、流水筛选与维护、CSV/XLSX 流水导入；
- 预算管理与执行进度；
- 投资组合汇总、持仓维护、不可变买卖记录和行情快照管理；
- 管理员专属 Agent 项目、知识库和项目作用域绑定管理；
- 六类知识文档上传、不可变版本历史、源文件下载、任务进度轮询和失败重试；
- 已发布知识库的 Dense 检索测试及 Chunk 来源定位展示；
- 统一的加载、空状态、接口错误提示和人民币/美元等币种格式化。

主要接口统一位于 `/api/v1/finance`：

```text
/accounts
/transactions
/transactions/import
/budgets
/holdings
/investment-transactions
/market-snapshots
/portfolio/summary
/reports/summary
```

流水导入文件必须使用表头 `transaction_date`、`transaction_type`、`amount` 和
`category`。可选表头为 `currency`、`description` 和 `external_id`。CSV 必须使用
UTF-8；XLSX 读取活动工作表。单文件最大 10 MiB、最多 10,000 行。默认严格模式下，
任意行校验失败都会阻止整批写入；`strict=false` 时可提交其余有效行。

XLSX 在解析 XML 前会流式预检 ZIP 容器：最多允许 256 个成员、32 MiB 总解压大小、
16 MiB 单成员大小；超过 1 MiB 的成员或归档压缩比不得高于 100。工作表逐行读取并在
扫描到第 10,001 行时立即终止，空行和异常行号间隔同样计入扫描上限。

## 使用 Docker 启动完整后端

要求 Docker Desktop 已启动。

```powershell
.\scripts\generate-dev-env.ps1
docker compose up --build -d
docker compose ps
```

生成脚本使用操作系统密码学随机数创建 JWT、初始管理员和数据库密码，并且默认不会
覆盖已有 `.env`。已有开发环境不要直接覆盖 `.env`，数据库密码还必须与现有 Docker
数据卷中的角色密码保持一致或同步轮换。若 `.env` 来自旧版示例，可执行
`.\scripts\generate-dev-env.ps1 -RotateAuthSecrets` 只轮换 JWT 和初始管理员配置，
不会改动数据库密码，也不会修改已经创建的管理员登录密码；该操作会使现有
Access Token 和 Refresh Token 失效。

服务地址：

- OpenAPI：`http://127.0.0.1:8010/docs`
- 存活检查：`http://127.0.0.1:8010/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8010/api/v1/health/ready`

就绪检查会验证数据库、Redis，以及 MinIO 应用账户的对象写入、读取元数据和删除权限。
浏览器下载链接由
`GET /api/v1/admin/document-versions/{document_version_id}/download-url`
按 `AURUM_OBJECT_STORAGE_EXTERNAL_ENDPOINT` 签发；该值必须是浏览器可访问的地址，
不能填写 Docker 内部的 `http://minio:9000`。

## 启动前端

要求已安装 Node.js 24，并已按上文启动后端。首次运行时安装依赖：

```powershell
Set-Location web
npm install
Copy-Item .env.example .env
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。开发服务器会把 `/api` 请求代理到
`http://127.0.0.1:8010`，通常不需要额外处理跨域。前端生产构建命令：

```powershell
npm run build
```

首次登录使用 `.env` 中生成的 `AURUM_ADMIN_INITIAL_PASSWORD`：

```json
{
  "identifier": "admin",
  "password": "<AURUM_ADMIN_INITIAL_PASSWORD 中的值>"
}
```

初始管理员会收到 `must_change_password: true`。调用
`POST /api/v1/auth/change-password` 后，当前 Access Token 和该用户全部 Refresh Token
都会失效，需要使用新密码重新登录。

## 在 PyCharm 中直接运行 API

如果需要在 PyCharm 中直接运行和断点调试 Python API，推荐使用 Python 3.12。
Docker API 使用 `8010`，PyCharm 直接运行的 API 使用 `8011`，两者可以同时运行。
如果尚未安装本地依赖或启动基础设施，可执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\scripts\generate-dev-env.ps1
docker compose up -d postgres redis
alembic upgrade head
aurum-agent grant-app-role
```

然后可以在 PyCharm 中右键 `app/main.py`，选择“运行 main”，服务器会监听
`http://127.0.0.1:8011`。也可以在项目根目录执行：

```powershell
python -m app.main
```

需要代码热重载时，改用：

```powershell
python -m uvicorn app.main:app --reload --port 8011
```

`app/main.py` 中的直接启动入口只在执行该文件时生效。Docker 和 Uvicorn
以 `app.main:app` 导入应用时不会重复启动服务器。

Docker 服务端口由 `.env` 中的 `AURUM_SERVER_PORT=8010` 控制，PyCharm
直接运行端口由 `AURUM_DIRECT_SERVER_PORT=8011` 控制。如需再次更换端口，
修改对应值并重启相应 API 即可。

## 常用验证

```powershell
python -m pytest
python -m ruff check app migrations tests
alembic check
docker compose config --quiet

Set-Location web
npm run check
npm run build
npm audit --audit-level=high
```

## 项目结构

```text
agent_aurum/
├── app/
│   ├── api/                 # FastAPI 路由、依赖和请求响应模型
│   ├── agents/              # LangGraph 状态、图、节点、工具和策略
│   ├── rag/                 # 文档加载、切分、向量化、检索、重排和引用
│   ├── finance/             # 财务导入、校验、计算和汇总
│   ├── providers/           # 身份、模型、行情、存储和向量库适配层
│   ├── db/                  # SQLAlchemy 模型、Repository、会话和数据库初始化
│   ├── services/            # 应用用例与事务编排
│   ├── workers/             # 异步任务
│   ├── observability/       # 日志、指标和链路追踪
│   ├── security/            # 密码、令牌和授权安全原语
│   ├── config.py
│   └── main.py
├── web/                     # Vue 3、TypeScript、Vite 和 Ant Design Vue 前端
├── migrations/              # Alembic 数据库迁移
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   └── rag_eval/
├── evals/
├── scripts/
└── deploy/
```

## 配置与密钥

配置统一使用环境变量；应用本身不再包含 JWT、初始管理员或数据库密码的可用默认值。
`AURUM_JWT_SECRET_KEY`、`AURUM_DATABASE_URL` 和
`AURUM_MIGRATION_DATABASE_URL` 缺失时，任何环境都会拒绝启动。管理员引导默认关闭；
只有显式设置 `AURUM_BOOTSTRAP_ADMIN=true` 时，才必须同时提供符合密码规则的
`AURUM_ADMIN_INITIAL_PASSWORD`。

`.env` 只用于本地开发并已被 Git 忽略，新环境应通过
`.\scripts\generate-dev-env.ps1` 生成。生产容器应由 Docker/Kubernetes Secret
注入同名变量；当 `AURUM_ENVIRONMENT=production` 时，应用还会拒绝 Debug 或不安全的
Refresh Token Cookie 配置。

Refresh Token 只通过限定认证接口路径的 HttpOnly Cookie 下发，不会出现在 API 响应体
或浏览器 `localStorage` 中。默认 `SameSite=Lax` 适用于前后端同站部署；如果生产环境
确实需要跨站部署，应同时设置 `AURUM_REFRESH_TOKEN_COOKIE_SAMESITE=none`、启用
Secure Cookie，并确保 HTTPS 与 `AURUM_CORS_ORIGINS` 的来源白名单配置正确。

登录接口在密码校验前通过 Redis 执行原子限流，默认限制为单 IP 每 60 秒 30 次、
全局每 60 秒 300 次；原有的“标识符 + IP”失败锁定仍独立生效。可通过
`AURUM_LOGIN_IP_REQUEST_LIMIT`、`AURUM_LOGIN_GLOBAL_REQUEST_LIMIT` 和
`AURUM_LOGIN_REQUEST_WINDOW_SECONDS` 调整容量，触发限制时接口返回 `429` 和
`Retry-After`。

生产部署前还应：

1. 使用密钥管理系统注入 JWT 密钥和初始管理员密码；
2. 在反向代理处启用 HTTPS；
3. 使用独立的迁移账号和最小权限 API 数据库账号；
4. 不向公网暴露 PostgreSQL、Redis；
5. 按 [部署指南](./aurum-agent-deployment-guide.md) 完成备份、监控和回滚演练。

## 数据隔离约束

RLS 策略读取事务局部参数 `app.current_user_id`。任何访问用户财务、检索日志或会话数据
的 Repository，必须先调用：

```python
await set_tenant_context(session, current_user.id)
```

Repository 查询仍须显式包含 `user_id` 条件。RLS 是第二道防线，不能替代应用层授权。
