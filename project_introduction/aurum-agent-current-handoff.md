# Aurum Agent 当前开发进度交接说明

> 交接日期：2026-08-02
> 项目路径：`E:\agent_aurum`
> 当前阶段：阶段五已完成，下一步进入阶段六企业级加固

## 1. 当前结论

Aurum Agent 已完成阶段一至阶段五。当前系统包含安全鉴权与租户隔离、个人财务账本、
知识库入库与 Hybrid Retrieval、可信引用 RAG、SSE/Checkpoint 会话，以及受控编排的
只读个人财务 Agent。阶段五最终图版本为 `finance-agent-p5.6-v1`，迁移头为
`20260802_0012`。

P5.6 已补齐版本化评测、数值 Grounding、跨用户恢复接口边界、真实浏览器自动化和交付
文档。模型无法指定用户、执行写工具或把受控证据之外的数字、行情、工具名和引用保存为
最终答案。

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

## 4. 验收基线

```powershell
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py
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
均为 0 个已知漏洞。后端 168 项测试和前端 18 项测试通过。真实 PostgreSQL 集成测试需
通过环境变量提供迁移/测试所有者连接，不要把连接字符串写入仓库。

## 5. 下一步

阶段六优先处理：用户/模型配额、日志脱敏、缓存与可观测性、RAG 回归、Prompt Injection、
压力测试、备份恢复、灰度发布与回滚。阶段五仍保持只读边界；自然语言记账和任何财务写
操作继续留在后续 Human-in-the-loop 方案中。
