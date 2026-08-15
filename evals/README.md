# Evaluation assets

`phase5-finance-agent.json` 已升级为 Agent V2 的离线契约评测集，覆盖动态只读能力目录、
统一时间语义、投资风险护栏和不可信能力参数拒绝。自然语言到能力的选择由外接模型完成，
不再使用确定性关键词路由，因此必须另行执行 Fake Provider、真实 Provider 和浏览器验收。

本地执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py
```

评测必须达到数据集中的 `deterministic_pass_rate=1.0`。跨用户隔离、模型回答 Grounding、
真实 PostgreSQL、真实模型和浏览器冒烟属于有状态验收，分别由 Pytest 集成测试及
`web` 目录的 Playwright 测试执行，不能由该离线数据集替代。

## P6.3 统一回归门禁

P6.3 新增 RAG 黄金结果、Prompt Injection 攻击集和故障场景清单。PR 档使用冻结结果、
真实 Prompt/引用/工具/输出策略及 Fake Provider 测试，统一执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_evaluation.py `
  --output .test-results\phase6-gate.json
```

命令会连续验证阶段五财务 Agent、P6.3 RAG、安全攻击和五类故障场景，并输出包含 Git、
Graph、Prompt 哈希、数据集版本与哈希的机器可读报告。候选发布还必须提供不含密钥的
Provider 证据文件：

```powershell
Copy-Item evals\load\candidate-evidence.example.json .test-results\candidate-evidence.json
# 用测试环境的真实模型元数据更新；仅在对应冒烟通过后设置 provider_smoke_passed=true，
# 完成长期记忆保存—新会话召回—删除—不再召回后设置 memory_smoke_passed=true：
.\.venv\Scripts\python.exe scripts\run_phase6_evaluation.py --mode candidate `
  --candidate-evidence .test-results\candidate-evidence.json `
  --output .test-results\phase6-candidate-gate.json
```

负载测试使用 `evals/load/` 中的两档配置。`local-smoke` 默认验证健康接口、错误率、延迟、
连接池和队列增长；提供隔离测试账号环境变量后还会执行 Fake SSE。`single-node-release`
中的普通 API、RAG、真实模型、SSE、文档入库和积压恢复均为必选，缺少夹具时命令会失败：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\local-smoke.json `
  --output .test-results\phase6-load-local.json

.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\single-node-release.json `
  --output .test-results\phase6-load-release.json
```

所有报告只记录统计值、版本和测试标识，不记录 Token、问题正文、文档正文或响应全文。

## M5 长期记忆发布门禁

长期记忆门禁只做确定性高价值检查：提案证据与敏感内容拒绝、模型输出契约、受控上下文、
稳定灰度分桶和上下文装配性能，不枚举自然语言句式：

```powershell
.\.venv\Scripts\python.exe scripts\run_memory_evaluation.py `
  --output .test-results\memory-gate.json
```

跨用户 RLS 隔离和完整保存/召回链路仍由 PostgreSQL 集成验收覆盖；真实 Provider 的判断质量
必须在候选环境冒烟确认，离线门禁不伪装成模型效果评测。
