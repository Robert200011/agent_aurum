# Aurum 金融财务管理与投资知识问答 Agent 总体技术方案与实施路线

> 文档状态：已确认，按实施进度持续维护
> 项目目录：`E:\agent_aurum`
> 文档分类目录：`project_introduction/`
> 编写日期：2026-07-23
> 最后更新：2026-08-02

## 0. 项目里程碑与当前状态

| 里程碑 | 状态 | 完成日期 | 主要交付 |
| --- | --- | --- | --- |
| 阶段一：架构和安全底座 | 已完成 | 2026-07-23 | FastAPI 分层架构、身份认证、数据库 schema、RLS、Redis、Docker Compose 和基础安全能力 |
| 阶段二：个人财务数据基础 | 已完成 | 2026-07-24 | 账户、流水、预算、投资、行情、确定性报表、CSV/XLSX 导入和多用户隔离 |
| 阶段一、二配套 Web 前端 | 已完成 | 2026-07-24 | 登录注册、应用框架、财务总览、账户、流水、预算和投资管理界面 |
| 阶段二收尾与安全审计整改 | 已完成 | 2026-07-24 | Refresh Token Cookie、登录限流、XLSX 防护、敏感默认配置移除及回归验证 |
| 阶段三：知识库管理 | 已完成 | 2026-07-29 | 知识库管理、六类文档入库、Hybrid Retrieval 基础、任务重试及管理员浏览器验收 |
| 阶段四：基础 RAG 问答 | 已完成 | 2026-07-31 | 浏览器问答、可信引用、持久化、Hybrid Retrieval、Reranker、SSE 和加密 Checkpoint |
| 阶段五：个人财务 Agent | 开发中（P5.1 至 P5.5 已完成） | 2026-08-02（P5.1 至 P5.5） | 完整只读工具、财务证据、运行审计、受控编排和前端可追溯展示 |
| 阶段六至阶段七 | 尚未开始 | — | 完整企业级加固和后续增强 |

阶段一稳定基线为提交 `933390a`，阶段二通过合并提交 `3bfb9b0` 进入 `master`。
截至 2026-07-31，阶段一至阶段四已经完成并合并到 `master`，当前基线提交为
`7b99307`。PDF、DOCX、Markdown、TXT、CSV、XLSX 均已进入统一
入库链路，管理员项目/知识库管理、文档上传与版本、任务进度与人工重试、Dense 检索
测试前端已经与管理 API 对齐。真实 DashScope Key 下的文档 Embedding、查询 Embedding、
pgvector 检索、来源展示和检索日志持久化已经通过浏览器核心验收；阶段四基础 RAG
问答 Demo、可信结构化引用、会话持久化、Hybrid Retrieval、Reranker 和 SSE 流式输出
已完成；阶段四增强项 Hybrid Retrieval、Reranker、SSE 与加密的 LangGraph
PostgreSQL Checkpoint 也已接入。阶段五已进入开发，P5.1 财务工具契约和最小 Agent
闭环、P5.2 完整只读工具集、P5.3 时间范围、币种与汇率以及 P5.4 开支异常分析和预算
建议以及 P5.5 运行记录、财务证据和前端展示均已完成，P5.6
按本方案继续推进。

## 1. 项目目标

本项目计划在 `E:\agent_aurum` 中独立开发一个基于 LangGraph 的金融财务管理与投资知识问答系统。当前阶段不依赖其他业务项目，用户、鉴权、知识库、会话、财务数据和 Agent 能力均在本项目内形成完整闭环。

系统主要面向以下场景：

- 个人记账和消费分析；
- 银行账户、存款和收支查询；
- 股票、基金及其他投资持仓分析；
- 财务与投资知识库问答；
- 基于个人真实财务数据和专业知识库给出针对性建议；
- 通过浏览器完成知识库管理、问答和多会话管理。

系统需要重点保证：

- 多用户数据隔离；
- 回答依据可追溯；
- 财务计算准确；
- 用户隐私和数据安全；
- 会话长期持久化；
- 服务可观测、可恢复、可扩展。

## 2. 当前项目基础

项目已经从最小示例演进为可独立启动的前后端应用。后端位于根目录 `app/`，前端位于
`web/`，本地基础设施由 `compose.yaml` 提供。

当前已经实际承载：

- 用户注册、登录、鉴权和角色管理；
- FastAPI 接口；
- 账户、收支、存款、持仓等结构化财务数据；
- 财务汇总和 CSV/XLSX 流水导入；
- PostgreSQL RLS、Redis 安全状态和审计日志；
- 覆盖阶段一、二能力的 Vue 3 浏览器管理界面。

后续阶段将继续建设：

- LangGraph 工作流和 Agent 工具；
- RAG 检索、模型适配和评测；
- 文档解析、索引和异步处理任务；
- 多会话、历史记录、流式问答和引用界面。

当前阶段的原则是：

- 仅聚焦 `agent_aurum`；
- 使用 Python 构建后端和 Agent 核心；
- 使用独立数据库和运行环境；
- 不依赖其他项目的用户、接口或数据表；
- 通过抽象接口为未来系统集成保留扩展点。

## 3. 总体架构

推荐采用独立的 Python Agent 应用架构：

```text
Vue 3 浏览器端
    │
    ▼
Caddy / Nginx
    │
    ▼
Python FastAPI API
    ├── 用户注册、登录与 RBAC
    ├── 项目和知识库管理
    ├── 会话、消息与 SSE
    ├── 账户、流水、预算和持仓
    ├── LangGraph Agent 工作流
    └── 管理和审计 API
          │
          ├── PostgreSQL + pgvector
          ├── Redis
          ├── S3 兼容对象存储
          ├── Celery 异步 Worker
          ├── Embedding / Reranker
          └── LLM Provider
```

### 3.1 项目职责

- 使用 Python 3.12；
- 使用 FastAPI 提供全部后端 API；
- 使用 LangGraph 编排问答流程；
- 自行负责用户身份、权限和管理员账号；
- 自行负责账户、流水、预算和持仓数据；
- 负责知识库解析、索引和检索；
- 负责问答生成、引用校验和风险检查；
- 负责 LangGraph Checkpoint；
- 负责浏览器端知识库管理和知识问答；
- 负责独立部署、监控、备份和恢复；
- 为未来外部系统接入提供 Provider 接口，但不将其作为当前依赖。

### 3.2 模块边界

项目内部仍需保持清晰分层：

```text
API / Router
    ↓
Application Service
    ↓
Domain Service / Agent / RAG
    ↓
Repository / Provider
    ↓
PostgreSQL / Redis / Object Storage / Model API
```

模型不能直接访问数据库。所有数据操作必须经过权限校验后的 Service 和 Repository。

## 4. 核心设计原则

个人财务数据和知识库文档必须采用不同的数据处理方式。

### 4.1 非结构化知识使用 RAG

适用数据：

- 财务知识文档；
- 投资基础资料；
- 股票和基金研究资料；
- PDF、Word、Markdown、TXT；
- CSV、Excel 说明性文件；
- 个人理财规则；
- 投资风险说明；
- 系统使用帮助文档。

处理流程：

```text
上传
  ↓
文件安全检查
  ↓
文档解析和清洗
  ↓
结构化分块
  ↓
Embedding
  ↓
向量和关键词索引
  ↓
检索与重排
  ↓
回答生成
  ↓
引用和事实一致性校验
```

### 4.2 结构化财务数据使用确定性工具

以下信息不能只依靠向量检索或让模型自行计算：

- 账户余额；
- 月度收入和支出；
- 存款变化；
- 消费分类；
- 预算执行情况；
- 股票和基金持仓；
- 持仓成本；
- 已实现和未实现盈亏；
- 行情时间；
- 币种和汇率。

Agent 应调用服务器定义的只读工具：

- `get_finance_summary`
- `get_income_expense_report`
- `search_transactions`
- `get_account_balances`
- `get_budget_status`
- `get_portfolio_summary`
- `get_holding_performance`
- `get_market_snapshot`

这些工具调用本项目内的 Python 财务 Application Service，并由 FastAPI 鉴权依赖从令牌中解析和注入当前用户 ID。工具参数中不允许出现可由模型自由填写的用户 ID。

禁止：

- 让模型接收或指定任意 `user_id`；
- 让模型执行任意 SQL；
- 将数据库连接工具直接暴露给模型；
- 允许 Agent 绕过 Python Service 和 Repository 层业务规则；
- 将经常变化的流水和余额简单向量化后作为计算依据。

### 4.3 混合问题联合回答

例如：

> 为什么我这个月餐饮开支增加了？应该如何调整预算？

LangGraph 应同时获取：

1. 当前用户本月和历史餐饮流水；
2. 月度收入、支出和预算执行情况；
3. 知识库中的预算管理资料；
4. 风险和建议规则。

最终回答需要区分：

- 用户真实数据；
- 知识库事实；
- 模型基于事实生成的建议；
- 风险提示；
- 数据更新时间。

## 5. LangGraph 工作流

推荐使用受控的 Hybrid RAG，而不是允许模型完全自由执行的 Agent。

初步工作流：

```text
用户问题
   ↓
身份、权限和会话验证
   ↓
输入安全检查
   ↓
问题分类
   ├── 通用财务知识
   ├── 个人收支查询
   ├── 投资持仓分析
   ├── 混合问题
   └── 高风险投资建议
   ↓
查询改写、实体识别和时间范围解析
   ↓
执行知识库检索或财务工具调用
   ↓
候选结果重排和相关性验证
   ↓
生成带引用的回答
   ↓
事实一致性、引用和风险校验
   ↓
保存消息、引用和运行记录
   ↓
通过 SSE 流式返回浏览器
```

### 5.1 建议的主要节点

- `authenticate_context`
- `validate_input`
- `classify_intent`
- `extract_entities`
- `parse_time_range`
- `rewrite_query`
- `plan_execution`
- `retrieve_knowledge`
- `call_finance_tools`
- `call_market_tools`
- `analyze_finance`
- `rerank_context`
- `grade_context`
- `generate_answer`
- `validate_financial_evidence`
- `validate_citations`
- `check_groundedness`
- `apply_financial_risk_policy`
- `persist_result`

### 5.2 写操作控制

V1 版本建议所有 Agent 工具只读。

如果后续加入以下能力：

- 自然语言记账；
- 修改账户余额；
- 修改持仓；
- 删除流水；
- 调整预算；

必须使用 Human-in-the-loop：

1. Agent 生成待执行操作；
2. 展示影响范围；
3. 用户确认、修改或拒绝；
4. 确认后才调用本项目内部的财务写服务；
5. 保存完整审计记录。

## 6. 用户、登录和权限

### 6.1 用户功能

- 用户注册；
- 用户名或邮箱登录；
- 查看个人资料；
- 修改密码；
- 登出；
- Access Token；
- Refresh Token；
- Refresh Token 轮换；
- 登录失败限流；
- 用户禁用和锁定；
- 跨时间登录后恢复历史会话。

### 6.2 角色

初期定义两个角色：

- `admin`
- `user`

后续可以扩展：

- `knowledge_editor`
- `auditor`
- `support`

### 6.3 管理员初始化

初始管理员：

- 用户名：`admin`
- 初始密码：不提供代码默认值，必须通过 `AURUM_ADMIN_INITIAL_PASSWORD` 显式注入

安全要求：

- 数据库只保存 Argon2id 或 bcrypt 哈希；
- 初始化过程必须幂等；
- 服务重启不得覆盖管理员密码；
- 推荐管理员首次登录强制修改密码；
- 所有环境都必须通过安全环境变量提供初始密码；
- 不得在日志中输出初始密码。

计划中的登录接口采用：

```json
{
  "identifier": "admin",
  "password": "<AURUM_ADMIN_INITIAL_PASSWORD 中的值>"
}
```

`identifier` 同时支持用户名和邮箱。

### 6.4 权限控制

前端：

- 普通用户不显示知识库和项目管理菜单；
- 管理页面设置路由守卫；
- 无权限页面跳转到 403。

后端：

- 所有管理 API 强制校验 `admin` 角色；
- 禁止仅依靠前端隐藏按钮实现权限控制；
- 管理操作写入审计日志；
- 用户只允许访问自己的会话和财务数据；
- Agent 服务不直接信任浏览器传来的角色和用户 ID。

## 7. 知识库和项目管理

### 7.1 项目

`agent_projects` 用于保存：

- 项目名称和描述；
- 系统提示词版本；
- 生成模型配置；
- Embedding 模型配置；
- Reranker 配置；
- 检索参数；
- 绑定的知识库；
- 风险策略；
- 启用和停用状态。

### 7.2 知识库

`knowledge_bases` 用于保存：

- 名称；
- 描述；
- 发布状态；
- 当前版本；
- 可见范围；
- 文档数量；
- 索引状态；
- 创建人和更新时间。

### 7.3 文档

文档需要支持：

- 上传；
- 批量上传；
- 下载；
- 预览；
- 删除；
- 启用和停用；
- 文档版本；
- 内容哈希；
- 解析状态；
- 索引状态；
- 失败重试；
- 重新解析；
- 重新索引；
- 标签和分类；
- 页码、章节、表格、行号等元数据。

### 7.4 管理页面

管理员页面计划包括：

- 项目列表和编辑页；
- 知识库列表和编辑页；
- 文档上传页；
- 文档预览页；
- 文档版本页；
- 解析和索引任务页；
- 分块预览页；
- 检索测试页；
- 提示词配置页；
- 模型配置页；
- 审计日志页。

普通用户不能访问以上页面和 API。

## 8. 浏览器问答界面

### 8.1 会话功能

- 新建会话；
- 历史会话列表；
- 会话重命名；
- 会话归档；
- 会话删除；
- 会话搜索；
- 跨设备恢复；
- 重新生成；
- 停止生成；
- 失败重试；
- 回答反馈。

### 8.2 回答展示

- SSE 流式输出；
- Markdown；
- 表格；
- 财务指标卡片；
- 可选的 ECharts 图表；
- 数据更新时间；
- 回答风险提示；
- 引用角标；
- 引用片段抽屉；
- 原文定位。

### 8.3 引用结构

后端应返回结构化回答：

```json
{
  "answer": "根据资料[1]，本月餐饮支出较上月增加……",
  "citations": [
    {
      "citation_id": 1,
      "document_id": "document-uuid",
      "document_version_id": "version-uuid",
      "chunk_id": "chunk-uuid",
      "title": "个人预算管理指南",
      "page": 12,
      "section": "餐饮预算",
      "quote": "建议将餐饮支出控制在可支配收入的合理区间内……",
      "score": 0.87
    }
  ],
  "data_as_of": "2026-07-23T10:30:00+08:00",
  "risk_notice": "以上内容仅供个人财务管理参考。"
}
```

引用校验要求：

- 模型只能引用本次实际检索到的 `chunk_id`；
- 不接受模型生成的任意文档 ID；
- 引用必须属于当前已发布知识库；
- 引用片段必须经过用户权限过滤；
- 文档删除或下线后，历史引用仍保留版本信息；
- 回答保存引用快照，避免原文变化后无法审计。

## 9. 多用户、多会话和持久化

### 9.1 产品业务表

建议建立：

- `conversations`
- `messages`
- `message_citations`
- `agent_runs`
- `agent_tool_calls`

这些表用于：

- 会话列表；
- 历史消息；
- 会话搜索；
- 引用追踪；
- 运行统计；
- 审计；
- 错误诊断。

### 9.2 LangGraph Checkpoint

- 每个会话 UUID 映射为 LangGraph `thread_id`；
- 使用 `AsyncPostgresSaver`；
- 保存图状态、执行步骤和恢复点；
- 支持故障后继续执行；
- 支持 Human-in-the-loop；
- Checkpoint 存放在独立 `agent` schema；
- 对敏感状态启用加密。

当前实现补充约束：

- API 启动时由迁移账号幂等执行 Checkpointer 自带的 `setup()`；
- 运行期使用最小权限应用账号读写 Checkpoint；
- SSE 与非流式回答均通过同一 LangGraph 图执行，不允许流式路径绕开 Checkpoint；
- Checkpoint channel value 使用 AES-EAX 加密，生产环境必须配置独立的
  `AURUM_LANGGRAPH_AES_KEY`；
- `agent_runs.detail.checkpoint_id` 关联最终恢复点，产品消息仍以 `chat` schema
  中的业务表为准。

当前聊天体验增强约束：

- SSE HTTP 订阅断开不再自动取消生成，后台运行通过独立数据库会话继续完成；
- 前端使用 `agent_run.id` 重新订阅并重放同一次生成事件，刷新页面后可恢复展示；
- 用户点击“停止生成”时才调用取消端点并把消息、运行记录收敛为 `cancelled`；
- 永久删除会话时同时级联清理业务消息、引用、运行记录和对应 Checkpoint thread；
- 当前 Demo 的事件重放协调器面向单 API 进程；跨进程、容器重启后的实时续传留待后续用
  Redis 事件流或持久化任务队列增强，最终消息与 Checkpoint 仍会持久化保留。

产品会话表和 LangGraph Checkpoint 不能相互替代：

- 产品表负责用户可见的会话和消息；
- Checkpoint 负责 Agent 图运行状态和恢复。

## 10. 数据模型初稿

### 10.1 用户和鉴权

- `users`
  - `id`
  - `email`
  - `username`
  - `password_hash`
  - `role`
  - `status`
  - `password_changed_at`
  - `must_change_password`
  - `token_version`
  - `created_at`
  - `updated_at`

- `refresh_tokens`
  - `user_id`
  - `token_hash`
  - `device_info`
  - `expires_at`
  - `revoked_at`

- `audit_logs`
  - `actor_user_id`
  - `action`
  - `resource_type`
  - `resource_id`
  - `ip`
  - `user_agent`
  - `detail`
  - `created_at`

### 10.2 个人财务

- `financial_accounts`
  - `id`
  - `user_id`
  - `name`
  - `account_type`
  - `currency`
  - `balance`
  - `is_active`
  - `created_at`
  - `updated_at`

- `financial_transactions`
  - `id`
  - `user_id`
  - `account_id`
  - `transaction_type`
  - `amount`
  - `currency`
  - `category`
  - `description`
  - `transaction_date`
  - `source`
  - `created_at`

- `budgets`
  - `id`
  - `user_id`
  - `category`
  - `period`
  - `amount`
  - `currency`
  - `start_date`
  - `end_date`

- `investment_holdings`
  - `id`
  - `user_id`
  - `account_id`
  - `symbol`
  - `asset_type`
  - `quantity`
  - `cost_basis`
  - `currency`
  - `updated_at`

- `investment_transactions`
  - `id`
  - `user_id`
  - `holding_id`
  - `transaction_type`
  - `quantity`
  - `price`
  - `fee`
  - `currency`
  - `transaction_at`

- `market_price_snapshots`
  - `symbol`
  - `asset_type`
  - `price`
  - `currency`
  - `recorded_at`
  - `data_source`

所有包含个人数据的表必须包含 `user_id`，并同时使用应用层过滤和 PostgreSQL Row Level Security 进行隔离。金额使用定点数类型，不使用二进制浮点数。

### 10.3 RAG

- `agent_projects`
- `knowledge_bases`
- `project_knowledge_bases`
- `documents`
- `document_versions`
- `document_chunks`
- `ingestion_jobs`
- `retrieval_logs`

`document_chunks` 主要字段：

- `id`
- `document_version_id`
- `knowledge_base_id`
- `content`
- `content_hash`
- `embedding`
- `page_number`
- `section_path`
- `sheet_name`
- `row_start`
- `row_end`
- `metadata`
- `token_count`
- `created_at`

### 10.4 会话

- `conversations`
  - `id`
  - `user_id`
  - `project_id`
  - `title`
  - `status`
  - `created_at`
  - `updated_at`

- `messages`
  - `id`
  - `conversation_id`
  - `user_id`
  - `role`
  - `content`
  - `status`
  - `model`
  - `prompt_tokens`
  - `completion_tokens`
  - `latency_ms`
  - `created_at`

- `message_citations`
  - `message_id`
  - `chunk_id`
  - `rank`
  - `score`
  - `quote_snapshot`

- `agent_runs`
  - `id`
  - `conversation_id`
  - `message_id`
  - `thread_id`
  - `trace_id`
  - `status`
  - `error_code`
  - `started_at`
  - `completed_at`

## 11. 技术栈建议

### 11.1 前端

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Axios
- Ant Design Vue 或 shadcn-vue
- ECharts
- Markdown 渲染组件

### 11.2 Python API 和业务服务

- Python 3.12
- FastAPI
- Pydantic 2
- SQLAlchemy 2
- asyncpg
- Alembic
- PyJWT 或 Authlib
- Argon2id
- Celery
- Redis
- Uvicorn
- SSE
- OpenTelemetry
- Prometheus

### 11.3 LangGraph 和 RAG

- LangGraph
- LangChain
- LangGraph PostgreSQL Checkpointer
- 文档加载和解析组件
- Embedding Provider
- Reranker Provider
- 结构化输出校验
- RAG 自动化评测

### 11.4 检索

- PostgreSQL 16
- pgvector
- HNSW
- Dense Retrieval
- 中文关键词或 Sparse Retrieval
- Reciprocal Rank Fusion
- Cross-encoder Reranker
- 元数据过滤

### 11.5 文档和对象存储

- S3 兼容对象存储；
- 本地开发可以使用 MinIO；
- 生产可使用 AWS S3、Cloudflare R2、Backblaze B2 或兼容服务；
- 原始文件和解析产物分开存储；
- 数据库只保存对象键和元数据。

### 11.6 模型

生成模型采用适配层，不在业务代码中硬编码提供商。

初期支持：

- OpenAI-compatible API；
- 云端模型；
- 本地 vLLM；
- 后续可切换 Qwen、DeepSeek 或其他模型。

中文 Embedding 和 Reranker 候选：

- `Qwen3-Embedding-0.6B`
- `Qwen3-Reranker-0.6B`
- `BAAI/bge-m3`

最终模型应通过项目自己的财务问答评测集确定。

## 12. 检索方案

初步检索流程：

1. 根据用户、项目和知识库进行权限过滤；
2. 对问题进行改写和实体抽取；
3. 执行 Dense 向量召回；
4. 执行关键词或 Sparse 召回；
5. 使用 Reciprocal Rank Fusion 合并结果；
6. 使用 Reranker 对候选片段重新排序；
7. 去除重复和高度相似片段；
8. 控制上下文 Token；
9. 对上下文相关性进行判断；
10. 上下文不足时明确提示资料不足。

建议初始参数：

- 向量召回：20～40 个片段；
- 关键词召回：20～40 个片段；
- 合并后候选：30～50 个片段；
- Reranker 最终保留：6～10 个片段。

这些值需要通过真实知识库评测后调整。

## 13. 安全设计

### 13.1 身份和网络

- 全站 HTTPS；
- 生产环境通过 Caddy 或 Nginx 暴露 FastAPI；
- FastAPI 统一完成身份认证和 RBAC；
- 数据库、Redis、对象存储和 Worker 仅开放在内部网络；
- JWT 密钥禁止写入版本库；
- 建议从共享 HS256 升级到非对称签名；
- 支持密钥轮换；
- Refresh Token 只保存哈希。

### 13.2 数据隔离

- 应用层所有查询携带 `user_id`；
- PostgreSQL 启用 Row Level Security；
- 普通用户不能访问其他用户会话；
- Agent 工具不能接收任意用户 ID；
- 管理员知识库权限与个人财务数据权限分离；
- 数据库服务账号按最小权限配置。

### 13.3 文件安全

- 文件大小限制；
- 扩展名白名单；
- MIME 类型校验；
- 文件名规范化；
- 病毒扫描；
- 压缩炸弹检测；
- 禁止执行上传文件；
- 文档解析进程资源限制；
- 对象存储使用随机对象键。

### 13.4 Prompt Injection

- 将文档内容视为不可信输入；
- 明确区分系统指令和知识内容；
- 文档中的命令不得成为 Agent 指令；
- 工具调用使用白名单；
- 高风险工具必须人工确认；
- 对检索内容进行注入检测；
- 输出前执行风险和引用校验。

### 13.5 日志和隐私

- 日志不记录密码和 Token；
- 不记录完整银行卡号；
- 对流水描述和个人信息脱敏；
- 模型调用日志可配置关闭；
- 云模型调用前进行敏感字段处理；
- 保存模型提供商、模型版本和数据时间；
- 对管理操作和工具调用进行审计。

## 14. 企业级性能优化

### 14.1 文档处理

- 文档解析异步化；
- OCR 异步化；
- Embedding 批处理；
- 内容哈希去重；
- 增量索引；
- 文档版本化；
- 失败重试；
- 死信队列；
- 任务幂等；
- 大文件分段处理。

### 14.2 检索

- HNSW 索引；
- 项目和知识库元数据索引；
- 热点检索缓存；
- 问题语义缓存；
- Reranker 批处理；
- 上下文去重；
- 自适应 Top-K；
- 检索超时和降级；
- 大规模后可替换独立检索引擎。

### 14.3 财务查询

- 月度收支预聚合；
- 投资组合快照；
- 财务指标缓存；
- 查询结果带数据版本；
- 用户数据变化后主动失效缓存；
- 账户、流水和持仓查询保持参数化；
- 复杂报表异步生成。

### 14.4 模型调用

- 简单和复杂问题模型路由；
- Token 预算；
- 上下文压缩；
- 超时；
- 指数退避重试；
- 熔断；
- 多提供商降级；
- 并发限制；
- 用户配额；
- 成本统计；
- SSE 流式输出。

### 14.5 水平扩展

- FastAPI 服务保持无状态；
- 所有会话状态存储在 PostgreSQL；
- 所有缓存和限流状态存储在 Redis；
- 多实例共享对象存储；
- Worker 可以独立扩容；
- API、Worker 和模型服务分别扩缩容。

## 15. 可观测性

需要贯通以下链路：

```text
浏览器
  → Caddy
  → FastAPI
  → LangGraph 节点
  → Retriever
  → 财务工具
  → LLM
  → PostgreSQL / Redis
```

计划包括：

- OpenTelemetry Trace；
- 统一 `trace_id`；
- Prometheus 指标；
- Grafana 仪表板；
- 结构化日志；
- 请求错误率；
- 首字延迟；
- 总回答延迟；
- 检索延迟；
- 模型延迟；
- Token 和费用；
- 工具调用成功率；
- 引用覆盖率；
- 文档处理成功率；
- 队列积压；
- 数据库连接池状态。

对 LangSmith 等外部观测服务应保持可选，并避免上传未经脱敏的个人财务数据。

## 16. 测试和质量评估

### 16.1 常规测试

- Python 单元测试；
- API 集成测试；
- 数据库迁移测试；
- Provider 接口合同测试；
- 前端组件测试；
- 浏览器端 E2E 测试；
- Docker Compose 冒烟测试。

### 16.2 权限测试

- 普通用户无法访问管理 API；
- 普通用户无法打开管理页面；
- 用户 A 无法读取用户 B 会话；
- 用户 A 无法查询用户 B 流水；
- 伪造 `user_id` 无效；
- 过期和撤销 Token 无效；
- 被禁用用户不能继续使用已有 Token。

### 16.3 RAG 评测

建立财务领域黄金测试集：

- 知识类问题；
- 个人收支问题；
- 时间范围问题；
- 投资持仓问题；
- 混合问题；
- 知识库没有答案的问题；
- 文档冲突问题；
- Prompt Injection 问题；
- 高风险投资建议问题。

主要指标：

- Retrieval Recall@K；
- Reranker 命中率；
- 引用准确率；
- 引用覆盖率；
- Groundedness；
- 回答完整性；
- 幻觉率；
- 拒答准确率；
- 财务数值正确率；
- 跨用户数据泄漏数量。

### 16.4 性能测试

- API 压力测试；
- SSE 并发测试；
- 大文件上传测试；
- 批量索引测试；
- HNSW 检索性能测试；
- Worker 积压恢复测试；
- 模型超时和降级测试；
- PostgreSQL 和 Redis 故障恢复测试。

## 17. 实施阶段

### 阶段一：架构和安全底座

- [x] 建立 Python 项目目录和依赖管理；
- [x] 建立 FastAPI 应用骨架；
- [x] 建立 PostgreSQL、Redis 和 pgvector 开发环境；
- [x] 定义 API、Service、Repository 和 Provider 分层；
- [x] 用户角色；
- [x] 管理员初始化；
- [x] 用户名或邮箱登录；
- [x] 修改密码；
- [x] Access/Refresh Token；
- [x] 登出和令牌撤销；
- [x] 建立用户、财务、RAG 和会话数据库 schema；
- [x] Docker Compose 开发环境；
- [x] 统一配置和密钥管理。

阶段一于 2026-07-23 完成，并通过静态检查、类型检查、自动化测试、全新 Docker
Compose 启动、真实认证流程以及 PostgreSQL RLS 跨用户隔离验证。

### 阶段二：个人财务数据基础

- [x] 账户管理；
- [x] 收入和支出流水管理；
- [x] 预算管理；
- [x] 股票和基金持仓管理；
- [x] 投资交易记录；
- [x] 行情快照；
- [x] CSV 和 Excel 账单导入；
- [x] 月度收支聚合；
- [x] 财务数据用户隔离；
- [x] 财务数据查询和统计测试。

阶段二于 2026-07-24 完成并合并进入 `master`。实现范围包括财务 CRUD、余额和收益
联动、统一币种口径的确定性汇总、导入幂等与逐行错误报告，以及应用层 `user_id`
过滤和 PostgreSQL RLS 双重隔离。

### 阶段一、二配套 Web 前端

- [x] 登录、注册、退出登录和强制修改初始密码；
- [x] 响应式应用框架、导航和用户菜单；
- [x] 财务总览、账户、流水、预算和投资管理；
- [x] CSV/XLSX 流水导入；
- [x] 按当前币种统一展示账户、余额、交易、预算和投资数据；
- [x] 加载、空状态、错误提示和前端自动化测试。

配套前端于 2026-07-24 随阶段二完成，位于根目录 `web/`。

### 阶段二收尾：安全审计整改

- [x] Refresh Token 从浏览器 `localStorage` 迁移到 HttpOnly Cookie；
- [x] 登录接口增加单 IP 和全局固定窗口限流，并保留账号/IP 失败锁定；
- [x] XLSX 导入增加 ZIP 容器预检、流式解压上限和逐行扫描上限；
- [x] 移除 JWT、初始管理员和数据库密码的可用开发默认值；
- [x] 增加安全配置生成脚本、回归测试和部署文档说明。

上述整改于 2026-07-24 完成。当前回归基线为 59 项后端测试、10 项前端测试，
Ruff、Mypy、Alembic、Docker Compose 配置检查和前端生产构建全部通过。

### 阶段三：知识库管理

- [x] 项目管理；
- [x] 知识库管理后端；
- [x] 文档上传；
- [x] 对象存储；
- [x] Markdown、TXT 解析；
- [x] PDF、DOCX 受限解析及页码/章节定位；
- [x] CSV、XLSX 受限解析及工作表/行范围定位；
- [x] 异步任务；
- [x] 六类文档的确定性分块和来源边界保护；
- [x] DashScope Embedding 适配器、批处理流水线及真实 Key 入库/查询冒烟；
- [x] pgvector 写入、检索和 HNSW 索引；
- [x] 文档版本及原子发布；
- [x] Worker 内部任务进度和失败重试；
- [x] 管理员 Dense 检索测试、任务进度和人工重试 API；
- [x] 管理员知识库前端：项目与知识库管理、项目绑定、文档和版本上传、任务进度与
  人工重试、源文件下载及 Dense 检索测试。
- [x] 管理员浏览器核心验收：项目/知识库生命周期、版本入库、真实向量检索、来源展示
  和检索日志 RLS 持久化。

阶段一至阶段三已经完成；阶段四基础 RAG 浏览器问答 Demo 及当前规划的聊天增强项已完成。

### 阶段四：基础 RAG 问答

- [x] LangGraph 状态定义；
- [x] Hybrid Retrieval；
- [x] Reranker；
- [x] 回答生成；
- [x] SSE 流式输出；
- [x] 结构化引用；
- [x] 引用原文查看；
- [x] 会话和消息保存；
- [x] LangGraph Postgres Checkpoint；
- [x] 历史会话恢复；
- [x] 会话删除与会话搜索；
- [x] 重新生成回答与失败回答重试；
- [x] 显式停止生成；
- [x] SSE 检索、生成和引用收尾状态展示；
- [x] 单 API 进程内跨请求恢复运行中的生成任务。

### 阶段五：个人财务 Agent

阶段五采用“受控编排的只读财务 Agent”，不允许模型自由调用数据库、指定用户身份或
执行财务写操作。现有聊天 API、会话持久化、SSE、LangGraph Checkpoint、RAG 检索和
可信引用链路继续作为唯一问答入口；阶段五只扩展现有回答图和聊天页面，不开发独立的
“财务 Agent 页面”，也不重复实现阶段二已有的财务业务逻辑。

现有 `FinanceService` 已具备财务摘要、流水筛选、账户、预算、持仓估值和行情快照等
确定性能力。阶段五首先为这些能力定义受限工具契约，然后增加问题分类、时间与币种
解析、工具路由、财务分析、混合回答和风险校验。

#### 阶段五目标和边界

- V1 所有 Agent 工具只读；
- 模型只负责问题分类、参数抽取和回答组织；
- 用户身份只从 FastAPI 鉴权结果和受保护的 LangGraph Runtime Context 注入；
- 日期、金额、汇率、预算执行率、盈亏和异常指标均由 Python 确定性计算；
- 财务事实、知识库事实、分析建议和风险提示在回答中明确区分；
- 所有知识性结论继续使用可信结构化引用；
- 所有财务数值携带统计期间、币种、数据时间和数据完整性说明；
- 当前阶段不实现自然语言记账、预算修改、流水删除或持仓调整。

#### 阶段五目标工作流

```text
用户问题
  ↓
身份、会话和输入校验
  ↓
意图分类
  ├── 通用财务知识
  ├── 个人收支或账户查询
  ├── 投资持仓或行情查询
  ├── 财务数据与知识库混合问题
  └── 高风险投资建议
  ↓
实体、时间范围、币种和对比口径解析
  ↓
生成受控执行计划
  ├── 知识问题：执行 RAG
  ├── 财务问题：调用白名单财务工具
  ├── 混合问题：分别执行 RAG 和财务工具后汇合
  └── 高风险问题：在所需查询之外启用强化风险策略
  ↓
执行确定性财务分析
  ↓
生成回答
  ↓
校验财务证据、知识引用、Groundedness 和风险提示
  ↓
由 ChatService 原子保存消息、引用、证据和运行记录
  ↓
通过现有 SSE 链路返回浏览器
```

模型生成的工具计划必须经过 Pydantic Schema 和服务器白名单校验。计划无效时最多执行
一次受控修复；仍无法确定日期、币种或查询对象时，应要求用户澄清，不得猜测参数或
改为执行宽范围查询。

原始阶段范围与开发批次的对应关系如下：

| 原始能力 | 开发批次 | 主要交付 |
| --- | --- | --- |
| 财务摘要工具 | P5.1 | `get_finance_summary` |
| 收支查询工具 | P5.1 | `get_income_expense_report` |
| 流水搜索工具 | P5.1 | `search_transactions` |
| 账户余额工具 | P5.1 | `get_account_balances` |
| 预算状态工具 | P5.2 | `get_budget_status` |
| 持仓分析工具 | P5.2 | `get_portfolio_summary`、`get_holding_performance` |
| 行情快照工具 | P5.2 | `get_market_snapshot` |
| 时间范围解析 | P5.3 | 相对时间、显式区间和对比窗口 |
| 币种和汇率处理 | P5.3 | 分币种展示、汇率快照和受控换算 |
| 开支异常分析 | P5.4 | `analyze_expense_anomalies`：区间对比、分类贡献和稳健异常规则 |
| 预算建议 | P5.4 | `get_budget_advice`：预算预测、剩余额度和可解释建议 |
| 财务数据与知识库联合回答 | P5.1、P5.4 | 混合路由、可信引用、财务证据和风险策略 |

#### P5.1：财务工具契约和最小 Agent 闭环

第一批只交付截图中确认的最小财务 Agent，控制单次开发范围：

- [x] 定义统一的财务工具输入、输出、错误和审计契约；
- [x] `get_finance_summary`：返回指定区间和单一币种的收支、净现金流、账户余额及预算摘要；
- [x] `get_account_balances`：返回当前用户按币种分组的有效账户余额；
- [x] `search_transactions`：按日期、类型、分类、账户、币种和关键词执行有界流水搜索；
- [x] `get_income_expense_report`：返回收支合计、分类明细及可选对比区间；
- [x] LangGraph 问题分类、实体抽取、受控工具路由和失败澄清；
- [x] 基于个人财务数据生成回答；
- [x] 财务数据与知识库联合回答；
- [x] 在现有聊天界面展示“查询财务数据”和“查询知识库”的运行状态。

P5.1 于 2026-08-01 完成：现有回答图升级为 `finance-agent-p5.1-v1`，工具调用仅允许
服务端白名单且用户身份由可信上下文绑定；财务工具审计快照随 Agent Run 持久化，聊天
SSE 增加“理解问题”和“查询个人财务数据”状态。后端 110 项测试、前端 17 项组件测试、
Ruff、Mypy、Alembic 检查、前端类型检查与生产构建均通过；真实 PostgreSQL 集成测试已
覆盖四个工具及跨用户隔离，重建后的 API 容器健康检查通过。

最小版本验收后，用户应能在同一会话中完成以下场景：

- “我这个月收入、支出和净现金流是多少？”；
- “我的 CNY 账户余额分别是多少？”；
- “查找上个月餐饮类支出”；
- “本月餐饮支出为什么比上月高，应该如何调整？”；
- “结合知识库中的预算原则分析我的实际预算执行情况”。

#### P5.2：完整只读工具集

在最小闭环稳定后补齐以下工具：

- [x] `get_budget_status`：返回预算额度、已用、剩余、执行率和覆盖区间；
- [x] `get_portfolio_summary`：返回投资组合成本、市值、未实现盈亏和价格完整性；
- [x] `get_holding_performance`：按持仓或证券代码返回成本、最新价格和收益表现；
- [x] `get_market_snapshot`：返回行情价格、币种、来源和观测时间；
- [x] 持仓分析和行情缺失时的明确降级回答。

P5.2 于 2026-08-01 完成：财务工具白名单扩展为 8 个只读工具，预算执行按预算自身
覆盖区间与请求窗口的交集统计；持仓估值按币种匹配最新行情并确定性计算未实现盈亏和
收益率。行情缺失、行情超过可配置新鲜度阈值、零成本收益率不可计算、空持仓、空预算、
结果截断和查询超时均返回结构化警告或稳定错误，不会生成虚构价格和估值。回答图升级为
`finance-agent-p5.2-v1`，投资组合、单证券持仓、预算状态和行情问题已经进入现有受控聊天
链路。真实 PostgreSQL 全量后端 119 项测试、前端 17 项组件测试、Ruff、Mypy、Alembic
检查、前端类型检查与生产构建均已通过；重建后的 API 容器健康检查通过，默认行情
新鲜度阈值为 72 小时且已正确注入运行环境。

所有工具必须遵守以下契约：

- 输入参数中不存在 `user_id`；
- 从可信运行上下文注入当前用户，并继续使用应用层过滤与 PostgreSQL RLS；
- 流水明细、账户和持仓结果设置最大返回数量，不接受任意排序或 SQL；
- 金额、数量、百分比和汇率使用 `Decimal` 或数据库定点数；
- 输出统一包含工具名、规范化参数、统计期间、币种、`data_as_of`、结果和警告；
- 不向模型传递完成回答所不需要的敏感流水描述；
- 数据缺失、行情过期或查询超时时返回结构化警告，不生成虚构数据。

#### P5.3：时间范围、币种和汇率

- [x] 实现显式日期区间及“今天、昨天、本周、上周、本月、上月、本季度、今年、最近
  N 天”等相对时间解析；
- [x] 实现“同比、环比、相比上月”等对比窗口；
- [x] 使用服务端注入的当前时间和配置时区，模型不能自行决定当前日期；
- [x] 日期区间继续使用现有包含首尾日期的财务报表语义；
- [x] 未指定目标币种时按币种分组展示，禁止将不同币种直接相加；
- [x] 新增 `exchange_rate_snapshots`，记录基础币种、报价币种、汇率、来源和观测时间；
- [x] 指定目标币种时仅使用可审计且满足新鲜度要求的汇率快照；
- [x] MVP 只支持直接或反向汇率，不进行不可审计的多跳换算；
- [x] 汇率缺失或过期时明确提示无法完成换算，并保留原币种结果。

P5.3 于 2026-08-02 完成：新增独立的确定性时间解析模块，显式区间、自然日/周/月/
季度/年、最近 N 天及同比、等长环比、相比上月均由服务端当前日期解析，默认使用可配置的
`Asia/Shanghai` IANA 时区，日期边界保持包含首尾。财务摘要、账户余额、收支报表、预算
状态和投资组合在未指定 `target_currency` 时返回原币种分组；指定目标币种时，保留所有
原币种事实，并使用 `finance.exchange_rate_snapshots` 中满足 24 小时默认新鲜度阈值的
单个直接或反向快照生成换算汇总。工具结果同时返回原始汇率、应用汇率、方向、来源和
观测时间；缺失或过期时不换算、不多跳，并返回结构化警告。迁移
`20260802_0011`、回答图 `finance-agent-p5.3-v1`、管理员汇率发布/查询接口、137 项后端
测试、Ruff、Mypy 和 Alembic 一致性检查均已通过。

#### P5.4：开支异常分析和预算建议

- [x] 当前区间与等长前一区间比较，计算变化金额、变化比例和分类贡献；
- [x] 历史窗口充足时使用中位数和 MAD 等稳健统计识别异常；
- [x] 样本不足、历史基数为零或分类变化时不下确定性异常结论；
- [x] 异常分析只描述数据驱动项，不把相关流水表述为已经证明的因果关系；
- [x] 基于已发生支出、剩余预算、时间进度和历史支出计算预计期末支出；
- [x] 给出剩余日均可用额度、预计超支额和可解释的预算调整方向；
- [x] 涉及通用预算比例或投资原则时必须检索知识库并附可信引用；
- [x] 高风险投资问题统一增加风险提示，禁止承诺收益或给出确定性买卖结论。

P5.4 于 2026-08-02 完成：财务工具白名单扩展为 10 个只读工具。新增
`analyze_expense_anomalies`，以当前区间的相邻等长前窗为对比基准，输出变化金额、变化
比例和分类移动贡献；历史有效样本不少于 4 个且 MAD 非零时才生成稳健异常结论，零基数、
样本不足以及分类新增或消失均返回不可确定的结构化结论。新增 `get_budget_advice`，结合
预算期已发生支出、时间进度、当前日均和至少 2 个历史有效期间的中位数，输出期末预测、
预计超支、剩余日均可用额度、预测依据和确定性调整代码。不同原币种的异常信号和预算预测
分别换算展示，不跨币种合并统计信号；汇率仍沿用 P5.3 的直接/反向快照证据和新鲜度约束。
回答图升级为 `finance-agent-p5.4-v1`，预算原则和投资原则问题强制进入知识检索，高风险投资
问题在最终校验节点清理收益承诺及确定性买卖表述，并追加统一风险提示。148 项后端测试、
Ruff、Mypy、Alembic 一致性检查和真实 PostgreSQL 跨用户隔离集成测试均通过；重建后的
API、Worker 和 Beat 已加载新版本，API 存活与依赖就绪检查通过。P5.4 未新增数据库表，
继续使用 P5.3 的迁移头 `20260802_0011`。

#### P5.5：运行记录、财务证据和前端展示

建议通过新的 Alembic 迁移补充以下持久化结构：

- `chat.agent_tool_calls`：工具名、规范化参数、状态、耗时、数据时间、结果摘要和错误码；
- `chat.message_evidence`：回答使用的财务事实快照及其工具调用来源；
- `finance.exchange_rate_snapshots`：可审计的汇率快照。

上述包含用户数据的记录必须启用 RLS。工具审计默认不保存完整敏感流水描述，可保存聚合
摘要、必要证据和结果摘要哈希。`agent_runs.detail` 继续保存图版本、执行计划摘要、工具数量
和模型诊断信息，不将全部工具结果长期堆叠在单个 JSON 字段中。

现有聊天 API 和前端按向后兼容方式扩展：

- [x] SSE 用户可见阶段增加问题理解、财务查询、知识检索、分析、生成和最终校验；
- [x] 回答区区分“个人财务数据”“知识库依据”“分析建议”和“风险提示”；
- [x] 展示统计期间、币种、数据更新时间、行情或汇率时间；
- [x] 知识事实继续使用现有引用原文查看能力；
- [x] 财务事实展示来源工具和计算口径，但不伪装成文档引用；
- [x] 保持停止生成、断线恢复、重新生成、失败重试和历史会话兼容。

P5.5 于 2026-08-02 完成：迁移 `20260802_0012` 新增 `chat.agent_tool_calls` 和
`chat.message_evidence`，两表均启用并强制 PostgreSQL RLS，通过复合租户外键分别绑定
`agent_runs`、`messages` 和工具调用来源。工具审计保存规范化且脱敏的参数、状态、耗时、
数据时间、结果摘要、错误码和 SHA-256 结果哈希；消息证据保存回答实际使用的确定性财务
数值、统计区间、币种、警告和计算口径，并递归移除流水描述、搜索词和内部资源标识。
`agent_runs.detail` 不再保存完整工具结果，只保留意图、检索摘要、工具数量与状态、数据时间、
风险策略和模型诊断。聊天 API、SSE 完成事件和历史会话响应按向后兼容方式增加财务证据、
数据更新时间和风险提示，运行摘要增加工具数量；回答图升级为 `finance-agent-p5.5-v1`，
用户可见阶段完整覆盖问题理解、财务查询、知识检索、分析、生成和最终校验。聊天前端新增
独立的“个人财务数据”“分析建议”“知识库依据”和“风险提示”区域，展示来源工具、统计
期间、币种、数据/行情/汇率观测时间及计算口径，原有可点击知识引用、停止、恢复、重新生成
和失败重试链路保持兼容。151 项后端测试、18 项前端测试、Ruff、Mypy、前端类型检查、
ESLint、生产构建、Alembic 一致性和真实 PostgreSQL 持久化/隔离测试均已通过。

#### P5.6：测试、评测和交付验收

阶段五需要增加以下测试矩阵：

- [ ] 时间解析边界：月末、年末、闰年、时区和相对时间；
- [ ] 财务工具 Schema、参数上限、空结果和异常结果；
- [ ] Decimal 精度、预算执行率、持仓盈亏和汇率换算；
- [ ] 纯知识、纯财务、投资、混合和高风险问题路由；
- [ ] 开支异常与预算建议在正常、零基数和样本不足情况下的行为；
- [ ] 用户 A 无法通过问题、工具参数、Checkpoint 或恢复接口查询用户 B 数据；
- [ ] 模型伪造 `user_id`、工具名、金额、行情和引用时被拒绝；
- [ ] SSE 状态、停止、恢复、重试、重新生成和历史消息展示；
- [ ] 财务证据、知识引用、风险提示和数据更新时间持久化；
- [ ] 真实浏览器端的最小财务 Agent 和混合回答冒烟。

阶段五完成标准：

1. 本节列出的 11 项原始阶段五能力全部完成；
2. Agent 不注册任何财务写工具；
3. 跨用户财务数据泄漏数量为零；
4. 每个财务数值均可追溯到确定性工具结果和计算口径；
5. 不同币种未经有效汇率转换不会被合并；
6. 知识性结论具有可信引用，高风险回答具有风险提示；
7. 数据不足时能够澄清或降级，不编造余额、流水、行情和汇率；
8. 后端 Pytest、Ruff、Mypy、Alembic 检查，前端类型、Lint、组件测试和生产构建全部通过；
9. 完成真实模型、真实数据库和浏览器端核心场景验收；
10. 更新当前交接文档、API 契约、评测说明和阶段状态。

### 阶段六：企业级加固

- [x] PostgreSQL RLS 基础；
- [x] 审计日志基础；
- [x] 登录接口单 IP、全局及失败次数限流；
- [x] Refresh Token HttpOnly Cookie 与轮换；
- [x] XLSX 导入行数、解压大小和压缩比防护；
- [x] 敏感配置无可用默认值及启动校验；
- [ ] 用户和模型配额；
- [x] Checkpoint 加密；
- [ ] 日志脱敏；
- [ ] 缓存；
- [ ] OpenTelemetry；
- [ ] Prometheus 和 Grafana；
- [ ] RAG 回归评测；
- [ ] Prompt Injection 测试；
- [ ] 压力测试；
- [ ] 备份和恢复；
- [ ] 灰度发布和回滚。

阶段六尚未整体完成。上方已勾选的是阶段一至阶段四期间提前落地的安全基线，不能替代后续
对配额、可观测性、压力测试、备份恢复和发布流程的完整验收。

### 阶段七：后续增强

- [ ] 自然语言记账；
- [ ] Human-in-the-loop 写操作；
- [ ] 预算自动生成；
- [ ] 财务报告自动生成；
- [ ] 投资组合风险报告；
- [ ] 多模型路由；
- [ ] 本地模型部署；
- [ ] 移动端适配；
- [ ] 通知和定期报告；
- [ ] MCP Server。

## 18. 建议的第一版目录结构

```text
agent_aurum/
├── app/
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── conversations.py
│   │   ├── accounts.py
│   │   ├── transactions.py
│   │   ├── budgets.py
│   │   ├── holdings.py
│   │   ├── knowledge_bases.py
│   │   ├── documents.py
│   │   └── projects.py
│   ├── agents/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── nodes/
│   │   ├── tools/
│   │   └── policies/
│   ├── rag/
│   │   ├── loaders/
│   │   ├── splitters/
│   │   ├── embeddings/
│   │   ├── retrievers/
│   │   ├── rerankers/
│   │   └── citations/
│   ├── finance/
│   │   ├── calculators/
│   │   ├── importers/
│   │   ├── summaries/
│   │   └── validators/
│   ├── providers/
│   │   ├── identity.py
│   │   ├── finance.py
│   │   ├── market.py
│   │   ├── model_provider.py
│   │   └── object_storage.py
│   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   └── session.py
│   ├── services/
│   ├── workers/
│   ├── observability/
│   ├── security/
│   ├── config.py
│   └── main.py
├── web/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   └── rag_eval/
├── evals/
├── scripts/
├── deploy/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── project_introduction/
    ├── README.md
    ├── aurum-agent-current-handoff.md
    └── 其他架构、方案和历史交接文档
```

该目录结构已在阶段一完成后落地。结合已实现的安全底座，实际结构额外保留了
`app/api/schemas/`、`app/db/base.py`、`app/db/bootstrap.py`、
`app/providers/vector_store.py`、`app/errors.py` 和 `app/cli.py`；
这些文件分别承担 API 数据契约、ORM 公共基类、数据库权限初始化、向量存储抽象、
统一异常和运维命令职责。尚未实现的阶段性模块目前只保留清晰的包或端点骨架，
不会被注册为可用 API。

## 19. 待讨论事项

### 19.1 模型部署

待确定：

- MVP 使用云模型还是本地模型；
- 是否允许个人财务数据发送到云模型；
- 是否需要先进行字段脱敏；
- 是否需要支持多个模型提供商。

初步建议：

- 建立 OpenAI-compatible 模型适配层；
- MVP 先使用云 API；
- 保留切换本地 vLLM 的能力；
- 不在业务代码中硬编码模型名称。

### 19.2 Agent 写权限

待确定：

- 是否允许 Agent 创建和修改流水；
- 是否允许 Agent 调整预算；
- 是否允许 Agent 修改持仓。

初步建议：

- V1 完全只读；
- V2 通过 Human-in-the-loop 增加写操作。

### 19.3 知识库可见范围

待确定：

- 所有普通用户是否共享同一套知识库；
- 是否存在项目级知识库；
- 是否需要用户组权限；
- 是否允许用户拥有私人知识库。

初步建议：

- 管理员维护统一知识库；
- 普通用户只能查询已发布知识；
- 个人财务数据始终按用户隔离；
- 数据模型预留项目级和用户级可见范围。

### 19.4 前端位置

初步建议：

- Vue 3 前端放在 `E:\agent_aurum\web`；
- Python 后端放在 `E:\agent_aurum\app`；
- 前后端在同一仓库独立管理依赖；
- 生产环境通过统一域名和 Caddy 或 Nginx 路由。

### 19.5 规模目标

详细技术参数仍需确认：

- 预计用户数量；
- 同时在线用户数量；
- 文档数量和总容量；
- 文档更新频率；
- 是否需要 OCR；
- 目标响应时间；
- 预算和服务器配置。

### 19.6 未来外部系统集成

当前版本不依赖任何外部财务项目，但需要预留以下抽象接口：

```python
class IdentityProvider: ...
class FinanceDataProvider: ...
class MarketDataProvider: ...
class KnowledgeRepository: ...
```

当前默认实现均位于本项目：

```text
IdentityProvider      → LocalIdentityProvider
FinanceDataProvider   → LocalPostgresFinanceProvider
MarketDataProvider    → LocalMarketDataProvider
KnowledgeRepository  → PgVectorKnowledgeRepository
```

未来如需和其他系统拉通，应新增 REST、OIDC 或消息事件适配器，不直接共享业务数据库，也不修改 LangGraph 的核心工作流。

## 20. 初步结论

推荐方案为：

1. 在 `agent_aurum` 中建设可独立运行的 Python、FastAPI、LangGraph 应用；
2. 用户、鉴权、财务数据、知识库、会话和管理能力全部在当前项目内闭环；
3. 非结构化财务知识使用 RAG；
4. 个人收支和投资持仓使用受控的确定性工具；
5. 使用 PostgreSQL、pgvector、Redis 和对象存储；
6. 使用产品会话表和 LangGraph Checkpoint 双重持久化；
7. 管理员负责项目和知识库管理；
8. 普通用户只能进行知识问答；
9. V1 Agent 保持只读；
10. 从权限隔离、引用追踪、可观测性和自动化评测开始建设企业级能力；
11. 其他项目只作为未来可选集成对象，不构成当前开发依赖。

## 21. 参考资料

- [LangChain Retrieval](https://docs.langchain.com/oss/python/langchain/retrieval)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [pgvector](https://github.com/pgvector/pgvector)
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Qwen3 Embedding](https://qwenlm.github.io/blog/qwen3-embedding/)
- [BGE-M3](https://bge-model.com/bge/bge_m3.html)
