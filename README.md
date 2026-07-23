# Aurum Agent

Aurum Agent 是面向个人财务、存款收支和投资知识问答的 Python 服务。本仓库目前完成
“阶段一：架构和安全底座”，前端、财务业务接口、知识库管理和 LangGraph RAG 将在后续
阶段实现。

后端采用根目录 `app/` 包布局，不再使用 `src/aurum_agent/`。现有代码按 API、Agent、
RAG、Finance、Provider、Database、Service、Worker、Observability 和 Security
边界组织，后续阶段可直接在对应领域目录内扩展。

## 阶段一已包含

- FastAPI 分层应用骨架：API、Service、Repository、Provider；
- PostgreSQL 16、pgvector 和 Redis 开发环境；
- `identity`、`finance`、`rag`、`chat`、`audit`、`agent` 数据库 schema；
- 用户注册、用户名或邮箱登录、个人资料查询和修改密码；
- Argon2id 密码哈希；
- 短期 JWT Access Token；
- 只保存 SHA-256 摘要的 Refresh Token、轮换和重用检测；
- Redis 登录失败限流和 Access Token 即时撤销；
- `admin / 123456` 幂等初始化，管理员首次登录必须修改密码；
- 个人财务、检索日志和会话表的 PostgreSQL Row Level Security；
- 迁移所有者与最小权限 API 数据库角色分离；
- 请求 ID、安全响应头、CORS 白名单、统一错误格式和审计日志。

## 使用 Docker 启动完整后端

要求 Docker Desktop 已启动。

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

服务地址：

- OpenAPI：`http://127.0.0.1:8010/docs`
- 存活检查：`http://127.0.0.1:8010/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8010/api/v1/health/ready`

首次登录：

```json
{
  "identifier": "admin",
  "password": "123456"
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
Copy-Item .env.example .env
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
├── web/                     # Vue 3 前端预留目录
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

配置统一使用 `AURUM_` 前缀的环境变量。`.env` 只用于本地开发，已被 Git 忽略。
生产容器应将 Docker/Kubernetes Secret 映射为同名环境变量。当
`AURUM_ENVIRONMENT=production` 时，如果仍使用示例 JWT 密钥、管理员密码 `123456`
或开启 Debug，应用会拒绝启动。

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
