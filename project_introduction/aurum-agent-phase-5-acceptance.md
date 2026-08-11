# 阶段五 P5.6 测试、评测与交付验收

> 验收日期：2026-08-02
> 图版本：`finance-agent-p5.6-v1`
> 数据库迁移头：`20260802_0012`

> 2026-08-11 更新：本文件保留阶段五历史验收证据；当前运行时已升级为
> `finance-capability-agent-v2`。下述确定性路由器及关键词日期解析测试已由 V2 能力目录、
> 服务端语义时间、Fake Provider、真实 Provider 和浏览器验收取代。

## 1. 自动化验收矩阵

| 验收域 | 主要证据 |
| --- | --- |
| 月末、年末、闰年、时区和相对时间 | `tests/unit/test_finance_time_ranges.py` |
| 工具 Schema、参数上限、空结果和异常结果 | `tests/unit/test_finance_agent_tools.py` |
| Decimal、预算、持仓盈亏和汇率 | `tests/unit/test_finance_analytics.py`、工具单元/集成测试 |
| 知识、财务、投资、混合和高风险路由 | `tests/unit/test_finance_agent_planner.py`、版本化评测集 |
| 异常分析与预算建议边界 | `tests/unit/test_finance_analytics.py` |
| 问题、工具、Checkpoint、恢复和重试的跨用户隔离 | Chat Service、真实 PostgreSQL 集成测试 |
| 伪造身份、写工具、金额、行情、工具名和引用拒绝 | 工具适配器、回答图 Grounding 和引用测试 |
| SSE、停止、恢复、失败重试、重新生成和历史消息 | Chat Service 与前端组件测试 |
| 工具审计、财务证据、引用、风险和数据时间持久化 | `tests/integration/test_chat_persistence.py` |
| 真实浏览器财务与混合回答 | `web/e2e/phase5-finance-agent.e2e.ts` |

根目录 `/tests/` 已解除错误的 Git 忽略规则，全部后端回归测试现在属于正式交付资产。

## 2. 版本化评测集

数据集：`evals/phase5-finance-agent.json`。当前含 16 个确定性用例：9 个路由、4 个时间
边界和 3 个不可信请求拒绝用例，阈值为 100%。

```powershell
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py
```

验收结果：`16/16`，通过率 `1.0`，无失败用例。

全量质量门禁结果：

| 检查 | 结果 |
| --- | --- |
| Pytest（含真实 PostgreSQL） | 168 项通过 |
| Ruff | 通过 |
| Mypy | 119 个源文件通过 |
| Alembic | 无新迁移，`20260802_0012 (head)` |
| 前端类型、Lint、Vitest | 通过，18 项组件/工具测试 |
| 前端生产构建 | 通过 |
| Playwright Edge | 1 项真实浏览器场景通过 |
| npm audit | 0 个已知漏洞 |

## 3. 真实环境验收

浏览器使用本机 Microsoft Edge，由 Playwright 启动真实 Vue 页面，并连接 Docker 中的
FastAPI、PostgreSQL、Redis、MinIO、Worker 以及真实 DashScope `qwen-plus`。

通过的两个核心场景：

1. “我这个月收入、支出和净现金流是多少？”：执行 `get_finance_summary`，浏览器展示
   统计期间、CNY 数值、数据时间、计算口径和分析建议；
2. 财务/知识混合问题：执行 1 次财务工具及 Hybrid Retrieval，最终持久化 1 条财务证据、
   3 条可信引用，运行记录为 completed。

真实数据库抽查结果：两轮均使用 `finance-agent-p5.6-v1`；纯财务轮为 1 个工具、1 条证据、
0 条知识引用；混合轮为 1 个工具、1 条证据、3 条知识引用。API 就绪检查的 database、
Redis、object storage 和 ingestion worker 均为 true。

验收同时观察到模型尝试伪造空知识上下文的 `[S1]`，以及自行计算工具未返回的比例；两者
均被服务端拒绝。这验证了伪造防线不是仅依赖 Prompt。系统最多用同一证据受控重答一次，
第二次仍不合格时运行失败，不保存无效答案。

## 4. 执行命令

```powershell
# 后端及真实 PostgreSQL（集成测试夹具使用迁移/测试所有者连接）
$env:AURUM_RAG_INTEGRATION_DATABASE_URL = '<test-owner-url>'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app migrations tests scripts
.\.venv\Scripts\python.exe -m mypy app scripts
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m alembic current

# 前端
Set-Location web
npm run check
npm run build
npm run test:e2e
npm audit
```

本地 `.env` 中的迁移连接可用于一次性开发验收，但不得写入测试代码、文档或 Git。

## 5. 交付结论

- 10 个 Agent 工具全部只读，写工具数为 0；
- 自动化与真实场景未发现跨用户数据泄漏；
- 数值、行情、汇率、引用和工具名均有服务器端可执行校验；
- 无有效汇率时不会合并币种；缺数据时澄清或降级；
- 真实模型、真实数据库和真实浏览器核心场景已通过；
- 阶段五原始 11 项能力及财务/知识混合回答已完成，阶段五可交付。
