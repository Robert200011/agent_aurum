# Aurum Agent

Aurum Agent 是面向个人财务、投资数据和个人知识问答的智能应用。当前架构不再包含管理员角色、管理员页面或 Agent 项目；所有注册用户使用同一种身份，并自行维护仅属于自己的知识库。

## 当前产品模型

- 用户可以注册、登录、维护个人资料和密码。
- 每个用户可以创建多个个人知识库，上传、更新、停用和删除自己的文档。
- 知识库默认处于 `active` 状态，可通过 `search_enabled` 独立控制是否参与问答检索。
- 会话只绑定用户，不绑定项目、知识库或其它固定知识范围。
- 提问先经过确定性路由，再按需调用个人知识检索或只读财务工具。
- PostgreSQL RLS 与 Repository 显式所有者条件共同隔离个人知识、会话和财务数据。

旧的阶段交接与验收文档保留为历史记录，其中出现的管理员、Agent 项目和项目—知识库绑定均不再代表当前实现。

## 问答路由

当前路由将问题分为五类：

| 路由 | 触发条件 | 执行链路 |
| --- | --- | --- |
| `direct` | 普通知识或通用建议，不需要私有数据 | 直接生成回答 |
| `knowledge` | 明确提到知识库、上传文档、我的资料等 | 检索当前用户所有启用的个人知识库 |
| `finance` | 明确请求个人财务、预算、账户、交易或持仓数据 | 调用白名单只读财务工具 |
| `mixed` | 同时明确请求个人知识和财务事实 | 个人知识检索与财务工具组合 |
| `clarify` | 时间、证券代码等关键条件缺失 | 返回澄清问题，不执行数据查询 |

“如何制定预算”一类通用问题不会自动检索知识库；“根据我的知识库制定预算”才会进入知识或混合链路。这样可以减少无意义检索、错误引用和额外模型成本。

## 个人知识库生命周期

知识库只保留两个状态：

- `active`：允许维护文档；是否进入问答检索由 `search_enabled` 决定。
- `disabled`：不允许上传，也不会进入问答检索。

文档上传后仍通过异步摄取流水线完成解析、分块、Embedding、Hybrid Retrieval 索引和不可变版本发布。用户无需执行额外的“发布知识库”步骤。

主要接口位于 `/api/v1`：

```text
/knowledge-bases
/knowledge-bases/{knowledge_base_id}
/knowledge-bases/{knowledge_base_id}/documents
/knowledge-bases/{knowledge_base_id}/search-preview
/documents/{document_id}
/documents/{document_id}/versions
/document-versions/{document_version_id}/download-url
/ingestion-jobs/{job_id}
/conversations
/conversations/{conversation_id}/messages
```

## 数据库迁移

迁移 `20260808_0013_personal_knowledge.py` 执行以下转换：

1. 将原知识库的 `created_by` 回填为 `owner_user_id`，保留知识库、文档、版本、切片和对象存储键。
2. 将原 `draft`、`published` 状态统一转换为 `active`，新增 `search_enabled=true`。
3. 删除 Agent 项目、项目—知识库绑定以及会话上的 `project_id`；历史会话、消息和引用继续保留。
4. 删除用户的 `role` 和 `must_change_password` 字段；原管理员账号成为普通用户账号。
5. 为个人知识库启用强制 RLS，并建立用户内不区分大小写的知识库名称唯一索引。

升级前应先备份数据库。迁移不会移动既有对象存储文件，新上传文件使用 `users/{owner_user_id}/knowledge-bases/...` 命名空间。

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

生成脚本创建本机 JWT、数据库和对象存储密钥，不再生成初始管理员账号或管理员密码。应用启动后直接通过注册页面创建用户。

前端开发：

```powershell
Set-Location web
npm install
Copy-Item .env.example .env
npm run dev
```

常用地址：

- OpenAPI：`http://127.0.0.1:8010/docs`
- 前端：`http://127.0.0.1:4173`
- 存活检查：`http://127.0.0.1:8010/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8010/api/v1/health/ready`

## 本地验证

```powershell
.venv\Scripts\python.exe -m pytest tests/unit -q
.venv\Scripts\python.exe -m ruff check app migrations tests
.venv\Scripts\python.exe -m alembic check
docker compose config --quiet

Set-Location web
npm run check
npm run build
```

集成测试需要显式配置 `AURUM_RAG_INTEGRATION_DATABASE_URL`，否则会安全跳过。

## 项目结构

```text
agent_aurum/
├── app/
│   ├── api/                 # FastAPI 路由、依赖和请求响应模型
│   ├── agents/              # LangGraph、路由策略和财务工具
│   ├── rag/                 # 文档解析、切分、检索、重排和引用
│   ├── finance/             # 财务导入、校验和确定性计算
│   ├── providers/           # 模型、存储、向量和缓存适配层
│   ├── db/                  # SQLAlchemy 模型、Repository 和租户上下文
│   ├── services/            # 应用用例与事务编排
│   └── workers/             # 异步摄取任务
├── web/                     # Vue 3、TypeScript、Vite 和 Ant Design Vue
├── migrations/              # Alembic 数据库迁移
├── tests/                   # 单元、集成、契约、端到端和评测测试
├── evals/                   # 路由与 Agent 回归数据集
├── scripts/
└── deploy/
```

## 安全边界

个人数据查询必须先设置事务级用户上下文：

```python
await set_tenant_context(session, current_user.id)
```

Repository 查询仍需显式包含 `owner_user_id` 或 `user_id`；RLS 是第二道防线，不能替代应用层所有权校验。Refresh Token 只通过 HttpOnly Cookie 下发，访问令牌不再携带角色声明。
