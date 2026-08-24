# Evaluation assets

`phase5-finance-agent.json` 是财务 Agent 的离线契约评测集，覆盖动态只读能力目录、长期记忆
能力、统一时间语义、投资风险护栏和不可信参数拒绝。自然语言到能力的选择由模型完成，因此还需
执行 Fake Provider、真实 Provider 和浏览器验收。

## 财务能力门禁

```powershell
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py
```

评测必须达到 `deterministic_pass_rate=1.0`。跨用户隔离、模型回答 Grounding、真实 PostgreSQL、
真实模型和浏览器冒烟由 Pytest 集成测试及 `web` 目录的 Playwright 测试覆盖。

## 长期记忆门禁

```powershell
.\.venv\Scripts\python.exe scripts\run_memory_evaluation.py `
  --output .test-results\memory-gate.json
```

该门禁检查提案证据、敏感内容拒绝、模型输出契约、受控上下文、稳定灰度分桶和装配性能。跨用户
RLS 隔离和完整保存/召回链路仍需 PostgreSQL 集成验收；真实 Provider 的判断质量需在候选环境
冒烟确认。

## HTTP/SSE 负载验证

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\local-smoke.json `
  --output .test-results\load-local.json

.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\single-node-release.json `
  --output .test-results\load-release.json
```

两档负载配置验证健康接口、错误率、延迟、会话/SSE 和数据库连接池增长。报告只记录统计值、
版本和测试标识，不记录 Token、问题正文、个人财务数据或响应全文。
