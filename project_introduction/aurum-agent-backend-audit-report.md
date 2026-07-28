# 后端审查报告：阶段三第 4 步前的缺陷、风险与修复建议

> 审查范围：当前后端框架、FastAPI 路由与服务层、SQLAlchemy 模型与 Alembic 迁移、RAG 上传/Outbox、Celery、S3/MinIO、Docker Compose、运行时配置与依赖。  
> 审查时间：2026-07-27  
> 审查结论：阶段三第 1 至第 3 步的主要代码骨架已经形成，静态检查和单元测试曾通过；但在进入解析、分块、Embedding 和向量发布前，应先修复本报告中的高优先级问题。否则会影响新环境迁移、真实对象上传、异步投递可靠性、上传幂等性和项目作用域完整性。

## 整改进度更新（2026-07-28）

审计结论保持有效，当前按“建议修复顺序”记录实施状态：

| 顺序 | 修复事项 | 当前状态 |
|---:|---|---|
| 1 | 固化历史迁移并验证空库升级 | 已完成初步整改与空库升级验证 |
| 2 | 修复 `0004` downgrade 约束名 | 已完成，并通过 `0006 → 0003 → 0006` 往返验证 |
| 3 | 创建 MinIO 应用账户和最小权限 | 已完成初步整改与应用账户对象探针 |
| 4 | 启动可靠 Outbox dispatcher | 已完成；Worker 子进程复用进程内事件循环，fork/退出时重置或释放数据库资源，并通过连续扫描与真实事件投递复验 |
| 5 | Outbox 退避、失败终态与人工重试 | 已完成；具备持久化安全错误、指数退避、最大尝试、失败终态和管理员重试 API |
| 6 | 上传请求幂等记录和故障恢复 | 已完成；新增 `DocumentUploadRequest`，并通过失败恢复与并发同键测试 |
| 7 | 有效项目 binding / 发布规则 | 已完成；服务层行锁与数据库延迟约束触发器共同维护有效作用域 |
| 8 | Document / Version / Job / Chunk 作用域完整性 | 已完成；使用复合唯一键和复合外键阻止跨父级、跨知识库关联 |
| 9 | Compose 队列名配置漂移 | 已完成；Worker、生产者与 Beat 统一使用 `AURUM_INGESTION_QUEUE_NAME`，并增加非默认队列配置测试 |
| 10 | readiness 与外部下载 endpoint | 已完成；readiness 使用应用账户验证 MinIO 对象权限，下载签名使用独立外部 endpoint |

第 5 至第 8 项的 PostgreSQL 集成测试位于
`tests/integration/test_rag_reliability.py`；第 9、10 项的队列、存储和健康检查测试位于
`tests/unit/test_worker_configuration.py`、`tests/unit/test_s3_object_storage.py`、
`tests/unit/test_system_health.py` 与 `tests/unit/test_document_download.py`。
第 4 项的进程级异步运行时测试位于 `tests/unit/test_worker_async_runtime.py`。
2026-07-28 容器复验中，同一 Worker 子进程连续完成 5 次 Beat 扫描，未再出现
`Event loop is closed` 或 `Future attached to a different loop`；随后真实 Outbox
事件成功发布为 Celery Job，数据库状态更新为 `published`，测试数据已清理。

至此，本报告列出的 10 项代码整改均已完成。阶段三第 4 步正式准入前仍应完成
“真实管理员上传全链路”和“Worker 状态纳入统一健康检查/告警”两项运维验收。

## 一、当前已验证的正常项

- 当前开发数据库已位于 `20260727_0006 (head)`。
- 当前已通过：`ruff`、`mypy`、`pytest`（98 passed，4 个需显式测试数据库的集成测试 skipped）、`alembic check`、`docker compose config --quiet` 与 `git diff --check`。
- RAG 管理路由已注册，文档上传、文档版本、任务状态等 API 契约已进入 OpenAPI。
- API、PostgreSQL、Redis、MinIO 与 Celery Worker 曾成功启动；MinIO 初始化容器也已成功创建 bucket 并关闭匿名访问。
- Celery Beat 已按配置周期扫描 Outbox；扫描日志包含领取、发布、发布失败、耗尽、积压、失败总数和最长等待时间。
- 上传校验、对象键生成、不可变 `DocumentVersion`、`IngestionJob`、`OutboxEvent`、S3/MinIO Provider 与管理员 RBAC 的基础代码已经存在。
- 当前尚未完成真实管理员成功上传冒烟，因为本地唯一管理员仍处于 `must_change_password = true` 状态；这是既有安全策略的正常拦截，而不是代码崩溃。

## 二、严重程度总览

| 等级 | 数量 | 含义 |
|---|---:|---|
| Critical / P0 | 3 | 会阻断全新部署、真实上传或异步入库主链路；应在阶段四前处理。 |
| High / P1 | 5 | 会造成数据孤儿、回滚失败、错误发布或可配置环境失效；应紧随 P0 修复。 |
| Medium / P2 | 4 | 当前路径不一定立即触发，但会降低可靠性、隔离性或后续功能可扩展性。 |
| Environment | 1 | 本地开发环境污染，不直接等于应用代码缺陷。 |

---

## 三、Critical / P0：必须优先修复

### P0-1：历史 Alembic 迁移引用当前 ORM 元数据，空数据库升级不可复现

**位置**

- `migrations/versions/20260723_0001_phase_one_foundation.py:22`
- `migrations/versions/20260723_0001_phase_one_foundation.py:53-58`

**问题**

首个迁移导入当前所有模型后调用：

```python
Base.metadata.create_all(bind=connection, checkfirst=True)
```

`Base.metadata` 会随应用代码演进而改变，并非 20260723 时刻的历史数据库结构。因此全新数据库执行 `0001` 时，会提前创建当前模型所拥有的后续字段、索引、约束和表。

随后迁移链继续执行时会发生重复定义。例如：

- 当前 `FinancialTransaction` 已含 `import_key`，而 `20260724_0003_phase_two_finance_invariants.py` 又会新增该列；
- 当前 `AgentProject` 已含 `deleted_at`，而 `20260725_0004_rag_versioned_ingestion.py` 又会新增该列；
- 当前模型已含 `rag.outbox_events`，而 `20260726_0005_document_upload_outbox.py` 又会创建该表。

**影响**

- 新环境首次部署可能失败；
- CI 临时数据库初始化可能失败；
- 灾难恢复、演示环境和测试环境无法可靠从零构建；
- 当前已有开发数据库因历史上已经逐步升级，未必暴露此问题。

**建议修复**

1. 将 `0001` 改为不可变的历史 DDL 或只代表阶段一结构的独立 `MetaData`；
2. 禁止历史迁移导入当前的 `Base.metadata`；
3. 逐个确认 `0002`、`0003`、`0004`、`0005` 的增量语义与基线不重叠；
4. 增加“空 PostgreSQL 数据库执行 `alembic upgrade head`”的自动化验证。

---

### P0-2：MinIO 未创建 API/Worker 实际使用的应用账号与最小权限

**位置**

- `compose.yaml:18-23`
- `compose.yaml:70-104`
- `scripts/generate-dev-env.ps1`
- `app/providers/s3_object_storage.py:17-35`

**问题**

当前设计区分：

```text
MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
    MinIO 根管理员，用于初始化与维护。

AURUM_OBJECT_STORAGE_ACCESS_KEY / AURUM_OBJECT_STORAGE_SECRET_KEY
    API 与 Worker 的应用访问凭据。
```

但 `minio-init` 目前只创建 bucket 并关闭匿名访问：

```sh
mc mb --ignore-existing ...
mc anonymous set none ...
```

并没有：

- 创建 `AURUM_OBJECT_STORAGE_ACCESS_KEY` 对应的 MinIO 用户或 service account；
- 创建对象读写所需的最小权限策略；
- 将策略绑定至该应用账户。

**影响**

API 通过应用账户调用 S3 `put_object` 时可能被 MinIO 拒绝；健康检查仍可能显示 API、MinIO 均正常，直到首次上传才暴露错误。

**建议修复**

1. 在 `minio-init` 中创建应用用户或 service account；
2. 创建并绑定仅限目标 bucket、仅含所需 `GetObject` / `PutObject` / `DeleteObject` / `HeadObject` 权限的策略；
3. 保持 API/Worker 不使用 root 凭据；
4. 增加基于应用账户的 bucket / 权限 readiness 检查；
5. 为本地与生产分别明确账户生命周期和密钥轮换方案。

---

### P0-3：Outbox 已持久化，但没有任何调度机制真正投递事件

**位置**

- `app/services/rag.py`：创建 `OutboxEvent` 的上传激活流程；
- `app/workers/ingestion.py:17-56`：定义 `dispatch_pending_outbox_events`；
- `app/workers/celery_app.py:16-29`：无 Beat 调度配置；
- `compose.yaml:133-152`：只启动 Celery Worker，没有启动 Celery Beat / Dispatcher 服务。

**问题**

上传流程会创建 `IngestionJob` 和 `OutboxEvent`，这是正确的事务边界。但当前只定义了 dispatcher task，并没有：

- 在上传提交后调用 dispatcher；
- 定期执行 dispatcher；
- 启动 Celery Beat；
- 启动独立 Outbox dispatcher 进程。

**影响**

成功上传后资源可能长期停留在：

```text
DocumentVersion: awaiting_pipeline
IngestionJob:    awaiting_pipeline
OutboxEvent:     unpublished
```

`run_ingestion_job` 不会被投递，后续真正的入库流水线也无法启动。

**建议修复**

1. 以独立 Celery Beat 或独立 dispatcher 服务周期扫描 Outbox；
2. 可在上传提交后额外触发一次 dispatcher 以降低延迟，但不能作为唯一可靠机制；
3. correctness 必须依赖数据库 Outbox + 周期扫描；
4. 增加任务投递、待投递事件数量、投递失败次数和最长等待时间指标。

---

## 四、High / P1：应在阶段四前修复

### P1-1：上传幂等键只在 Job 创建阶段唯一，预留与激活之间会留下孤儿记录

**位置**

- `app/services/rag.py:284-344`
- `app/services/rag.py:346-401`
- `app/services/rag.py:434-504`
- `app/db/models/rag.py:216-247`
- `app/db/repositories/rag.py:164-166`

**问题**

当前流程大致为：

```text
检查 IngestionJob.idempotency_key
→ 提交 Document / DocumentVersion(uploading)
→ 写入并核验对象存储
→ 创建带唯一 idempotency_key 的 IngestionJob
→ 创建 Outbox
```

幂等唯一约束仅位于 `IngestionJob`，而该 Job 在预留版本与对象写入之后才创建。

**失败场景**

- 对象写成功，但 Job / Outbox 激活事务失败；
- 清理逻辑删除对象，但已提交的 `DocumentVersion(uploading)` 仍存在；
- 相同 `Idempotency-Key` 重试时找不到 Job，会创建新的 Document / Version；
- 旧预留版本成为无 Job、无对象或不可恢复状态的孤儿记录。

**建议修复**

引入独立的、在预留阶段便唯一的上传请求记录，例如：

```text
DocumentUploadRequest
- idempotency_key UNIQUE
- target_type / target_id
- content_hash
- metadata_hash
- document_id
- document_version_id
- lifecycle_status
- error_code / error_detail
- created_at / updated_at
```

该记录作为上传操作的幂等锚点：

- 同键同内容返回原请求状态或原结果；
- 同键不同目标/内容/元数据返回 409；
- 失败后可恢复、重试或清理，不重复创建逻辑文档与版本。

---

### P1-2：并发相同幂等键上传会产生额外预留文档/版本

**位置**

- `app/services/rag.py:291-304`
- `app/services/rag.py:328-343`
- `app/services/rag.py:468-503`

**问题与场景**

两个并发请求可能同时查询不到同一个幂等键对应的 Job，并各自：

1. 创建并提交一个 `Document` / `DocumentVersion`；
2. 写入一个对象；
3. 尝试创建 Job；
4. 只有其中一个请求因 `IngestionJob.idempotency_key` 唯一约束获胜；
5. 失败请求删除对象，但其预留 Document / Version 仍然存在。

**影响**

- 幂等操作产生多份数据库记录；
- `uploading` 状态积累；
- 后续列表、审计、清理和版本编号均可能被污染。

**建议修复**

与 P1-1 一并处理：在首次预留前用唯一上传请求记录、数据库锁或事务级冲突处理串行化同一幂等键。

---

### P1-3：Outbox 投递失败没有持久化退避、错误摘要或终态

**位置**

- `app/workers/ingestion.py:34-48`
- `app/db/repositories/rag.py:187-207`
- `app/db/models/rag.py:250-276`

**问题**

`run_ingestion_job.delay()` 失败时仅记录日志并跳过；数据库不会更新：

- `last_error`；
- `available_at`；
- 退避时间；
- 最大尝试次数；
- 终态 / dead-letter 状态。

**影响**

当 Redis / Celery 不可用时，同一 Outbox 事件在租约过期后会立即再次被领取，形成热重试。批次容量有限时，还可能挤占新事件。

**建议修复**

- 持久化安全错误摘要；
- 使用有上限的指数退避更新 `available_at`；
- 定义最大投递次数和 `failed` / dead-letter 状态；
- 增加管理员可见的重试接口；
- 对失败、积压和超时事件提供指标与告警。

---

### P1-4：`0004` downgrade 约束名错误，可能阻断回滚

**位置**

- `migrations/versions/20260725_0004_rag_versioned_ingestion.py:274-279`
- `migrations/versions/20260725_0004_rag_versioned_ingestion.py:540-551`
- `app/db/base.py:17-23`

**问题**

升级创建 `document_versions.embedding_dimensions` 的检查约束时，SQLAlchemy 命名约定会生成实际数据库约束名。降级逻辑尝试删除的名称与真实名称不一致，导致真实检查约束可能保留。

随后的 `DROP COLUMN embedding_dimensions` 会因该约束仍依赖列而被 PostgreSQL 拒绝。

**建议修复**

1. 使用真实的命名约定生成名，或在 downgrade 使用明确、正确的约束名；
2. 在 PostgreSQL 上执行完整 round-trip：

```powershell
python -m alembic upgrade head
python -m alembic downgrade 20260724_0003
python -m alembic upgrade head
```

3. 在干净数据库和已有升级数据库上都验证。

---

### P1-5：软删除唯一项目后，知识库仍可能被发布

**位置**

- `app/services/rag.py`：项目软删除；
- `app/services/rag.py`：`publish_knowledge_base`；
- `app/db/models/rag.py:90-106`：`ProjectKnowledgeBase`。

**问题**

项目删除仅将 Project 标记为 disabled / deleted，不会删除或失效其 binding。知识库发布只检查“是否有任意 binding”，不验证 binding 对应项目是否 active、未删除。

**错误场景**

```text
创建项目 A
→ 创建只绑定 A 的知识库
→ 软删除项目 A
→ 发布知识库
```

发布会成功，但该知识库已没有有效项目作用域。

**建议修复**

- 发布时通过 binding join `AgentProject`，要求至少有一个：

```text
project.status = active
AND project.deleted_at IS NULL
```

- 删除项目时明确处理关联 binding；
- 或禁止删除仍是某知识库唯一有效绑定方的项目；
- 将“至少一个有效项目绑定”作为业务与数据库层共同维护的不变量。

---

## 五、Medium / P2：建议在阶段四实现前纳入设计

### P2-1：解绑最后一个项目绑定存在并发竞争

**位置**

- `app/services/rag.py:252-270`

**问题**

当前先读取 binding 数量再删除。若知识库仅有两个 binding，两个并发解绑请求可以都读到数量为 2，随后都执行删除，最终留下零 binding。

**建议修复**

- 锁定 KnowledgeBase 或关联 binding 集合；
- 更可靠地使用数据库触发器 / 受控存储过程保护最小基数；
- 为并发解绑添加集成测试。

---

### P2-2：Document、Version、Job 与 Chunk 的同父/同知识库关系未被数据库保证

**位置**

- `app/db/models/rag.py:125-127`
- `app/db/models/rag.py:188-193`
- `app/db/models/rag.py:230-235`

**问题**

当前 UUID 外键独立存在，数据库允许：

- 一个 Document 的 `current_published_version_id` 指向其他 Document 的 Version；
- 一个 Job 的 `document_id` 与 `document_version_id` 不属于同一 Document；
- 一个 Chunk 的 `document_version_id` 属于知识库 A，但 `knowledge_base_id` 指向知识库 B。

**影响**

阶段四 Worker 一旦关联错误，数据库仍会接受数据，从而可能造成错误发布、级联删除异常或跨知识库检索泄露。

**建议修复**

- 通过复合唯一键 / 复合外键表达同父关系；
- 或在受控写入层中强制验证并用数据库触发器作为最终防线；
- 在开始 Worker 写入 Chunk 前必须补充该完整性保护。

---

### P2-3：Compose 配置队列名与 Worker 实际消费队列不一致

**位置**

- `compose.yaml:24`
- `compose.yaml:137-144`
- `app/workers/celery_app.py:16-18`

**问题**

生产者使用可配置的：

```text
AURUM_INGESTION_QUEUE_NAME
```

但 Compose Worker 固定为：

```yaml
--queues=aurum-ingestion
```

修改环境变量后，生产者可能投递到新队列，而 Worker 仍只消费旧队列。

**建议修复**

将 Worker 参数改为变量化：

```yaml
--queues=${AURUM_INGESTION_QUEUE_NAME:-aurum-ingestion}
```

并增加非默认队列名的 Compose / Worker 冒烟验证。

---

### P2-4：S3/MinIO 依赖未进入 readiness 健康检查

**位置**

- `app/main.py`
- `compose.yaml:126-130`
- `app/providers/s3_object_storage.py:17-35`

**问题**

API 启动仅构造 boto3 Client，不会验证 bucket 存在、应用账户存在或权限正确。healthcheck 仅访问 `/health/live`。

因此可能出现：

```text
API healthy
MinIO healthy
但应用 S3 账户不存在或 bucket 无权限
→ 首次上传才失败
```

**建议修复**

- 区分 liveness 与 readiness；
- readiness 执行应用账户有权限的轻量 bucket / object 操作；
- 避免使用 root 账户检查；
- 将失败原因保留在服务端日志，不暴露存储内部细节。

---

### P2-5：未来预签名下载 URL 可能使用 Docker 内部主机名

**位置**

- `compose.yaml:18`
- `app/providers/s3_object_storage.py:99-110`

**问题**

容器内使用：

```text
http://minio:9000
```

通过该 endpoint 生成的预签名 URL 可能包含 `minio:9000`，浏览器无法解析 Docker 内部 DNS 名称。

当前没有公开下载接口，因此尚不影响已实现上传路径。

**建议修复**

后续提供下载/预览前，区分：

- 服务端内部 S3 endpoint；
- 对浏览器可访问的公开 / 反向代理 endpoint；
- 预签名 URL 所使用的外部 endpoint。

---

## 六、依赖与本地环境提示

### `pip check` 报告的全局依赖冲突

本地 Anaconda base 环境仍报告：

```text
aiobotocore 2.19.0 requires botocore<1.36.4,>=1.36.0,
but installed botocore is 1.43.56
```

Aurum 当前直接使用 `boto3`，不直接使用 `aiobotocore`，因此该冲突不等于当前应用代码无法运行；但说明 base 环境存在全局依赖污染。

**建议**：为项目建立独立虚拟环境，并在该环境中执行开发、测试、迁移、Worker 和 CI，不继续将 Anaconda base 环境作为可靠验证基线。

---

## 七、建议修复顺序

在开始阶段三第 4 步之前，建议按以下顺序实施：

1. 将历史迁移改为不可变 DDL / 历史 Metadata，并验证空数据库 `upgrade head`；
2. 修复 `0004` downgrade 的约束名，并验证 downgrade / upgrade round-trip；
3. 在 MinIO 初始化流程中创建应用账户、最小权限策略和 bucket 绑定；
4. 实现并启动可靠 Outbox dispatcher / Beat；
5. 为 Outbox 增加错误持久化、指数退避、最大重试与 dead-letter / 管理重试；
6. 引入上传请求幂等记录，修复预留—存储—激活的并发与故障恢复；
7. 修复项目软删除、发布与“至少一个有效项目 binding”的不变量；
8. 补强 Document / Version / Job / Chunk 的同父与同知识库完整性约束；
9. 修复队列名 Compose 配置漂移；
10. 增加 S3 readiness 与外部下载 endpoint 配置，为未来下载/预览做准备。

## 八、阶段四的准入条件

以下条件满足后，才建议开始 PDF/DOCX/CSV/XLSX 解析、清洗、Chunk、DashScope Embedding、pgvector 写入与原子版本发布：

- [x] 全新 PostgreSQL 数据库可完成 `alembic upgrade head`；
- [x] 迁移 downgrade / upgrade round-trip 可通过；
- [x] MinIO 应用账户拥有并仅拥有目标 bucket 所需权限；
- [ ] 已完成真实管理员上传：API → MinIO → Document/Version/Job/Outbox；
- [x] Outbox 可自动投递且投递失败有持久化退避和恢复路径；
- [x] 幂等重复与并发上传不会创建孤儿 Document / Version；
- [x] 已保证项目 binding、Document/Version/Job/Chunk 的作用域完整性；
- [x] 非默认队列名配置下 Worker 能正常消费；
- [ ] 基础运维指标与 readiness 能准确反映数据库、Redis、MinIO、Worker 状态。
