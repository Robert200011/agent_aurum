# Aurum Agent 开发交接文档（2026-07-27）

> 交接日期：**2026-07-27**  
> 项目路径：`E:\agent_aurum`  
> 工作分支：`phase-3-knowledge-base-2`
> 当前开发阶段：**阶段三：知识库管理**  
> 当前实际进度：**阶段三第 1～6 步功能、真实 DashScope Key 外部冒烟和管理员浏览器核心验收已完成；待最终质量门禁、整理提交和分支合并。**

## 0. 后续整改补充（2026-07-28）

后端审计报告列出的 10 项代码整改现已全部完成。第 4 项 Outbox dispatcher
已修复 Celery Worker 重复任务跨事件循环复用 asyncpg 连接的问题：每个 Worker
子进程使用稳定的进程级事件循环，并在 fork 与进程退出时重置或释放数据库资源。

容器复验已完成同一子进程连续 5 次 Beat 扫描和 1 条真实 Outbox 自动发布，
未再出现 `Event loop is closed` 或跨循环 Future 异常。扫描日志现包含领取量、
发布量、发布失败量、耗尽量、积压量、失败总数和最长等待时间。

真实管理员 `API → MinIO → Document/Version/Job/Outbox` 上传冒烟已经通过；临时管理员
与验收数据已清理，既有管理员账号没有被修改。Worker/Beat 心跳已接入 Redis 和
`/api/v1/health/ready`：心跳过期时 readiness 返回非 200，容器复验时数据库、Redis、
MinIO 和 ingestion Worker 均为 ready。

### 0.1 阶段三第 4 步入库闭环（2026-07-28）

本轮已完成：

- Markdown/TXT 的 UTF-8 安全解析、NFKC/换行/空白规范化和 Markdown 章节路径；
- 基于规范化文本字符偏移的确定性多语言切块、重叠窗口、Chunk 数量上限和内容哈希；
- 同知识库、同 Embedding 模型/维度范围内复用已发布 Chunk 向量；
- DashScope `text-embedding-v4` 批量适配器、超时/限流/响应维度校验和可重试错误分类；
- 1024 维 pgvector 写入、cosine 检索及 HNSW 索引迁移 `20260728_0007`；
- 带租约的 Worker 流水线、解析产物分离存储、进度、失败摘要、有限重试和幂等消费；
- `DocumentVersion`、Chunk、向量及 `Document.current_published_version_id` 的事务性原子发布；
- 使用真实 PostgreSQL/pgvector 和固定假向量完成端到端集成验收；
- PDF 按页受限提取并记录 `page_number`，加密文件、超页数和无可提取文本文件安全失败；
- DOCX 使用禁用 DTD、实体和外部引用的 OpenXML 解析，保留标题章节路径与表格行文本；
- CSV 使用 UTF-8 严格解析并记录物理行范围，XLSX 只读取缓存单元格值并记录工作表和行范围；
- 分块器按 PDF 页和 XLSX 工作表建立硬边界，防止 Chunk 跨来源分区后丢失引用精度；
- 增加提取字符数、表格列数、工作表数和单元格字符数限制，并接入 Compose 环境配置。

### 0.2 阶段三第 5 步检索、进度与人工重试 API（2026-07-28）

本轮已完成：

- `POST /api/v1/admin/knowledge-bases/{knowledge_base_id}/retrieve`：对查询文本使用
  DashScope query 类型 Embedding，在单个已发布知识库中执行 pgvector cosine Dense 检索；
- 检索层强制过滤已发布知识库、有效项目作用域、当前已发布文档版本、启用且未删除文档；
- 返回 Chunk 正文、文档标题、页码、章节、工作表、行范围、字符偏移、分数和检索来源；
- 成功检索写入 `RetrievalLog`，记录操作者、查询、结果数、耗时、最高分和模型信息；
- `GET /api/v1/admin/documents/{document_id}/ingestion-jobs`：按文档返回任务历史；
- 任务详情补充自动/人工重试次数、错误详情、开始时间和完成时间；
- `POST /api/v1/admin/ingestion-jobs/{job_id}/retry`：仅允许管理员重试失败的最新版本，
  原子重置 Job/Version 并重新入队 Outbox；
- 保留 `retry-dispatch` 处理单纯的消息投递失败，避免与流水线执行失败混用；
- 人工重试默认最多 5 次，迁移 `20260728_0008` 增加数据库持久化计数与非负约束；
- 真实 PostgreSQL/pgvector 临时验收覆盖检索、日志、任务历史、重试、重复重试拒绝，
  验收数据已清理。

### 0.3 阶段三第 6 步管理员知识库前端（2026-07-28）

本轮已完成：

- 增加管理员专属 `/admin/projects` 和 `/admin/knowledge-bases` 路由、侧边菜单及前端
  `adminOnly` 路由守卫；普通用户不显示入口，后端 RBAC 仍是最终权限边界；
- 项目创建、编辑、启停、软删除，以及唯一有效知识库作用域的操作说明和错误反馈；
- 知识库创建、编辑、发布、终止性停用、软删除、项目绑定与安全解绑；
- PDF、DOCX、Markdown、TXT、CSV、XLSX 文档和新版本上传，单次上传使用稳定的
  `Idempotency-Key`，失败后在同一弹窗重试不会产生新的业务请求键；
- 文档列表、内容哈希、启停/删除、不可变版本历史、版本元数据和预签名源文件下载；
- 入库任务自动轮询、进度、自动/人工重试计数、失败摘要、失败任务重试，以及单纯
  Outbox 投递失败的独立重新投递入口；
- 已发布知识库的 Dense 检索测试，可配置返回条数和最低分数，并展示 Chunk 正文、
  相似度、文档标题、页码、章节、工作表或行范围；
- 桌面与移动端响应式布局，以及统一的加载、空状态、业务错误和危险操作确认。

### 0.4 真实 DashScope Key 与管理员浏览器验收（2026-07-29）

本轮已完成：

- 运行时已配置真实 DashScope Key；任何密钥值均未写入仓库或项目文档；
- 管理员通过浏览器创建项目和知识库，完成知识库发布、停用等生命周期操作验证；
- 通过浏览器上传 TXT 文档及新版本，Worker 入库任务完成至 100%，当前版本原子发布，
  旧版本正确标记为已被替代；
- 文档 Chunk 使用 DashScope `text-embedding-v4` 生成 1024 维向量并写入 pgvector；
- 查询“本次验收编号是什么？”时，查询文本再次通过真实 DashScope API 生成向量，
  Dense/cosine 检索命中 `agent测试用.txt`，返回 `AURUM-RAG-0729`；
- 该次检索返回 1 个结果，最高分 `0.6278`、耗时 `313 ms`，模型为
  `text-embedding-v4`，对应 `RetrievalLog` 已成功持久化；
- 修复 Axios 全局 JSON `Content-Type` 导致 `FormData` 上传被序列化为 JSON、FastAPI
  返回 422 的问题，并增强前端请求校验错误展示；
- 修复 Dense 检索成功后写入 `rag.retrieval_logs` 时缺少事务级租户上下文、触发
  PostgreSQL RLS 拒绝并返回 500 的问题；检索服务现在会在访问租户表前设置当前管理员
  用户上下文，RLS 写入及回滚式无残留验证均通过；
- 当前数据库位于 `20260728_0008 (head)`；readiness 确认数据库、Redis、对象存储和
  ingestion Worker 全部 ready。

当前收尾事项：

- 执行阶段三最终后端、前端、迁移和 Compose 质量门禁；
- 复核 Git 变更范围，确保 `.env`、本地缓存和临时验收脚本未被提交；
- 提交并合并 `phase-3-knowledge-base-2`，随后再进入阶段四基础 RAG 问答。

最近验证结果：

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 通过，95 个源文件 |
| 当前本地 Pytest | 39 项通过，5 项集成测试按环境开关跳过 |
| 四类新增格式解析样本 | PDF、DOCX、CSV、XLSX 全部通过 |
| 入库流水线 PostgreSQL/pgvector 临时验收 | 四类新增格式全部发布成功，来源定位落库正确，验收数据已清理 |
| 第 5 步 PostgreSQL/pgvector 临时验收 | 检索、日志、进度与人工重试全部通过，验收数据已清理 |
| 管理员知识库前端 | TypeScript、ESLint、10 项既有前端测试和 Vite 生产构建通过 |
| 真实 DashScope Key 入库与检索 | `text-embedding-v4` 文档/查询向量生成、pgvector 命中和来源展示通过 |
| 检索日志 RLS 修复 | Ruff 通过，RAG 针对性测试 10 项通过，真实 RLS 写入与回滚验证通过 |
| Alembic | 已升级至 `20260728_0008`，downgrade/upgrade 与 metadata check 通过 |
| Docker | API、Worker、Beat 正常；`/api/v1/health/ready` 返回 ready，四项依赖均为 true |

以下原始交接内容保留为 2026-07-27 时点记录。

## 1. 当前进度结论

项目已完成：

- **阶段一**：架构、安全底座、认证、RBAC、审计、PostgreSQL / pgvector / Redis / Alembic / Docker Compose；
- **阶段二**：个人财务数据、RLS、导入与财务前端基础能力；
- **阶段三第 1 步**：RAG 数据模型、固定 1024 维向量配置、迁移、Provider 契约、MinIO / Celery 基础设施；
- **阶段三第 2 步**：管理员项目、知识库、显式项目绑定/共享、审计与 RBAC；
- **阶段三第 3 步**：安全上传、文档元数据、不可变版本、S3/MinIO Provider、`IngestionJob`、Outbox、文档 API 的主要代码实现。

但阶段三第 3 步尚不能视为“生产可靠完成”。后端审查发现迁移可复现性、MinIO 应用账户、Outbox 自动分发、上传幂等并发恢复等问题。它们会影响新环境部署和真实入库链路，必须先整改。

因此，当前工作处于：

```text
阶段三 / 第 3 步：实现完成 → 审查发现缺陷 → 整改与真实链路验证待进行
```

而不是：

```text
阶段三 / 第 4 步：解析、分块、Embedding、向量写入
```

## 2. 已实现能力

### 2.1 阶段三第 1 步：RAG 基础设施

主要文件：

- `app/db/models/rag.py`
- `migrations/versions/20260725_0004_rag_versioned_ingestion.py`
- `app/rag/constants.py`
- `app/config.py`
- `app/providers/object_storage.py`
- `app/providers/model_provider.py`
- `app/providers/vector_store.py`
- `app/workers/celery_app.py`
- `compose.yaml`

已实现：

- `AgentProject`、`KnowledgeBase`、`ProjectKnowledgeBase`；
- `Document`、不可变 `DocumentVersion`、`DocumentChunk`、`IngestionJob`；
- 知识库固定 DashScope `text-embedding-v4`、固定 1024 向量维度、cosine 距离度量；
- 文档版本、任务租约、重试、状态、错误摘要等基础字段；
- PostgreSQL / pgvector、Redis、MinIO、Celery Worker 的 Compose 基础定义；
- 对象存储、Embedding、Vector Store Provider 契约；
- 文件大小、ZIP 展开大小、压缩比、Chunk 参数等安全配置。

### 2.2 阶段三第 2 步：管理员项目与知识库 CRUD

主要文件：

- `app/api/schemas/rag.py`
- `app/db/repositories/rag.py`
- `app/services/rag.py`
- `app/api/projects.py`
- `app/api/knowledge_bases.py`
- `app/api/dependencies.py`
- `app/api/router.py`

已实现：

- 管理员项目 CRUD、禁用与软删除；
- 知识库 CRUD、发布、停用与软删除；
- 首次创建知识库时原子创建一个项目 binding；
- 额外项目 binding 代表显式共享；
- 禁止移除最后一个 binding；
- 管理员 RBAC：普通用户及要求修改初始密码的管理员均被拒绝；
- 审计事件、稳定的 `ConflictError` / `NotFoundError` / `BusinessRuleError` 映射。

### 2.3 阶段三第 3 步：上传、版本与任务创建骨架

主要文件：

- `app/rag/upload_validation.py`
- `app/providers/s3_object_storage.py`
- `app/api/documents.py`
- `app/services/rag.py`
- `app/db/models/rag.py`
- `migrations/versions/20260726_0005_document_upload_outbox.py`
- `app/workers/ingestion.py`
- `tests/unit/test_document_upload_validation.py`

已实现：

- 支持 PDF、DOCX、Markdown、TXT、CSV、XLSX；
- 有界读取、SHA-256、危险文件名拒绝、UTF-8 校验；
- DOCX/XLSX ZIP64、多磁盘、加密、目录穿越、超大成员、展开大小与压缩比防护；
- 服务端生成对象键，不将客户端文件名拼入对象路径；
- S3/MinIO `put/get/head/delete/presigned-url` 适配器；
- 文档、不可变版本、入库任务与 Outbox 模型；
- 管理员文档上传、追加版本、文档/版本/任务查询、禁用、软删除 API；
- 强制 `Idempotency-Key` API 契约；
- 上传后任务初始状态为 `awaiting_pipeline`；
- Celery Outbox dispatcher 与最小 Job 占位入口。

## 3. 已执行的验证

已完成过的代码级验证：

```powershell
python -m ruff check app tests migrations
python -m mypy app
python -m pytest
python -m alembic check
docker compose config --quiet
git diff --check
```

最近一次代码级结果：

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 通过，82 个源文件 |
| Pytest | 80 项通过 |
| Alembic metadata check | 通过；存在已知 `documents` / `document_versions` 循环 FK 排序警告 |
| Docker Compose 配置 | 通过 |
| Git diff whitespace | 通过 |

数据库曾实际位于：

```text
20260726_0005 (head)
```

> 注意：`alembic check` 不代表空数据库能完整升级。审查已经确认历史 `0001` 迁移依赖当前 ORM 元数据，空数据库升级链目前不可安全视为已验证。

## 4. 阶段三第 3 步整改清单（下一步必须做）

完整问题说明见：

- [`aurum-agent-backend-audit-report.md`](./aurum-agent-backend-audit-report.md)

### P0：先修复

#### 4.1 固化历史迁移，保证空数据库可完整升级

问题文件：

- `migrations/versions/20260723_0001_phase_one_foundation.py`

`0001` 使用当前 `Base.metadata.create_all()`，会使当前模型字段提前出现在空数据库，随后 `0003`、`0004`、`0005` 重复添加字段/表而失败。

整改目标：

- 把 `0001` 改成历史固定 DDL 或仅含阶段一模型的固定 Metadata；
- 不再导入当前 `Base.metadata`；
- 在新建、隔离的 PostgreSQL 数据库中执行：

```powershell
python -m alembic upgrade head
python -m alembic current
```

#### 4.2 创建 MinIO 应用账户和最小权限策略

问题文件：

- `compose.yaml`
- `scripts/generate-dev-env.ps1`
- `app/providers/s3_object_storage.py`

当前 MinIO 初始化仅创建 bucket 并关闭匿名访问，没有创建 API / Worker 使用的 `AURUM_OBJECT_STORAGE_ACCESS_KEY` 对应账户或 service account。

整改目标：

- 使用 `minio-init` 创建应用账户或 service account；
- 为其绑定目标 bucket 的最小对象读写权限；
- API / Worker 始终使用应用凭据，不使用 root 凭据；
- 增加基于应用账户的 readiness 验证。

#### 4.3 启动可靠的 Outbox dispatcher

问题文件：

- `app/workers/ingestion.py`
- `app/workers/celery_app.py`
- `compose.yaml`

目前已创建 `OutboxEvent` 和 dispatcher task，但没有 Beat、独立调度进程或上传后的触发路径。事件会永久保持未发布状态。

整改目标：

- 新增 Celery Beat 或独立 dispatcher 服务；
- 周期扫描待发布 Outbox；
- 上传后可额外触发一次 dispatcher 以降低延迟；
- 正确性依赖持久 Outbox + 周期扫描，而非单次请求触发。

### P1：紧接 P0 修复

#### 4.4 修复上传幂等预留的并发与恢复问题

当前唯一幂等键在 `IngestionJob`，但 Job 在 Document / DocumentVersion 预留和对象写入之后才创建。

整改目标：

- 新增上传请求表，例如 `DocumentUploadRequest`；
- 在预留阶段即对 `idempotency_key` 建数据库唯一约束；
- 持久化请求目标、内容哈希、元数据哈希、关联 Document / Version、状态和安全错误；
- 同键重放返回原请求状态；同键不同内容返回 409；
- 失败后可恢复或清理，而不产生孤儿 `uploading` 版本。

#### 4.5 为 Outbox 增加退避、失败状态和人工重试

整改目标：

- `.delay()` 失败时写入 `last_error`；
- 使用有上限的指数退避更新 `available_at`；
- 限制最大尝试次数，进入 dead-letter / failed 状态；
- 提供管理重试能力与指标；
- 避免 Redis 不可用时热重试挤占新事件。

#### 4.6 修复 `0004` downgrade 约束名

问题文件：

- `migrations/versions/20260725_0004_rag_versioned_ingestion.py`

整改目标：

- 使用真实约束名删除 `document_versions.embedding_dimensions` 相关检查约束；
- 在隔离数据库验证：

```powershell
python -m alembic upgrade head
python -m alembic downgrade 20260724_0003
python -m alembic upgrade head
```

#### 4.7 修复项目删除后的有效 binding / 发布规则

整改目标：

- `publish_knowledge_base` 必须确认至少一个 binding 对应 active、未删除 Project；
- 删除项目时禁止破坏唯一有效 binding，或明确将 binding 失效；
- 维护“知识库至少有一个有效项目作用域”的不变量。

### P2：进入阶段四前纳入数据完整性设计

- 锁定或数据库保护“解绑后至少保留一个 binding”；
- 保障 Document、DocumentVersion、IngestionJob、DocumentChunk 的同父 / 同知识库关联；
- 修复 Compose 可配置队列名与固定 `--queues=aurum-ingestion` 的漂移；
- 增加数据库、Redis、MinIO 应用权限的 readiness；
- 为未来浏览器预签名下载 URL 分离内部 MinIO endpoint 与外部可访问 endpoint。

## 5. 整改完成后的真实验收顺序

1. Docker Desktop 与 PostgreSQL / MinIO / Redis 恢复可访问；
2. 使用干净 PostgreSQL 数据库验证完整迁移链；
3. 验证 downgrade / upgrade round-trip；
4. 确认 MinIO 应用账户存在且只能访问目标 bucket；
5. 通过正常流程使管理员完成初始密码修改；
6. 创建项目和知识库；
7. 使用管理员 JWT 调用 multipart 上传接口；
8. 验证以下链路：

```text
API 校验
→ MinIO put/head
→ Document
→ DocumentVersion
→ IngestionJob
→ OutboxEvent
→ Dispatcher
→ Celery Job
```

9. 验证重复请求、并发请求、存储失败、投递失败、重试和软删除路径；
10. 仅在以上完成后开始阶段三第 4 步。

## 6. 后续正式开发步骤

### 下一步：阶段三第 3 步整改与验收

当前最准确的下一步不是解析或 Embedding，而是：

```text
阶段三第 3 步整改：迁移可靠性、MinIO 权限、Outbox 调度、上传幂等、作用域完整性
```

### 整改完成后：阶段三第 4 步

进入 Worker 入库流水线：

1. PDF、DOCX、Markdown、TXT、CSV、XLSX 的受限解析；
2. 来源定位：页码、章节、工作表、行范围、字符偏移；
3. Unicode / 空白清洗和确定性分块；
4. 同知识库/模型范围内的内容哈希去重；
5. DashScope `text-embedding-v4` 批量 Embedding；
6. pgvector Chunk 写入和检索烟雾测试；
7. 原子发布 `DocumentVersion` 并更新 `Document.current_published_version_id`；
8. 临时错误退避、不可恢复错误隔离、任务进度和失败摘要。

### 阶段三后续步骤

- **第 5 步**：检索、进度与重试 API；
- **第 6 步**：管理员知识库前端、上传界面、任务状态、版本历史与检索测试面板；
- 第 1～6 步功能完成后，先做管理员浏览器验收和真实 Key 外部冒烟，再进入
  LangGraph、RAG 问答、SSE 和财务 Agent。

## 7. 本地环境与依赖注意事项

- `.env` 中的真实密码、JWT 密钥、DashScope Key、MinIO root / 应用凭据不得提交或贴入文档。
- 本机 Anaconda base 环境存在：

```text
aiobotocore 2.19.0 requires botocore<1.36.4,>=1.36.0,
but botocore 1.43.56 is installed
```

Aurum 当前不直接使用 `aiobotocore`，但该冲突说明 base 环境不干净。后续建议创建独立虚拟环境，再执行依赖安装、测试、迁移与本地运行。

- Docker / MinIO 运行状态曾发生变化；重新进行端到端验收前先运行：

```powershell
docker compose ps --all
docker compose config --quiet
python -m alembic current
```

## 8. 关键文档索引

- [当前后端审查报告（2026-07-27）](./aurum-agent-backend-audit-report.md)
- [总体实施路线](./aurum-agent-initial-design.md)
- [系统架构](./aurum-agent-architecture.md)
- [部署指南](./aurum-agent-deployment-guide.md)
- [旧交接文档（2026-07-24）](./aurum-agent-current-handoff.md)
