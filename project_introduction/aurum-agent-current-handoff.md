# Aurum Agent 当前开发进度交接说明

> 交接日期：2026-07-24
> 项目路径：`E:\agent_aurum`
> 当前主分支：`master`
> 当前基线：`ad3a1eb`

## 1. 当前结论

Aurum Agent 已完成阶段一“架构和安全底座”、阶段二“个人财务数据基础”及覆盖前两个
阶段的 Vue 3 Web 前端。四项高优先级安全审计遗留问题也已完成整改。下一步应进入
阶段三“知识库管理”，LangGraph、RAG 问答和完整财务 Agent 尚未开始实现。

## 2. 已完成的主要能力

- FastAPI 分层后端、PostgreSQL、pgvector、Redis、Alembic 和 Docker Compose；
- 用户注册、登录、改密、RBAC、JWT Access Token 和 HttpOnly Refresh Token Cookie；
- Redis 登录失败锁定、单 IP 限流、全局限流和令牌撤销；
- 账户、流水、预算、持仓、投资交易、行情快照和确定性财务报表；
- CSV/XLSX 流水导入、幂等提交、逐行错误报告、行数限制和压缩炸弹防护；
- 应用层 `user_id` 过滤与 PostgreSQL RLS 双重用户隔离；
- 登录注册、响应式应用框架、财务总览、账户、流水、预算和投资管理前端；
- JWT、初始管理员和数据库密码无可用代码默认值，并提供本地安全配置生成脚本。

## 3. 当前尚未实现

- 项目、知识库和文档管理；
- 对象存储、文档解析、分块、Embedding 和 pgvector 检索；
- LangGraph 工作流、RAG 回答、结构化引用和 SSE；
- 会话历史、Checkpoint 和 Agent 工具编排；
- 完整的生产部署资产、集中监控、自动备份与 CI/CD。

## 4. 本地启动

首次建立本地配置：

```powershell
.\scripts\generate-dev-env.ps1
docker compose up --build -d
docker compose ps
```

后端 OpenAPI 位于 `http://127.0.0.1:8010/docs`。前端启动：

```powershell
Set-Location web
npm install
npm run dev
```

已有旧版 `.env` 时，不要直接覆盖数据库密码。只需轮换认证密钥可执行：

```powershell
.\scripts\generate-dev-env.ps1 -RotateAuthSecrets
```

## 5. 验证基线

当前交接使用以下命令验证：

```powershell
python -m ruff check app migrations tests
python -m pytest
python -m mypy app
alembic check
docker compose config --quiet

Set-Location web
npm run check
npm run build
```

2026-07-24 验证结果：

| 检查 | 结果 |
| --- | --- |
| Ruff | 通过 |
| Pytest | 59 项通过 |
| Mypy | 74 个源文件通过 |
| 前端类型、Lint 和测试 | 通过，10 项测试 |
| 前端生产构建 | 通过 |
| Alembic | 无待生成迁移 |
| Docker Compose 配置 | 通过 |
| API Docker 镜像构建 | 通过 |

数据库迁移头为 `20260724_0003`。执行测试或启动服务前应确认 Docker Desktop 已启动，
且本地 `.env` 已提供全部必填敏感配置。

## 6. 下一阶段建议

阶段三开始前先确认以下四项：

1. 模型与 Embedding 供应商；
2. 对象存储方案；
3. 异步任务队列；
4. 知识库可见范围。

确认后按“知识库 CRUD → 文档上传与任务状态 → 解析与分块 → Embedding 与检索”的顺序
形成纵向闭环，继续沿用现有权限、审计、租户隔离、测试和配置安全约束。

## 7. 文档索引

- [项目运行说明](./README.md)
- [总体技术方案与实施路线](./aurum-agent-initial-design.md)
- [总体架构设计](./aurum-agent-architecture.md)
- [部署上线与运维方案](./aurum-agent-deployment-guide.md)
- [阶段一交接与后续里程碑](./aurum-agent-phase-1-handoff.md)
