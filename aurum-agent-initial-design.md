# Aurum 金融财务管理与投资知识问答 Agent 初步方案

> 文档状态：初步方案，待讨论确认  
> 项目目录：`E:\agent_aurum`  
> 编写日期：2026-07-23

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

`E:\agent_aurum\main.py` 当前只是一个最小 LangChain 示例。

该目录后续将建设为一个可独立启动、部署和使用的完整 Agent 项目，主要承载：

- 用户注册、登录、鉴权和角色管理；
- FastAPI 接口；
- LangGraph 工作流；
- RAG 检索；
- 文档解析和索引；
- 多用户、多会话和历史记录；
- 账户、收支、存款、持仓等结构化财务数据；
- Agent 工具；
- 模型适配；
- RAG 评测；
- 异步文档处理任务；
- 浏览器管理和问答界面。

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
- `rewrite_query`
- `plan_retrieval`
- `retrieve_knowledge`
- `call_finance_tools`
- `call_market_tools`
- `rerank_context`
- `grade_context`
- `generate_answer`
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
- 初始密码：`123456`

安全要求：

- 数据库只保存 Argon2id 或 bcrypt 哈希；
- 初始化过程必须幂等；
- 服务重启不得覆盖管理员密码；
- 推荐管理员首次登录强制修改密码；
- 生产环境允许通过安全环境变量覆盖初始密码；
- 不得在日志中输出初始密码。

计划中的登录接口采用：

```json
{
  "identifier": "admin",
  "password": "123456"
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
- `feedback`

这些表用于：

- 会话列表；
- 历史消息；
- 会话搜索；
- 引用追踪；
- 用户反馈；
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

- [ ] 账户管理；
- [ ] 收入和支出流水管理；
- [ ] 预算管理；
- [ ] 股票和基金持仓管理；
- [ ] 投资交易记录；
- [ ] 行情快照；
- [ ] CSV 和 Excel 账单导入；
- [ ] 月度收支聚合；
- [ ] 财务数据用户隔离；
- [ ] 财务数据查询和统计测试。

### 阶段三：知识库管理

- [ ] 项目管理；
- [ ] 知识库管理；
- [ ] 文档上传；
- [ ] 对象存储；
- [ ] PDF、DOCX、Markdown、TXT 解析；
- [ ] CSV、XLSX 解析；
- [ ] 异步任务；
- [ ] 分块；
- [ ] Embedding；
- [ ] pgvector 索引；
- [ ] 文档版本；
- [ ] 任务进度和失败重试。

### 阶段四：基础 RAG 问答

- [ ] LangGraph 状态定义；
- [ ] Hybrid Retrieval；
- [ ] Reranker；
- [ ] 回答生成；
- [ ] SSE 流式输出；
- [ ] 结构化引用；
- [ ] 引用原文查看；
- [ ] 会话和消息保存；
- [ ] LangGraph Postgres Checkpoint；
- [ ] 历史会话恢复。

### 阶段五：个人财务 Agent

- [ ] 财务摘要工具；
- [ ] 收支查询工具；
- [ ] 流水搜索工具；
- [ ] 账户余额工具；
- [ ] 持仓分析工具；
- [ ] 行情快照工具；
- [ ] 时间范围解析；
- [ ] 币种和汇率处理；
- [ ] 开支异常分析；
- [ ] 预算建议；
- [ ] 财务数据与知识库联合回答。

### 阶段六：企业级加固

- [ ] PostgreSQL RLS；
- [ ] 审计日志；
- [ ] API 限流；
- [ ] 用户和模型配额；
- [ ] Checkpoint 加密；
- [ ] 日志脱敏；
- [ ] 缓存；
- [ ] OpenTelemetry；
- [ ] Prometheus 和 Grafana；
- [ ] RAG 回归评测；
- [ ] Prompt Injection 测试；
- [ ] 压力测试；
- [ ] 备份和恢复；
- [ ] 灰度发布和回滚。

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
└── README.md
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
