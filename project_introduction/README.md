# Aurum Agent

Aurum Agent 是面向个人财务开支管理和投资理财分析的智能应用。当前产品由统一用户身份、财务
数据、长期记忆、会话和财务领域 Agent 组成，不再包含个人知识库、文档上传或 RAG 检索链路。

## 当前能力

- 注册、登录、个人资料、偏好和密码管理；
- 账户、流水、预算、持仓、行情与确定性财务指标查询；
- 有界只读工具调用、财务分析计划、回答深度协议和风险守门；
- 用户主动保存的长期目标、偏好与约束记忆；
- PostgreSQL RLS 与 Repository 显式所有者条件共同隔离个人数据；
- LangGraph Checkpoint、SSE、运行审计、配额和财务证据展示。

通用财务概念由模型按安全边界回答；当前余额、流水、预算、持仓和行情等个人事实必须来自本轮
只读财务工具。长期记忆只提供个性化背景，不能代替实时财务事实。

## 专项文档

- [财务领域化升级技术方案](./aurum-agent-financial-domain-upgrade-plan-2026-08-16.md)
- [P7.1 计划与回答协议验收报告](./aurum-agent-phase-7-p7.1-acceptance.md)
- [长期记忆开发计划](./aurum-agent-memory-development-plan-2026-08-13.md)
- [生产发布与回滚手册](../deploy/release-runbook.md)

旧架构、阶段交接和 P3–P6 验收文档保留为历史记录，其中出现的管理员、Agent 项目、知识库、
文档摄取、MinIO、Celery、Reranker 和引用均不代表当前实现。

## 当前问答链路

```text
START
  ↓
run_capability_agent
  ↓
validate_answer
  ↓
END
```

Agent 仅注册三类能力：只读财务工具、长期记忆检索和无需个人数据的直接回答。模型不能执行任意
SQL、写入财务数据或自行指定用户 ID。复杂问题会先生成受约束的财务分析计划，再按计划调用能力；
简单事实问题走快速路径。

## 数据库升级

迁移 `20260816_0023_remove_personal_knowledge.py` 会删除 `chat.message_citations`，并级联删除
整个 `rag` schema。该迁移不可逆；如需保留旧文档数据，必须在升级前完成独立归档。

```powershell
alembic upgrade head
aurum-agent grant-app-role
```

## 本地启动

要求 Docker Desktop、Python 3.12 和 Node.js 24。

```powershell
.\scripts\generate-dev-env.ps1
docker compose up --build -d
docker compose ps
```

常用地址：

- OpenAPI：`http://127.0.0.1:8010/docs`
- 前端：`http://127.0.0.1:4173`
- 存活检查：`http://127.0.0.1:8010/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8010/api/v1/health/ready`

前端开发：

```powershell
Set-Location web
npm install
Copy-Item .env.example .env
npm run dev
```

## 本地验证

```powershell
.venv\Scripts\python.exe -m pytest tests/unit -q
.venv\Scripts\python.exe -m ruff check app migrations scripts tests
.venv\Scripts\python.exe -m alembic check
docker compose config --quiet

Set-Location web
npm run check
npm run build
```

## 项目结构

```text
agent_aurum/
├── app/
│   ├── api/          # FastAPI 路由、依赖和请求响应模型
│   ├── agents/       # LangGraph、财务计划、策略和工具
│   ├── finance/      # 财务导入、校验和确定性计算
│   ├── memory/       # 长期记忆策略与检索上下文
│   ├── providers/    # 模型、Embedding、缓存和安全存储适配层
│   ├── db/           # SQLAlchemy 模型、Repository 和租户上下文
│   └── services/     # 应用用例与事务编排
├── web/              # Vue 3、TypeScript、Vite 和 Ant Design Vue
├── migrations/       # Alembic 数据库迁移
├── tests/            # 单元、集成、契约和端到端测试
├── evals/            # 财务与长期记忆回归数据集
├── scripts/
└── deploy/
```

## 安全边界

个人数据查询必须先设置事务级用户上下文：

```python
await set_tenant_context(session, current_user.id)
```

Repository 查询仍需显式包含 `owner_user_id` 或 `user_id`；RLS 是第二道防线，不能替代应用层
所有权校验。Refresh Token 只通过 HttpOnly Cookie 下发，日志和指标不得记录用户正文或敏感值。
