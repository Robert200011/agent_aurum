# Aurum Agent 部署上线与运维方案

> 文档状态：持续维护中的部署方案
> 项目目录：`E:\agent_aurum`
> 文档分类目录：`project_introduction/`
> 对应设计文档：[Aurum Agent 总体技术方案](./aurum-agent-initial-design.md)
> 编写日期：2026-07-23
> 最后更新：2026-08-03

## 1. 文档目标

本文档用于规划 `agent_aurum` 的开发环境、测试环境和生产环境部署流程，覆盖：

- 生产部署拓扑；
- Docker 镜像和 Docker Compose；
- 域名、HTTPS 和网络访问；
- 环境变量及密钥；
- 数据库迁移；
- 管理员初始化；
- 首次上线；
- 日常版本发布；
- 健康检查和冒烟测试；
- 日志、监控和告警；
- 数据备份与恢复；
- 版本回滚；
- 服务扩容；
- 常见故障处理。

### 1.1 当前落地边界

截至 2026-08-03，阶段一至阶段六工程开发已经完成。仓库已具备开发 Compose、生产蓝绿
Compose、Caddy Gateway、API/Web 镜像、对象存储、Worker、LangGraph/RAG、Prometheus、
Grafana、OpenTelemetry、加密备份恢复、发布清单、回滚脚本和 GitHub Actions 门禁。
阶段六通过 PR #11 合入 `master`，当前功能基线为 `e8aa6ea`。

这些资产已经通过本地发布与故障回滚演练，但仍不等同于完成公网生产部署。正式上线必须
在候选服务器配置域名/TLS、镜像 digest、外部密钥和异地备份，并复跑真实 Provider、目标
容量、隔离恢复和人工切流门禁。

## 2. 部署策略

### 2.1 初期推荐方案

项目初期推荐使用：

- 一台 Linux 服务器；
- Docker Engine；
- Docker Compose；
- Caddy 或 Nginx；
- 云端 LLM API；
- 云端或本地 Embedding 服务；
- PostgreSQL + pgvector；
- Redis；
- S3 兼容对象存储。

该方案适用于：

- 个人项目；
- 小规模团队；
- 初期用户量；
- 需要快速上线；
- 暂时不需要 Kubernetes 的阶段。

### 2.2 后期扩展方案

当出现以下情况时，再考虑 Kubernetes 或托管容器平台：

- FastAPI 需要多个副本；
- 文档解析任务量明显增长；
- Embedding 和 Reranker 需要独立 GPU；
- Worker 需要根据队列自动扩缩容；
- 需要跨可用区高可用；
- 单机故障已经无法满足可用性要求。

当前阶段不建议为了“企业级”标签提前引入 Kubernetes。企业级能力应优先体现在权限、审计、可恢复、可观测、备份和发布安全上。

## 3. 推荐生产拓扑

```text
Internet
   │
   ▼ 80 / 443
Caddy / Nginx
   ├── Vue 3 静态文件
   └── /api、/health、SSE
              │
              ▼
         FastAPI API
              │
              ├── LangGraph Agent
              ├── 用户与 RBAC
              ├── 项目和知识库管理
              ├── 会话和消息
              ├── 财务数据服务
              └── 管理和审计 API
                      │
                      ├── PostgreSQL + pgvector
                      ├── Redis
                      ├── S3 / MinIO
                      ├── Celery Worker
                      ├── Celery Beat
                      ├── Embedding / Reranker
                      └── LLM Provider
```

### 3.1 服务列表

| 服务 | 建议服务名 | 职责 | 是否暴露公网 |
|---|---|---|---|
| 反向代理 | `gateway` | HTTPS、静态文件、API 转发 | 是，仅 80/443 |
| 前端构建 | `web` | 构建 Vue 3 静态文件 | 否 |
| API | `api` | FastAPI、LangGraph、鉴权、SSE | 否 |
| 文档 Worker | `worker_ingestion` | 解析、OCR、分块、Embedding | 否 |
| 通用 Worker | `worker_default` | 报告、异步业务任务 | 否 |
| 定时任务 | `scheduler` | 清理、快照、定期任务 | 否 |
| 数据库 | `postgres` | 业务数据、向量、Checkpoint | 否 |
| 缓存和队列 | `redis` | 缓存、限流、Celery Broker | 否 |
| 对象存储 | `minio` | 原始文档和解析产物 | 否 |
| 监控 | `prometheus` | 指标采集 | 默认否 |
| 仪表板 | `grafana` | 指标展示 | 建议仅内网或鉴权后访问 |

### 3.2 端口原则

生产服务器对外只开放：

- `80/tcp`：跳转到 HTTPS；
- `443/tcp`：浏览器和 API；
- SSH 管理端口：仅允许可信 IP。

以下端口只允许 Docker 内部网络或受控内网访问：

- FastAPI；
- PostgreSQL；
- Redis；
- MinIO；
- Prometheus；
- Grafana；
- Embedding；
- Reranker；
- 本地 LLM。

禁止直接将 PostgreSQL、Redis、MinIO 管理端口暴露到公网。

## 4. 推荐部署目录

项目后续应建设以下部署文件：

```text
agent_aurum/
├── app/
├── web/
├── migrations/
├── deploy/
│   ├── docker-compose.dev.yml
│   ├── docker-compose.test.yml
│   ├── docker-compose.prod.yml
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── Dockerfile.web
│   ├── Caddyfile
│   ├── env/
│   │   ├── development.env.example
│   │   ├── test.env.example
│   │   └── production.env.example
│   ├── scripts/
│   │   ├── deploy.sh
│   │   ├── migrate.sh
│   │   ├── init-admin.sh
│   │   ├── backup.sh
│   │   ├── restore.sh
│   │   ├── rollback.sh
│   │   └── smoke-test.sh
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── grafana/
│       └── provisioning/
├── pyproject.toml
├── alembic.ini
├── .env.example
└── project_introduction/
    ├── README.md
    └── 其他项目介绍、架构和交接文档
```

生产部署文件应与开发环境文件分开，避免开发配置被误用于生产。

## 5. 环境划分

### 5.1 开发环境

目标：

- 本地快速启动；
- 支持热更新；
- 允许调试日志；
- 使用测试数据；
- 可以使用本地 MinIO；
- 可以使用内存或开发 Checkpointer。

开发环境不得连接生产数据库和生产对象存储。

### 5.2 测试环境

目标：

- 接近生产配置；
- 执行数据库迁移测试；
- 执行权限和跨用户隔离测试；
- 执行 RAG 回归评测；
- 执行 SSE 和 Worker 测试；
- 执行发布和回滚演练。

测试环境应使用独立数据库、Redis、对象存储桶和模型配额。

### 5.3 生产环境

要求：

- 禁止热更新；
- 禁止 Debug 模式；
- 禁止默认密钥；
- 禁止使用 `latest` 镜像；
- 强制 HTTPS；
- 启用日志脱敏；
- 启用数据库连接池；
- 启用健康检查；
- 启用备份；
- 启用监控和告警；
- 使用正式域名。

## 6. 生产环境变量和密钥

生产环境配置建议通过服务器环境文件、Docker Secret 或密钥管理系统注入。

示例：

```dotenv
AURUM_APP_NAME=Aurum Agent
AURUM_ENVIRONMENT=production
AURUM_DEBUG=false
AURUM_SERVER_HOST=0.0.0.0
AURUM_SERVER_PORT=8010

AURUM_DATABASE_URL=postgresql+asyncpg://aurum_app:<由密钥系统注入>@postgres:5432/aurum
AURUM_MIGRATION_DATABASE_URL=postgresql+asyncpg://aurum_owner:<由密钥系统注入>@postgres:5432/aurum
AURUM_DATABASE_POOL_SIZE=20
AURUM_DATABASE_MAX_OVERFLOW=20
AURUM_REDIS_URL=redis://:<由密钥系统注入>@redis:6379/0

AURUM_JWT_SECRET_KEY=<由密钥系统注入的高强度随机值>
AURUM_ACCESS_TOKEN_TTL_MINUTES=15
AURUM_REFRESH_TOKEN_TTL_DAYS=30
AURUM_REFRESH_TOKEN_COOKIE_SECURE=true
AURUM_REFRESH_TOKEN_COOKIE_SAMESITE=lax

AURUM_ADMIN_USERNAME=admin
AURUM_ADMIN_INITIAL_PASSWORD=<一次性高强度随机密码>
AURUM_BOOTSTRAP_ADMIN=true

AURUM_CORS_ORIGINS=["https://agent.example.com"]
AURUM_LOG_LEVEL=INFO
```

上例只包含当前代码已经支持的配置。LangGraph 加密、对象存储、模型、Embedding、
Reranker、Celery、OpenTelemetry 和 Prometheus 等变量应在相应功能落地后再加入，
不能提前假定名称或实现已经确定。

### 6.1 密钥管理要求

- 生产 `.env` 不得提交到 Git；
- `.env.example` 中的敏感字段必须留空；
- JWT 密钥不得写入代码、镜像或 Compose 默认值；
- 数据库密码和 Redis 密码必须随机生成；
- 模型 API Key 不得出现在日志；
- `LANGGRAPH_AES_KEY` 必须单独备份；
- 密钥轮换需要有操作记录；
- 开发、测试、生产不能复用相同密钥。

### 6.2 初始管理员

满足产品要求的初始管理员：

- 用户名：`admin`
- 初始密码：无代码默认值，由密钥管理系统生成并注入一次性高强度随机值

生产要求：

- 只有显式设置 `AURUM_BOOTSTRAP_ADMIN=true` 时才允许初始化；
- 只在首次初始化时使用；
- 数据库只保存密码哈希；
- 初始化脚本必须幂等；
- 管理员存在时不得自动重置密码；
- 第一次登录必须修改密码；
- 初始化成功后设置 `AURUM_BOOTSTRAP_ADMIN=false`，并删除初始密码配置；
- 日志不得打印初始密码。

## 7. 服务器准备

### 7.1 推荐系统

建议使用受支持的 Linux 服务器发行版，并安装：

- Docker Engine；
- Docker Compose；
- Git 或容器镜像仓库凭据；
- 防火墙；
- 时间同步服务；
- 基础磁盘监控。

### 7.2 初期资源建议

如果 LLM 和 Embedding 均使用外部 API，可以从以下资源级别开始评测：

- 4 vCPU；
- 8 GB 内存；
- 100 GB SSD；
- 独立备份存储。

该配置只是初始基线，正式容量应根据以下测试结果调整：

- 同时在线用户；
- SSE 并发连接；
- 文档解析并发；
- 文档体积；
- pgvector 数据量；
- Worker 峰值内存；
- 数据库磁盘增长。

如果需要本地运行 Embedding、Reranker 或 LLM，应单独评估 CPU、内存、显存和模型并发，不应直接沿用上述配置。

### 7.3 域名和 DNS

上线前准备：

1. 申请域名或子域名；
2. 将 A/AAAA 记录指向生产服务器；
3. 确认 80 和 443 端口可访问；
4. 配置 Caddy 或 Nginx；
5. 验证 HTTPS 证书；
6. 配置 HSTS、安全响应头和上传大小限制。

## 8. 容器镜像策略

### 8.1 镜像

建议构建：

```text
aurum-agent-api:<version>
aurum-agent-worker:<version>
aurum-agent-web:<version>
```

API 和 Worker 可以复用同一个 Python 基础镜像，但应通过不同启动命令运行。

### 8.2 版本标签

推荐使用：

- Git Commit SHA；
- 语义化版本，例如 `v0.1.0`；
- 发布候选版本，例如 `v0.1.0-rc.1`。

禁止生产环境使用：

```text
latest
```

每次部署必须能够明确知道：

- 使用了哪个代码提交；
- 使用了哪个镜像；
- 使用了哪个数据库迁移版本；
- 使用了哪个前端版本；
- 使用了哪些模型配置。

### 8.3 构建要求

- 使用多阶段构建；
- 使用非 root 用户运行应用；
- 不将密钥复制进镜像；
- 固定依赖版本；
- 构建阶段执行测试；
- 扫描依赖和镜像漏洞；
- 保持镜像尽量精简；
- 为 API 和 Worker 设置明确启动命令。

## 9. 首次上线流程

以下命令是目标部署流程示例，需在对应 Compose 文件和脚本实现后才能执行。

### 9.1 获取代码或镜像

代码部署方式：

```bash
git clone <repository-url> /opt/aurum-agent
cd /opt/aurum-agent
git checkout <release-tag>
```

镜像部署方式：

```bash
docker compose -f deploy/docker-compose.prod.yml pull
```

推荐生产服务器拉取已通过 CI 构建和测试的镜像，而不是在生产服务器临时构建。

### 9.2 创建生产配置

```bash
cp deploy/env/production.env.example deploy/env/production.env
```

然后填写：

- 数据库密码；
- Redis 密码；
- JWT 密钥；
- Checkpoint 加密密钥；
- 对象存储密钥；
- 模型 API Key；
- 域名；
- 初始管理员信息。

生产配置完成后应限制文件权限。

### 9.3 启动基础设施

先启动：

```bash
docker compose -f deploy/docker-compose.prod.yml up -d postgres redis minio
```

然后等待以下检查通过：

- PostgreSQL 可连接；
- pgvector 扩展可用；
- Redis `PING` 成功；
- 对象存储桶存在；
- 持久化目录或卷可写。

### 9.4 执行数据库迁移

目标命令：

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm api alembic upgrade head
```

要求：

- 迁移前自动备份；
- 迁移只能由一个一次性任务执行；
- API 多副本不能同时自动迁移；
- 迁移脚本必须经过测试环境验证；
- 大表迁移需要评估锁表时间；
- 优先使用向前兼容迁移。

### 9.5 初始化管理员

目标命令：

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm api aurum-agent bootstrap-admin
```

初始化程序需要：

- 检查用户名是否存在；
- 不存在时创建管理员；
- 使用安全密码哈希；
- 设置 `must_change_password=true`；
- 已存在时返回成功但不修改密码；
- 写入安全审计记录。

### 9.6 启动应用服务

```bash
docker compose -f deploy/docker-compose.prod.yml up -d api worker_ingestion worker_default scheduler web gateway
```

生产环境禁止：

- 使用 `--reload`；
- 开启 FastAPI Debug；
- 将异常堆栈返回给浏览器；
- 使用开发服务器直接暴露公网。

### 9.7 检查容器状态

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

需要确认：

- 所有必须服务处于运行状态；
- 健康检查通过；
- Worker 已连接队列；
- API 已连接数据库和 Redis；
- Caddy 或 Nginx 已加载证书；
- 无持续重启容器。

### 9.8 执行冒烟测试

```bash
deploy/scripts/smoke-test.sh
```

冒烟测试通过后，首次上线才算完成。

## 10. 健康检查

### 10.1 API 健康端点

FastAPI 应提供：

```text
GET /health/live
GET /health/ready
GET /metrics
```

### 10.2 存活检查

`/health/live` 只判断：

- API 进程是否存活；
- 事件循环是否能够响应。

该接口不应依赖所有外部服务，否则数据库短暂故障会导致容器被反复重启。

### 10.3 就绪检查

`/health/ready` 检查：

- PostgreSQL；
- Redis；
- 必要的对象存储；
- 数据库迁移版本；
- LangGraph Checkpointer；
- 必要配置是否加载。

Embedding、Reranker 和 LLM 可以根据系统策略标记为：

- 必须可用；
- 可降级；
- 暂时不可用但 API 仍可启动。

### 10.4 Worker 健康

Worker 健康指标至少包括：

- Worker 是否在线；
- 队列积压；
- 任务成功率；
- 任务失败率；
- 重试数量；
- 最老任务等待时间；
- 文档解析平均耗时；
- Embedding 平均耗时。

## 11. 上线后冒烟测试

自动化冒烟测试至少覆盖：

### 11.1 基础功能

- 首页能够打开；
- HTTPS 正常；
- API 能够响应；
- 未登录访问受保护 API 返回 401；
- 普通用户访问管理 API 返回 403。

### 11.2 用户和权限

- 注册；
- 用户名登录；
- 邮箱登录；
- Refresh Token；
- 修改密码；
- 登出；
- 管理员首次登录强制改密；
- 用户 A 无法访问用户 B 数据。

### 11.3 知识库

- 创建项目；
- 创建知识库；
- 上传测试文档；
- Worker 完成解析；
- 文档生成分块；
- Embedding 写入 pgvector；
- 文档状态变为可检索。

### 11.4 问答

- 新建会话；
- SSE 流式回答；
- 返回引用；
- 引用可打开；
- 刷新页面后恢复历史会话；
- 删除或归档会话；
- 知识不足时正确提示。

### 11.5 财务数据

- 创建账户；
- 写入测试流水；
- 查询月度收支；
- 查询账户余额；
- 创建测试持仓；
- Agent 只能查询当前用户数据；
- 金额和币种计算正确。

## 12. 日常版本发布

标准发布流程：

```text
提交代码
   ↓
静态检查和单元测试
   ↓
API、数据库和前端集成测试
   ↓
权限与 RAG 回归测试
   ↓
构建带版本号的镜像
   ↓
镜像安全扫描
   ↓
推送镜像仓库
   ↓
部署测试环境
   ↓
测试环境冒烟测试
   ↓
生产数据库备份
   ↓
执行兼容性迁移
   ↓
部署生产新版本
   ↓
健康检查和冒烟测试
   ├── 成功：完成发布
   └── 失败：回滚旧镜像
```

### 12.1 发布前检查

- 代码已经评审；
- 所有测试通过；
- 数据库迁移经过测试；
- 生产配置字段齐全；
- 镜像已推送；
- 当前生产版本已记录；
- 数据库备份成功；
- 回滚镜像仍然可用；
- 发布窗口和负责人明确。

### 12.2 发布命令示例

```bash
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps api worker_ingestion worker_default scheduler web
docker compose -f deploy/docker-compose.prod.yml ps
deploy/scripts/smoke-test.sh
```

生产发布脚本需要在任意一步失败时停止，并给出清晰错误信息。

## 13. 数据库迁移策略

### 13.1 原则

- 所有 Schema 变化通过 Alembic；
- 禁止手工修改生产表后不提交迁移；
- 每个发布版本记录迁移版本；
- 迁移脚本必须支持从当前生产版本升级；
- 先扩展、后迁移数据、最后删除旧字段；
- 避免在一次发布中立即删除仍被旧版本使用的字段。

### 13.2 兼容发布

推荐使用 Expand-Migrate-Contract：

1. 新增兼容字段或表；
2. 发布同时兼容新旧结构的应用；
3. 异步迁移历史数据；
4. 切换到新字段；
5. 后续版本删除旧字段。

这种方式便于应用镜像回滚。

### 13.3 禁止事项

- 未备份直接执行破坏性迁移；
- 自动执行未经验证的 `downgrade`；
- 在高峰期执行长时间锁表操作；
- 多个 API 副本同时运行迁移；
- 将数据修复脚本混入普通请求处理。

## 14. 备份策略

### 14.1 备份对象

至少备份：

- PostgreSQL 数据库；
- 原始上传文档；
- 文档解析产物；
- 对象存储元数据；
- 生产配置的安全副本；
- JWT 和 Checkpoint 加密密钥；
- Prometheus 和 Grafana 配置；
- 发布版本及镜像信息。

### 14.2 PostgreSQL

建议：

- 每日全量备份；
- 根据重要程度增加增量或 WAL 归档；
- 支持时间点恢复；
- 备份文件加密；
- 设置备份保留周期；
- 将备份复制到另一台服务器或另一存储区域。

LangGraph Checkpoint、会话、引用、用户、知识库元数据和个人财务数据都依赖 PostgreSQL，因此数据库恢复能力是核心要求。

### 14.3 对象存储

- 开启版本管理；
- 配置生命周期策略；
- 对删除操作进行审计；
- 定期校验数据库记录与对象是否一致；
- 重要文档跨存储复制；
- 避免只在生产服务器本地磁盘保存文件。

### 14.4 Redis

Redis 主要用于缓存和队列，不应成为唯一业务数据源。

P6.2 同时将 Redis 用作高成本入口的原子配额和短期并发租约。部署前应根据 API/Worker
副本数和模型容量审阅全部 `AURUM_QUOTA_*` 配置；租约 TTL 必须覆盖正常任务时长但不能
代替 Worker 终态释放。Redis 不可用时模型问答和文档上传会 fail-closed，已发布检索缓存
自动旁路 PostgreSQL 回源。`AURUM_RETRIEVAL_CACHE_*` 只控制短 TTL、抖动和单飞锁，不得
用于缓存最终回答或财务明细。

需要根据用途决定：

- 是否开启 AOF；
- 是否需要 RDB 快照；
- Broker 故障后任务如何恢复；
- 业务任务是否具备幂等性；
- 缓存丢失后是否能从数据库重建。

## 15. 恢复流程

恢复演练至少覆盖：

### 15.1 数据库恢复

1. 停止写入流量；
2. 确认恢复目标时间；
3. 创建新的恢复数据库；
4. 导入备份；
5. 校验迁移版本；
6. 校验用户、会话、文档、引用和财务数据；
7. 切换应用连接；
8. 运行冒烟测试；
9. 恢复流量；
10. 记录恢复过程。

不要直接覆盖唯一的生产数据库，应优先恢复到新实例并校验。

### 15.2 对象存储恢复

1. 恢复存储桶或对象版本；
2. 校验对象键；
3. 校验文件哈希；
4. 对比数据库文档记录；
5. 对缺失索引执行重新解析或重新索引；
6. 验证引用能够打开原文。

### 15.3 恢复指标

正式上线前需要明确：

- RPO：最多允许丢失多少时间的数据；
- RTO：故障后允许多长时间恢复；
- 备份保留周期；
- 恢复演练频率；
- 恢复负责人。

## 16. 回滚方案

### 16.1 应用回滚

保留上一个稳定镜像版本：

```text
CURRENT_VERSION=v0.2.0
PREVIOUS_VERSION=v0.1.9
```

如果新版本健康检查或冒烟测试失败：

1. 停止继续发布；
2. 保存错误日志和 Trace；
3. 将 API、Worker 和 Web 镜像切回旧版本；
4. 重新启动旧版本；
5. 执行健康检查；
6. 执行关键冒烟测试；
7. 记录故障和回滚原因。

### 16.2 数据库回滚

应用镜像可以回滚，但数据库不应默认自动执行破坏性降级。

推荐：

- 使用向前兼容迁移；
- 旧版本应用能够暂时兼容新 Schema；
- 数据问题优先使用修复迁移；
- 只有经过验证并且具备备份时才执行降级。

### 16.3 模型配置回滚

模型、提示词和检索参数也需要版本化：

- LLM 模型版本；
- Embedding 模型版本；
- Reranker 版本；
- Prompt 版本；
- Chunk 策略；
- Top-K；
- RAG 风险策略。

如果模型效果退化，应能够单独回滚配置，而不必回滚整个应用。

## 17. CI/CD

### 17.1 持续集成

每次提交或合并请求执行：

- Python 格式检查；
- Python 静态检查；
- Python 单元测试；
- 数据库迁移测试；
- API 集成测试；
- 前端格式和类型检查；
- 前端测试；
- Provider 合同测试；
- 权限隔离测试；
- RAG 基础回归测试；
- 依赖漏洞扫描；
- 镜像构建测试。

### 17.2 持续交付

通过测试后：

1. 构建版本化镜像；
2. 生成构建清单；
3. 推送到镜像仓库；
4. 自动部署测试环境；
5. 运行测试环境冒烟测试；
6. 生产部署需要人工批准；
7. 生产发布后执行健康检查；
8. 保存发布记录。

### 17.3 发布记录

当前开发里程碑记录如下；这些记录不等同于生产发布：

| 日期 | 里程碑 | Git 基线 | 验证摘要 |
| --- | --- | --- | --- |
| 2026-07-23 | 阶段一：架构和安全底座完成 | `933390a` | 后端测试、RLS、Docker 和真实认证流程通过 |
| 2026-07-24 | 阶段二及配套 Web 前端完成 | `3bfb9b0` | 财务功能、前端测试和生产构建通过 |
| 2026-07-24 | 阶段二安全审计整改完成 | 随整改分支交付 | 59 项后端测试、10 项前端测试及配置检查通过 |
| 2026-07-31 | 阶段四可信引用 RAG 完成 | `7b99307` | Hybrid Retrieval、Reranker、SSE、Checkpoint 和浏览器验收通过 |
| 2026-08-02 | 阶段五只读个人财务 Agent 完成 | `571192d` | 财务工具、Grounding、风险策略、评测和浏览器验收通过 |
| 2026-08-03 | 阶段六工程完成并合入 `master` | `e8aa6ea` | 企业级加固、供应链门禁、备份恢复、蓝绿发布与回滚演练通过 |

每次生产发布应记录：

- 发布时间；
- 发布负责人；
- Git Commit；
- 镜像版本；
- 数据库迁移版本；
- 模型和提示词版本；
- 配置变化；
- 备份位置；
- 冒烟测试结果；
- 是否发生回滚。

## 18. 监控、日志和告警

P6.1 已提供可执行的本地观测栈：

```powershell
docker compose -f compose.yaml -f compose.observability.yaml up -d --build
```

配置和运行说明位于 `deploy/observability/README.md`。Prometheus 和 Grafana 仅绑定
本机端口；生产 Gateway 必须继续屏蔽 `/metrics`。当前 Collector 使用 `debug`
exporter 验证链路，正式环境应替换为组织选定的 Trace 后端。

### 18.1 指标

至少采集：

- API 请求量；
- HTTP 错误率；
- P50、P95、P99 延迟；
- SSE 活跃连接；
- 首字延迟；
- LLM 总延迟；
- Token 使用量；
- 模型调用费用；
- RAG 检索延迟；
- Reranker 延迟；
- 引用覆盖率；
- Worker 队列长度；
- 任务失败率；
- PostgreSQL 连接池；
- 慢查询；
- Redis 内存；
- 磁盘容量；
- 对象存储容量。

### 18.2 日志

日志使用结构化 JSON，并包含：

- 时间；
- 日志级别；
- 服务名；
- `request_id`；
- `trace_id`；
- 用户 ID 的不可逆脱敏值；
- 路由；
- 状态码；
- 耗时；
- 错误码。

日志不得记录：

- 密码；
- Access Token；
- Refresh Token；
- API Key；
- JWT 私钥；
- 完整银行卡号；
- 完整个人财务明细；
- 未脱敏的文档敏感内容。

### 18.3 告警

建议告警条件：

- API 持续不可用；
- HTTP 5xx 明显增加；
- 数据库连接失败；
- Redis 不可用；
- Worker 全部离线；
- 队列持续积压；
- 文档解析失败率升高；
- LLM 调用失败率升高；
- 磁盘空间不足；
- 备份失败；
- 证书即将过期；
- 管理员连续登录失败；
- 出现跨用户权限异常。

## 19. 安全上线检查

上线前确认：

- [ ] HTTPS 已启用；
- [ ] HTTP 自动跳转 HTTPS；
- [ ] 数据库未暴露公网；
- [ ] Redis 未暴露公网；
- [ ] MinIO 管理端未暴露公网；
- [ ] FastAPI Debug 已关闭；
- [ ] 默认密钥已替换；
- [ ] JWT 私钥未进入 Git 和镜像；
- [ ] 管理员首次登录强制改密；
- [ ] 普通用户无法访问管理 API；
- [ ] PostgreSQL RLS 已验证；
- [ ] 上传文件类型和大小限制已启用；
- [ ] 日志脱敏已验证；
- [ ] API 限流已启用；
- [ ] CORS 只允许正式域名；
- [ ] 安全响应头已配置；
- [ ] 备份任务已启用；
- [ ] 恢复流程已演练；
- [ ] 镜像和依赖扫描通过。

## 20. 扩容路线

### 20.1 API 扩容

FastAPI 应保持无状态：

- 会话和消息写入 PostgreSQL；
- LangGraph 状态写入 Checkpointer；
- 缓存和限流写入 Redis；
- 文件写入对象存储。

这样可以增加多个 API 副本，由反向代理进行负载均衡。

### 20.2 Worker 扩容

将任务拆分为不同队列：

```text
ingestion
embedding
report
maintenance
default
```

根据队列积压分别增加 Worker，避免大文档解析阻塞普通任务。

### 20.3 数据层扩容

依次考虑：

1. 优化索引和慢查询；
2. 调整连接池；
3. 增加缓存；
4. PostgreSQL 升级配置；
5. 使用托管 PostgreSQL；
6. 配置只读副本；
7. 按数据量评估向量检索拆分。

### 20.4 模型服务扩容

- 简单问题使用小模型；
- 复杂问题使用强模型；
- Embedding 批处理；
- Reranker 批处理；
- GPU 服务独立部署；
- 设置并发和显存保护；
- 配置模型超时、熔断和降级。

## 21. 常见故障处理

### 21.1 API 无法启动

检查：

- 环境变量是否完整；
- 数据库是否可连接；
- Redis 是否可连接；
- 数据库迁移是否完成；
- JWT 密钥文件是否存在；
- 端口是否冲突；
- 容器日志是否有配置错误。

### 21.2 文档一直处于处理中

检查：

- Worker 是否在线；
- Celery 队列是否积压；
- Redis 是否可用；
- 文件是否能从对象存储读取；
- 解析器是否超时；
- Embedding 服务是否可用；
- 任务是否进入重试或死信队列。

### 21.3 问答没有引用

检查：

- 文档是否已发布；
- 分块是否生成；
- Embedding 是否写入；
- 项目是否绑定知识库；
- 权限过滤是否过严；
- Top-K 是否过低；
- Reranker 是否异常；
- 引用校验是否拒绝了无效引用。

### 21.4 SSE 中断

检查：

- Caddy 或 Nginx 是否缓冲响应；
- 代理超时是否过短；
- FastAPI Worker 是否被重启；
- LLM 是否超时；
- 浏览器是否主动取消；
- 多副本环境是否错误依赖本地内存状态。

### 21.5 数据库连接耗尽

检查：

- 连接池大小；
- API 副本数量；
- Worker 连接数；
- 是否存在未释放连接；
- 是否存在长事务；
- 是否存在慢查询；
- PostgreSQL 最大连接数。

## 22. 上线验收清单

只有以下条件满足后，版本才能视为成功上线：

### 22.1 基础设施

- [ ] 域名解析正确；
- [ ] HTTPS 正常；
- [ ] 所有必须容器健康；
- [ ] PostgreSQL 和 pgvector 正常；
- [ ] Redis 正常；
- [ ] 对象存储正常；
- [ ] Worker 正常；
- [ ] 监控能够采集数据。

### 22.2 数据

- [ ] 数据库迁移版本正确；
- [ ] 管理员初始化成功；
- [ ] 管理员没有被重复重置；
- [ ] 数据备份成功；
- [ ] 对象存储桶存在；
- [ ] 测试文档能够完成索引。

### 22.3 功能

- [ ] 注册和登录正常；
- [ ] 修改密码正常；
- [ ] 普通用户权限正确；
- [ ] 管理员知识库管理正常；
- [ ] 多会话正常；
- [ ] 历史消息正常；
- [ ] RAG 问答正常；
- [ ] 引用正常；
- [ ] 财务查询正常；
- [ ] SSE 流式输出正常。

### 22.4 安全

- [ ] 默认密钥已替换；
- [ ] 初始管理员已强制改密；
- [ ] 数据库和 Redis 未暴露公网；
- [ ] 跨用户隔离测试通过；
- [ ] 日志没有敏感信息；
- [ ] 上传安全限制生效；
- [ ] 限流生效。

### 22.5 运维

- [ ] 健康检查正常；
- [ ] 告警已配置；
- [ ] 发布版本有记录；
- [ ] 回滚镜像可用；
- [ ] 回滚流程已验证；
- [ ] 恢复流程已验证。

## 23. 快速命令参考

以下命令仅在对应部署文件实现后使用。

### 查看服务

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

### 查看日志

```bash
docker compose -f deploy/docker-compose.prod.yml logs --tail=200 api
docker compose -f deploy/docker-compose.prod.yml logs --tail=200 worker_ingestion
```

### 执行迁移

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm api alembic upgrade head
```

### 初始化管理员

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm api aurum-agent bootstrap-admin
```

### 启动生产服务

```bash
docker compose -f deploy/docker-compose.prod.yml up -d
```

### 停止生产服务

```bash
docker compose -f deploy/docker-compose.prod.yml down
```

执行 `down` 时不得附带删除数据卷的参数。

### 运行冒烟测试

```bash
deploy/scripts/smoke-test.sh
```

### 创建备份

```bash
deploy/scripts/backup.sh
```

### 执行回滚

```bash
deploy/scripts/rollback.sh <previous-version>
```

## 24. P6.3 候选发布质量门禁

候选实例切流前必须先执行统一评测和 `single-node-release` 负载档。Provider 证据只允许
记录环境、Chat/Embedding/Reranker Provider 与模型名和冒烟布尔结果，不得记录 API Key、
Token、Prompt 或响应正文。示例和完整夹具变量见 `evals/load/README.md`。

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_evaluation.py --mode candidate `
  --candidate-evidence .test-results\candidate-evidence.json `
  --output .test-results\phase6-candidate-gate.json

.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\single-node-release.json `
  --output .test-results\phase6-load-release.json
```

缺失夹具、任一必选场景跳过、非预期状态达到 1%、网络错误、跨用户/项目标记、P95 超过
锁定基线 20%，或 SSE/队列/数据库连接持续增长时均停止发布。首版单机基线标记为暂定，
只能用首次稳定候选运行经评审锁定；不得在同一发布中同时放宽阈值并声明回归通过。

## 25. P6.4 备份与隔离恢复

备份和恢复入口位于 `deploy/scripts/backup.ps1` 与 `restore.ps1`。正式运行前必须从外部
密钥系统注入专用 32 字节 base64 备份密钥，并把副本目录放到独立磁盘、主机或受控对象
存储。脚本只允许恢复到不存在的新数据库和新 bucket，不支持原地覆盖。

```powershell
.\deploy\scripts\backup.ps1 -OutputDirectory C:\AurumBackups\primary `
  -ReplicaDirectory D:\AurumBackups\replica

.\deploy\scripts\retention.ps1             # preview
.\deploy\scripts\retention.ps1 -Apply      # 审批后执行并记审计
```

完整的密钥、调度、保留和演练要求见 `deploy/backup-policy.md`。备份生成的
`aurum_backup.prom` 应挂载到 node-exporter textfile collector；缺失或 25 小时未更新会触发
Prometheus 告警。

## 26. 后续候选环境实施顺序

开发与本地演练项已经完成，后续正式上线按以下顺序执行：

1. 准备候选服务器、正式域名、DNS 和 TLS；
2. 将版本镜像推送到受控仓库并固定 digest；
3. 通过外部密钥系统注入运行密钥、备份密钥和最小权限账号；
4. 配置真正独立的异地备份介质并复跑隔离恢复演练；
5. 使用真实 Chat、Embedding 和 Reranker Provider 执行候选冒烟；
6. 使用完整隔离夹具运行 `single-node-release` 并锁定目标容量基线；
7. 审核发布 Manifest、备份、评测、负载、监控和回滚证据；
8. 由授权人员批准切流，发布后持续观察并保留旧槽；
9. 达到观察窗口后关闭旧槽并归档发布记录。

## 27. P6.5 可执行生产发布

P6.5 已实现 `deploy/compose.production.yaml`、Caddy Gateway、生产 Web 镜像、发布 Manifest、
`release.ps1`、`rollback.ps1` 和 GitHub Actions 发布门禁。生产切流需要显式人工批准，任何
切流后观测异常都会回滚到上一槽；自动回滚不执行数据库 `downgrade`。

完整参数、阈值、证据和演练命令见 `deploy/release-runbook.md`。开发机已完成成功切换与候选
故障回滚，本节所称“可执行”不表示已发布公网；真实 Provider、目标容量、正式 TLS/密钥与
异地备份仍须在候选服务器验收。

