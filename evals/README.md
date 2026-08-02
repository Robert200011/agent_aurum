# Evaluation assets

`phase5-finance-agent.json` 是阶段五的版本化确定性评测集，覆盖知识、财务、投资、混合、
高风险和澄清路由，以及月末、年末、闰年、相对时间与不可信工具请求拒绝。

本地执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py
```

评测必须达到数据集中的 `deterministic_pass_rate=1.0`。跨用户隔离、模型回答 Grounding、
真实 PostgreSQL、真实模型和浏览器冒烟属于有状态验收，分别由 Pytest 集成测试及
`web` 目录的 Playwright 测试执行，不能由该离线数据集替代。
