# Aurum Agent 当前开发进度交接说明

> 交接日期：2026-08-03
> 项目路径：`E:\agent_aurum`
> 当前阶段：阶段六 P6.1～P6.5 工程完成并已合入 `master`，待候选环境上线验收或进入阶段七规划

## 1. 当前结论

Aurum Agent 已完成阶段一至阶段六的工程开发。当前系统包含安全鉴权与租户隔离、个人财务账本、
知识库入库与 Hybrid Retrieval、可信引用 RAG、SSE/Checkpoint 会话，以及受控编排的
只读个人财务 Agent。阶段五最终图版本为 `finance-agent-p5.6-v1`，当前加固图版本为
`finance-agent-p6.3-v1`，迁移头为
`20260802_0012`。阶段六通过 GitHub PR #11 squash 合并，当前功能基线为 `e8aa6ea`；
本地 `master` 与 `origin/master` 已对齐，阶段六旧本地分支和 stash 已完成清理。

P5.6 已补齐版本化评测、数值 Grounding、跨用户恢复接口边界、真实浏览器自动化和交付
文档。模型无法指定用户、执行写工具或把受控证据之外的数字、行情、工具名和引用保存为
最终答案。

阶段六 P6.1 已完成字段白名单 JSON 日志、统一脱敏、`contextvars` 关联上下文、
OpenTelemetry OTLP Trace、Prometheus 指标、3 个 Grafana 面板和 6 条告警规则。完整
观测栈已在本地 Compose 中启动并通过抓取、面板加载和告警触发/恢复测试。

阶段六 P6.2 已完成 Redis Lua 原子配额、Token 预留/实际结算、Agent 与上传处理租约、
稳定 429/`Retry-After` 语义，以及仅保存已发布 Chunk 标识和分数的检索缓存。聊天和上传在
高成本操作前 fail-closed；缓存故障旁路，缓存命中仍以 PostgreSQL 当前项目权限和发布版本
重建引用。缓存 Key 仅含不可逆哈希、资源版本和算法参数，不含问题、文档正文或最终回答。

阶段六 P6.3 已完成版本化 RAG 黄金结果和 Prompt Injection 攻击集、最终模型输出安全
兜底、阶段五/六统一机器门禁、五类故障场景自动化，以及 `local-smoke` 和
`single-node-release` 两档负载配置。PR 门禁已通过；本机 60 次必选负载请求无错误、无
资源持续增长。真实 Provider 与完整发布负载由候选环境强制提供版本元数据和夹具，不能
用本地跳过结果替代。

阶段六 P6.4 已完成 PostgreSQL/MinIO 全版本 AES-256-GCM 加密备份、独立副本接口、
恢复目标防覆盖、恢复后 Alembic/RLS/业务计数/引用/checkpoint/对象哈希校验，以及默认
preview、apply 后留审计记录的数据保留执行器。本地已恢复到隔离数据库和 bucket，最终
演练 RPO 0.96 秒、RTO 12.21 秒，详见 P6.4 验收报告。

阶段六 P6.5 已完成单机生产 Compose、API/Web 生产镜像、Caddy Gateway、供应链 CI、发布
Manifest、发布前备份、一次性迁移、蓝绿切流、指标决策和一键回滚。独立生产栈演练中绿槽
20/20 请求成功、P95 43.56ms，故障注入后蓝槽回滚 10/10 成功；内部 MinIO TLS 与独立对象
域名的预签名下载也已通过，详见 P6.5 验收报告。

## 2. 阶段五交付

- 10 个只读财务工具：摘要、账户、流水、收支、预算、组合、持仓、行情、异常和预算建议；
- 服务端时间范围、比较窗口、时区、分币种与可审计汇率换算；
- Decimal 预算执行、持仓盈亏、稳健异常分析和预算预测；
- 知识、财务、投资、混合与高风险路由；
- 财务工具审计、消息证据、数据时间、知识引用和风险提示持久化；
- SSE 阶段、停止、恢复、重试、重新生成和历史展示；
- 回答数字与工具名 Grounding、引用白名单和一次受控重答；
- Edge + Vue + FastAPI + PostgreSQL + DashScope 的财务/混合场景验收。

详细契约与结果：

- [阶段五 API 与工具契约](./aurum-agent-phase-5-api-contract.md)
- [阶段五 P5.6 验收报告](./aurum-agent-phase-5-acceptance.md)
- [总体技术方案](./aurum-agent-initial-design.md)

## 3. 本地启动

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8010/api/v1/health/ready

Set-Location web
npm install
npm run dev
```

服务地址：OpenAPI `http://127.0.0.1:8010/docs`，前端开发服务器
`http://127.0.0.1:4173`。`.env` 包含本机敏感配置，不得提交。

Docker Desktop 中的 `aurum-agent` 是日常开发 Compose；`aurum-agent-production` 是 P6.5
蓝绿发布和回滚演练创建的独立生产 Compose 项目，不表示系统已部署到公网服务器。日常开发
只需启动 `aurum-agent`，生产演练栈应按发布手册注入完整密钥和发布参数后再启动。

## 4. 验收基线

```powershell
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py
.\.venv\Scripts\python.exe scripts\run_phase6_evaluation.py
.\.venv\Scripts\python.exe scripts\run_phase6_load.py --profile evals/load/local-smoke.json
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app migrations tests scripts
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m alembic check

Set-Location web
npm run check
npm run build
npm run test:e2e
npm audit
```

确定性评测为 16/16；真实 Edge 浏览器财务与混合回答通过；生产依赖和全部 npm 依赖审计
均为 0 个已知漏洞。本地后端测试和前端 18 项测试通过。真实 PostgreSQL 集成测试需
通过环境变量提供迁移/测试所有者连接，不要把连接字符串写入仓库。

`tests/` 按项目当前约定仅保留在本地并由 Git 忽略，因此 GitHub 后端检查不会执行完整
Pytest，阶段结束时仍须在受控本地环境运行上述完整测试并记录验收结果。

## 5. 下一步

阶段六功能代码已经合入 `master`，文档状态已按最终进度收口。若准备正式上线，下一步进入
候选环境验收：配置正式域名/TLS、镜像 digest、外部密钥和异地备份，复跑真实 Provider
冒烟与目标容量负载，再由授权人员批准切流；若继续产品开发，则先编写阶段七分批方案，
优先选择保持只读边界的财务报告或投资组合风险报告。自然语言记账和任何财务写操作必须
等 Human-in-the-loop、幂等、审计和撤销方案明确后再实施。阶段六整体顺序、范围和验收
标准见[阶段六企业级加固开发方案](./aurum-agent-phase-6-plan.md)，P6.1 结果见
[P6.1 验收报告](./aurum-agent-phase-6-p6.1-acceptance.md)，P6.2 结果见
[P6.2 验收报告](./aurum-agent-phase-6-p6.2-acceptance.md)。
[P6.3 验收报告](./aurum-agent-phase-6-p6.3-acceptance.md)记录了本地门禁结果，以及仍需在
候选环境执行的真实 Provider/单机负载证据；
[P6.4 验收报告](./aurum-agent-phase-6-p6.4-acceptance.md)记录了隔离恢复演练。
[P6.5 验收报告](./aurum-agent-phase-6-p6.5-acceptance.md)记录蓝绿发布和故障回滚演练，
[阶段六验收汇总](./aurum-agent-phase-6-acceptance.md)记录整体状态和上线前剩余门禁。
