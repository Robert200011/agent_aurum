# Aurum Agent 阶段一交接与后续里程碑文档

> 文档用途：保留阶段一交接快照，并记录后续里程碑，避免重复排查与重复设计。
> 阶段一交接时间：2026-07-23
> 后续状态更新时间：2026-07-24
> 项目路径：`E:\agent_aurum`
> 当前阶段：阶段一、阶段二及配套 Web 前端已完成，阶段三尚未开始。

## 0. 后续里程碑更新

本文件主体保留 2026-07-23 阶段一交接时的历史快照。后续实际进展如下：

| 里程碑 | 状态 | 完成日期 | 基线或说明 |
| --- | --- | --- | --- |
| 阶段一：架构和安全底座 | 已完成 | 2026-07-23 | 稳定基线 `933390a` |
| 阶段二：个人财务数据基础 | 已完成 | 2026-07-24 | 合并提交 `3bfb9b0` |
| 阶段一、二配套 Web 前端 | 已完成 | 2026-07-24 | 位于 `web/` |
| 阶段二安全审计整改 | 已完成 | 2026-07-24 | 四项高优先级遗留项全部修复 |
| 阶段三：知识库管理 | 尚未开始 | — | 下一阶段 |

阶段二主要完成账户、流水、预算、投资、行情快照、财务汇总、CSV/XLSX 导入以及
应用过滤与 RLS 双重用户隔离。配套前端完成登录注册、响应式应用框架、财务总览、
账户、流水、预算和投资管理。

安全审计整改完成以下事项：

- Refresh Token 改为认证接口路径下的 HttpOnly Cookie；
- 登录接口增加单 IP 和全局限流；
- XLSX 导入增加流式行数限制和压缩炸弹防护；
- 移除 JWT、初始管理员和数据库密码的可用开发默认值。

截至 2026-07-24，知识库管理、文档入库、LangGraph、RAG 问答、引用展示和 Agent
工具编排仍未实现。当前状态以
[总体技术方案](./aurum-agent-initial-design.md#0-项目里程碑与当前状态)和
[README](./README.md#项目里程碑)为准。

## 1. 阶段一交接时的一页结论（历史快照）

Aurum Agent 是一个独立开发的 Python 金融财务管理与投资知识问答项目。当前不依赖
`E:\personal_project_1`，后者即使继续使用 Go 开发，也不会影响本项目；未来需要拉通时，
应通过 REST API、OIDC 或消息事件等明确边界集成，不直接共享业务数据库。

截至 2026-07-23 阶段一交接时，已完成的是后端基础设施、安全与数据底座：

- FastAPI 后端应用、分层目录和统一配置；
- PostgreSQL 16、pgvector、Redis、Docker Compose；
- 用户注册、登录、刷新令牌、登出、修改密码和当前用户查询；
- 可选的初始管理员幂等创建及首次登录强制改密；
- Argon2id、JWT Access Token、Refresh Token 轮换与重用检测；
- Redis 登录失败限流和 Access Token 撤销；
- 用户、财务、RAG、会话及审计数据模型；
- PostgreSQL Row Level Security（RLS）租户隔离基础；
- 健康检查、统一异常格式、请求 ID、安全响应头、CORS 和审计日志；
- Alembic 迁移、测试、静态检查、类型检查和容器化运行。

在该历史时间点尚未完成浏览器前端、财务业务接口、知识库管理、文档解析与入库、
LangGraph 工作流、RAG 检索问答、引用展示和历史会话接口。阶段二和配套前端的后续
完成情况见本文件第 0 节。

## 2. 阶段一 Git 基线（历史快照）

本次交接前已通过 `git-manager` 只读检查确认：

| 项目 | 当前值 |
| --- | --- |
| 当前分支 | `feature/phase-2-knowledge-rag` |
| 当前 HEAD | `933390a872590b47e6e10af7c1bf23b564847bf0` |
| 提交说明 | `feat: complete phase 1 architecture and security foundation` |
| 主干 | `master`，与当前分支指向同一提交 |
| 上游分支 | 未配置 |
| 远程仓库 | 未配置 |
| 进行中的 Git 操作 | 无 |
| 交接文档创建前的工作区 | 干净 |

注意：

- 阶段一稳定基线是提交 `933390a872590b47e6e10af7c1bf23b564847bf0`；
- 当前功能分支是从该提交创建的，尚无第二阶段代码；
- 本交接文档是基线提交之后新增的本地文件，后续可由用户决定提交到 Git，或加入本地忽略；
- 不要在未确认需求前合并、重命名或删除分支；
- 当前分支名包含 `knowledge-rag`，但原计划中的“阶段二”是个人财务数据基础，二者存在命名与范围
  不一致。新会话开始开发前应先向用户确认第二阶段究竟优先做财务 CRUD，还是知识库与 RAG。

## 3. 项目目标与约束

目标产品是一个支持多用户的个人金融财务与投资 Agent，最终应实现：

- 浏览器注册、登录、修改密码和鉴权；
- 普通用户只能进行问答和管理自己的财务、会话数据；
- 只有管理员可以打开并操作知识库和项目管理界面；
- 多用户、多会话、历史对话持久化与恢复；
- 财务收支、账户、预算、股票、基金、存款和投资数据管理；
- 基于知识库的问答、结构化引用和引用原文查看；
- LangGraph 编排的财务工具调用与 RAG 混合回答；
- 企业级安全、性能、可观测性、评测、备份和部署能力。

当前明确约束：

- 本项目以 Python 为主，后端框架为 FastAPI；
- Agent 编排计划优先使用 LangGraph，但依赖和工作流尚未引入；
- 向量检索已选 PostgreSQL + pgvector，当前不采用 ChromaDB 作为主向量库；
- 前端预定 Vue 3，当前仅有占位目录；
- 本阶段不处理 `E:\personal_project_1`；
- `.env` 仅用于本机开发，真实密钥不得提交；
- 后续安全加固已移除初始管理员、JWT 和数据库密码的可用开发默认值。

## 4. 当前代码结构

```text
agent_aurum/
├── app/
│   ├── api/                 # 已实现认证、用户和健康检查；其余接口多为占位
│   ├── agents/              # LangGraph 目录占位
│   ├── db/
│   │   ├── models/          # identity、finance、rag、chat 数据模型
│   │   ├── repositories/    # 当前仅实现身份与令牌 Repository
│   │   ├── base.py
│   │   ├── bootstrap.py
│   │   └── session.py
│   ├── finance/             # 财务导入、校验、计算、汇总目录占位
│   ├── observability/       # 当前实现基础日志配置
│   ├── providers/           # 身份已实现；模型、向量、对象存储等仅有 Protocol
│   ├── rag/                 # 加载、切分、Embedding、检索、重排、引用目录占位
│   ├── security/            # 密码、JWT、Refresh Token 安全原语
│   ├── services/            # 已实现认证和管理员初始化
│   ├── workers/             # 异步任务目录占位
│   ├── cli.py               # serve、bootstrap-admin、grant-app-role
│   ├── config.py            # Pydantic Settings 和生产安全校验
│   └── main.py              # FastAPI 工厂、生命周期、中间件、直接启动入口
├── migrations/              # Alembic 迁移
├── scripts/postgres/init/   # PostgreSQL 应用角色初始化
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/            # 占位
│   ├── e2e/                 # 占位
│   └── rag_eval/            # 占位
├── web/                     # Vue 3 前端占位，尚未初始化 Node 工程
├── deploy/                  # 部署资产占位
├── evals/                   # 评测资产占位
├── compose.yaml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md
```

历史上的 `src/aurum_agent/` 布局已经取消。当前正式包路径是根目录下的 `app/`，不要重新创建
或恢复旧 `src` 结构。

## 5. 已实现功能

### 5.1 API

当前注册到 FastAPI 主路由的模块只有 `system`、`auth` 和 `users`。

| 方法 | 路径 | 状态 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health/live` | 已实现 | 进程存活检查 |
| `GET` | `/api/v1/health/ready` | 已实现 | PostgreSQL、Redis 就绪检查 |
| `POST` | `/api/v1/auth/register` | 已实现 | 普通用户注册 |
| `POST` | `/api/v1/auth/login` | 已实现 | 用户名或邮箱登录 |
| `POST` | `/api/v1/auth/refresh` | 已实现 | Refresh Token 轮换 |
| `POST` | `/api/v1/auth/logout` | 已实现 | Access/Refresh Token 撤销 |
| `POST` | `/api/v1/auth/change-password` | 已实现 | 修改密码并使旧令牌失效 |
| `GET` | `/api/v1/users/me` | 已实现 | 获取当前登录用户 |

`accounts.py`、`transactions.py`、`budgets.py`、`holdings.py`、`projects.py`、
`knowledge_bases.py`、`documents.py`、`conversations.py` 和 `chat.py` 目前没有实际路由，
也没有注册到 `app/api/router.py`。

### 5.2 身份与安全

- 密码使用 Argon2id 哈希；
- 密码强度验证在安全层统一处理；
- Access Token 是短期 JWT，带 issuer、audience、JTI、角色和 token version；
- Refresh Token 只在数据库保存 SHA-256 摘要，不保存明文；
- Refresh Token 支持轮换、令牌家族撤销和重用检测；
- 修改密码后撤销用户全部 Refresh Token，并通过 token version 使旧 Access Token 失效；
- Redis 保存登录失败计数和被撤销 Access Token 的 JTI；
- 登录失败限制默认是 15 分钟内 5 次；
- 已有 `require_admin` / `AdminContextDependency`，但尚无知识库管理接口使用它；
- 初始管理员由应用启动生命周期幂等创建；
- 初始管理员第一次登录返回 `must_change_password: true`，未改密前不能通过管理员依赖；
- JWT 和数据库连接必须显式配置；管理员引导开启时必须显式提供初始密码；
- API 包含请求关联 ID、保守安全响应头、CORS 白名单和统一错误响应。

### 5.3 数据库和租户隔离

已创建六个 PostgreSQL schema：

- `identity`
- `finance`
- `rag`
- `chat`
- `audit`
- `agent`

已定义的数据表：

| 领域 | 表/模型 |
| --- | --- |
| 身份与审计 | `users`、`refresh_tokens`、`audit_logs` |
| 财务 | `financial_accounts`、`financial_transactions`、`budgets`、`investment_holdings`、`investment_transactions`、`market_price_snapshots` |
| RAG | `agent_projects`、`knowledge_bases`、`project_knowledge_bases`、`documents`、`document_versions`、`document_chunks`、`ingestion_jobs`、`retrieval_logs` |
| 会话 | `conversations`、`messages`、`message_citations`、`agent_runs` |

迁移状态：

- `20260723_0001`：创建 schema、vector 扩展、全部基础表和租户 RLS；
- `20260723_0002`：规范化身份枚举值；
- 当前数据库位于 `20260723_0002 (head)`；
- `document_chunks.embedding` 已使用 pgvector 的 `Vector()` 字段；
- 尚未确定实际 Embedding 维数，也尚未创建 HNSW/IVFFlat 向量索引。

RLS 已启用并强制应用于以下用户数据表：

- 财务账户、财务流水、预算、投资持仓、投资交易；
- 检索日志；
- 会话、消息、消息引用、Agent 运行记录。

租户访问必须在同一数据库事务内先执行：

```python
await set_tenant_context(session, current_user.id)
```

Repository 查询仍必须显式携带 `user_id` 条件，RLS 只是第二道隔离防线。

## 6. 阶段一交接时已预留但尚未实现（历史快照）

以下内容只有目录、数据模型、Protocol 或空模块，接手时不要误认为已有业务逻辑：

- LangGraph `StateGraph`、节点、工具、策略和 Checkpointer；
- 大模型、Embedding 和 Reranker 的具体供应商适配；
- pgvector 检索 Repository 和混合检索；
- 对象存储实现；
- PDF、DOCX、Markdown、TXT、CSV、XLSX 文档解析；
- 文档切分、去重、Embedding、版本化和异步入库；
- 知识库、项目、文档管理 API；
- 财务账户、收支、预算、持仓、投资交易和行情 API；
- CSV/Excel 账单导入及数据校验；
- 财务聚合、统计与确定性计算工具；
- 会话、消息、引用和 Agent Run 的 Repository/API；
- SSE 流式回答；
- 引用片段展示和引用原文定位；
- Vue 3 浏览器端；
- Celery 或其他异步任务系统；
- MinIO/S3；
- OpenTelemetry、Prometheus、Grafana；
- RAG 回归评测、端到端测试和压力测试；
- Kubernetes 或正式生产部署资产。

当前 `pyproject.toml` 中也尚未安装 LangGraph、LangChain、文档解析、对象存储、Celery、
前端或模型 SDK 依赖。这是因为对应能力尚未开发，不是当前环境漏装。

## 7. 运行方式

### 7.1 Docker 启动完整后端

在 `E:\agent_aurum` 中执行：

```powershell
.\scripts\generate-dev-env.ps1
docker compose up --build -d
docker compose ps
```

常用地址：

- Swagger/OpenAPI：`http://127.0.0.1:8010/docs`
- 存活检查：`http://127.0.0.1:8010/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8010/api/v1/health/ready`

当前本机 Docker 实际状态：

- API：`127.0.0.1:8010`，健康；
- PostgreSQL：`127.0.0.1:5432`，健康；
- Redis：`127.0.0.1:6380` 映射到容器 `6379`，健康。

`.env.example` 默认 Redis 主机端口是 `6379`；当前本机因为端口占用使用了 `6380`。
不要把当前本机端口误写成所有环境的固定要求。

### 7.2 PyCharm 直接运行

Python 版本要求是 `>=3.12,<3.14`。当前验证使用：

```text
D:\anaconda\python.exe
Python 3.13.5
```

本地依赖安装：

```powershell
python -m pip install -e ".[dev]"
```

先启动基础设施并迁移：

```powershell
docker compose up -d postgres redis
alembic upgrade head
aurum-agent grant-app-role
```

然后右键运行 `app/main.py`，或执行：

```powershell
python -m app.main
```

直接运行默认监听 `http://127.0.0.1:8011`，与 Docker API 的 `8010` 分开，二者可以同时运行。

如需热重载：

```powershell
python -m uvicorn app.main:app --reload --port 8011
```

端口配置：

- `AURUM_SERVER_PORT=8010`：Docker/CLI API；
- `AURUM_DIRECT_SERVER_PORT=8011`：直接执行 `app/main.py`；
- 本机 Redis 暴露端口若改为 `6380`，应同时保证本地 API 的 `AURUM_REDIS_URL` 指向 `6380`。

### 7.3 管理员首次使用

开发环境初始凭据：

```json
{
  "identifier": "admin",
  "password": "<AURUM_ADMIN_INITIAL_PASSWORD 中的值>"
}
```

登录后必须调用：

```text
POST /api/v1/auth/change-password
```

改密会使当前 Access Token 和该用户所有 Refresh Token 失效，需要使用新密码重新登录。

## 8. 2026-07-23 实时验证结果

本次交接重新执行了以下检查：

| 检查 | 结果 |
| --- | --- |
| `python -m pytest` | 通过，`24 passed` |
| `python -m ruff check app migrations tests` | 通过 |
| `python -m mypy app migrations` | 通过，检查 69 个源文件 |
| `python -m pip check` | 通过，无损坏依赖 |
| `python -m alembic check` | 通过，无待生成迁移 |
| `python -m alembic current` | `20260723_0002 (head)` |
| `docker compose config --quiet` | 通过 |
| `docker compose ps` | API、PostgreSQL、Redis 全部 healthy |
| `/api/v1/health/live` | `{"status":"ok"}` |
| `/api/v1/health/ready` | 数据库和 Redis 均为 `true` |

已知质量项：

```powershell
python -m mypy app migrations tests
```

该命令目前会在 `tests/unit/test_models.py` 报 4 个类型错误，涉及 SQLAlchemy/pgvector
反射对象的第三方类型信息：

- `CreateIndex` 被识别为无类型调用；
- `TypeEngine[Any]` 类型桩未声明运行时存在的 `enums` 属性。

这不影响应用运行、数据库迁移或 24 个 Pytest 测试，但下一阶段可选择：

1. 为测试中的反射类型增加精确 `cast`；
2. 对第三方类型缺口增加最小范围的 `# type: ignore[...]`；
3. 明确规定 Mypy 只检查生产代码，并在 `pyproject.toml` 中固化范围。

不要为了让 Mypy 变绿而关闭全局 strict 模式。

## 9. 本地文件与 Git 忽略

当前已明确忽略：

- `.env`
- `.idea/`
- `.agents/`
- `.codex/`
- 虚拟环境、Python 缓存、测试缓存和运行日志；
- `aurum-agent-architecture.md`
- `aurum-agent-deployment-guide.md`
- `aurum-agent-initial-design.md`

前三份方案文档只在本地使用，不进入 Git。`.agents` 和 `.codex` 是辅助 Agent/Skill
资产，不属于产品源代码。

应继续版本管理：

- `.env.example`
- `compose.yaml`
- `Dockerfile`
- `.dockerignore`
- `pyproject.toml`
- `alembic.ini`
- `migrations/`
- `scripts/`
- 产品代码和自动化测试。

不要提交真实 `.env`、密钥、数据库数据卷、IDE 用户状态或本机缓存。

## 10. 关键设计决定

### 10.1 向量数据库

主方案是 PostgreSQL + pgvector，不采用 ChromaDB 作为生产主库，原因是：

- 用户、知识库、文档、权限、向量和引用可以保持事务一致性；
- 更适合与 PostgreSQL RLS 和现有多租户模型结合；
- 运维组件更少；
- 备份、审计、迁移和高可用方案更成熟。

Provider 层仍保持抽象，未来可以增加 ChromaDB 作为本地实验或测试适配器，但不应在没有
明确需求时替换 pgvector。

### 10.2 结构化财务与非结构化知识

- 非结构化金融知识通过 RAG 检索；
- 个人账户、收支、预算、持仓和交易必须通过确定性数据库工具查询；
- 混合问题由 LangGraph 同时编排财务工具和知识检索；
- 模型不应直接生成 SQL，也不应自行修改财务数据；
- 涉及写操作时，后续应加入显式确认或 Human-in-the-loop。

### 10.3 会话持久化

最终计划同时保留：

- 产品会话表：`conversations`、`messages`、`message_citations`、`agent_runs`；
- LangGraph PostgreSQL Checkpoint：保存图执行状态。

两者职责不同，不能互相替代。产品历史对话必须可查询、分页和展示，Checkpoint 用于恢复
Agent 执行状态。

## 11. 原阶段二开始前确认事项（历史快照）

不要直接开始编码，先与用户确认以下事项：

1. **阶段二范围**  
   原计划阶段二是“个人财务数据基础”，当前分支名却是
   `feature/phase-2-knowledge-rag`。需确认优先顺序。

2. **模型与 Embedding 供应商**  
   需确定使用 OpenAI 兼容 API、其他云模型还是本地模型，以及密钥注入方式。

3. **Embedding 维数**  
   确认模型后才能固定 `Vector(dimensions)` 并创建 HNSW/IVFFlat 索引。

4. **对象存储**  
   确认本地开发采用 MinIO、文件系统适配器，还是直接使用云端 S3 兼容服务。

5. **异步任务**  
   确认采用 Celery，或优先使用更轻量的任务队列。不能仅用 FastAPI
   `BackgroundTasks` 承担企业级文档入库。

6. **知识库可见范围**  
   当前需求倾向管理员维护共享知识库、普通用户只问答；需确认是否允许用户私有知识库。

7. **前端交付顺序**  
   确认先完成后端 API，再开发 Vue 3，还是按纵向功能切片同步推进。

## 12. 原阶段二开发顺序建议（历史快照）

如果继续遵循原始方案，建议先做“个人财务数据基础”：

1. 财务 Repository 和 Pydantic Schema；
2. 账户、收支、预算、持仓和投资交易 Service/API；
3. 每个请求设置 RLS tenant context，并继续显式过滤 `user_id`；
4. CSV/XLSX 导入、校验、幂等和错误报告；
5. 月度收支、余额、预算和持仓聚合；
6. 权限、跨用户隔离、金额精度和日期边界测试；
7. 再进入知识库管理和 LangGraph RAG。

如果用户明确决定先做知识库与 RAG，则建议纵向切片：

1. 确认模型、Embedding、对象存储和任务队列；
2. 实现管理员项目/知识库 CRUD 与 RBAC；
3. 实现文档上传、解析、版本和异步任务；
4. 实现分块、Embedding、pgvector 索引和检索；
5. 先完成一个带结构化引用的非流式问答闭环；
6. 再加入 LangGraph、SSE、Checkpoint、历史会话和 Vue 3；
7. 最后做混合检索、Reranker、缓存、评测和可观测性。

每一个纵向切片都应同时包含：

- API Schema；
- Service；
- Repository/Provider；
- 权限和租户隔离；
- Alembic 迁移；
- 单元/集成测试；
- README 更新；
- Docker 环境验证。

## 13. 阶段一结束时的接手提示词（历史快照）

可将以下内容直接发给新的 Codex 会话：

```text
请接手 E:\agent_aurum 项目。先完整阅读：
1. aurum-agent-phase-1-handoff.md
2. README.md
3. aurum-agent-initial-design.md

阶段一稳定基线提交为：
933390a872590b47e6e10af7c1bf23b564847bf0

当前分支应为 feature/phase-2-knowledge-rag。开始任何修改前，请先只读检查 Git
分支、HEAD、工作区、Docker 服务和测试状态。不要操作 E:\personal_project_1，
不要恢复旧 src/aurum_agent 目录，也不要默认第二阶段已经确定。

请先和我确认：第二阶段优先开发个人财务数据基础，还是知识库与 LangGraph RAG。
未经确认不要开始大规模开发。
```

## 14. 参考文档

- `README.md`：当前代码的运行与开发说明；
- `aurum-agent-initial-design.md`：总体方案和阶段清单；
- `aurum-agent-architecture.md`：整体架构图与说明；
- `aurum-agent-deployment-guide.md`：部署上线流程；
- `pyproject.toml`：Python 依赖和质量工具配置；
- `compose.yaml`：本地容器拓扑；
- `migrations/versions/`：数据库真实演进记录。

交接时应优先相信当前代码、迁移、测试和本文件中的实时核验结果；旧方案文档描述的是目标状态，
其中部分组件尚未实现。
