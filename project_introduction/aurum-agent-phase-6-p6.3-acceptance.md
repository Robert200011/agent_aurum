# Aurum Agent P6.3 验收报告

> 验收日期：2026-08-02  
> Git 基线：`571192d010767c4febcfa8b1408b8974c67f1cec`  
> 当前回答图：`finance-agent-p6.3-v1`  
> 结论：基础开发和本地确定性验收通过；真实 Provider 与完整单机发布负载留给候选环境执行

## 1. 已完成能力

- 新增 7 类 RAG 冻结用例，覆盖可回答、拒答、冲突、多版本、跨知识库、混合财务和引用定位；
- 新增 9 类 Prompt Injection 用例，覆盖直接/间接注入、Prompt/密钥索取、伪造引用、
  伪造工具/身份、写操作和跨项目检索；
- 最终模型输出增加敏感凭据、内部 UUID、系统提示回显和财务写操作声明的确定性兜底；
- SSE 改为完整缓冲，通过引用、财务 Grounding、风险和安全校验后才发送净化文本，避免
  “最终拒绝但原始增量已泄露”；当前版本保持 SSE 协议，但不承诺逐 Token 输出；
- `run_phase6_evaluation.py` 统一执行阶段五、RAG、安全和故障场景，报告固定数据集/Prompt/
  Graph/Git 版本；候选档强制保存 Chat、Embedding、Reranker 型号和 Provider 冒烟结论；
- 五类故障场景均绑定实际 Pytest：配额拒绝、Provider 超时、SSE 取消、缓存失效和
  Reranker 降级；
- `local-smoke` 与 `single-node-release` 负载配置、基线和阈值已版本化，报告吞吐、
  P50/P95/P99、首字节、错误率、状态码、隔离标记及 Prometheus 资源前后快照。

## 2. 本地验收结果

统一 PR 门禁全部通过：阶段五 16/16；RAG 7/7，Recall@K、引用有效率/覆盖率、
Groundedness、拒答和财务数值准确率均为 100%，跨用户泄漏为 0；安全攻击 9/9，攻击阻断
和 Prompt 边界均为 100%，写工具、身份及跨项目泄漏为 0；5/5 故障检查通过。

本机 Docker `local-smoke` 执行 40 次存活和 20 次就绪请求：错误率、网络错误和隔离泄漏
均为 0；存活 P95 约 6.7ms，就绪 P95 约 36.5ms；SSE 连接、队列和已借出数据库连接无
持续增长。由于本次没有向进程注入隔离测试账号夹具，Fake SSE 被配置按预期标记为
`required=false` 的跳过项，不能作为候选发布 SSE 证据。

执行命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_evaluation.py
.\.venv\Scripts\python.exe scripts\run_phase6_load.py --profile evals\load\local-smoke.json
.\.venv\Scripts\ruff.exe check app migrations tests scripts
.\.venv\Scripts\mypy.exe app
.\.venv\Scripts\python.exe -m pytest
```

## 3. 候选发布强制项

本地结果不能替代真实环境。进入发布前必须完成：

1. 使用真实 PostgreSQL、Redis、MinIO、Chat、Embedding 和 Reranker 执行候选门禁；
2. 从示例创建无密钥的 candidate evidence，记录环境和真实模型版本；
3. 为 `single-node-release` 提供隔离账号、知识库、会话、文档和恢复任务夹具，所有场景
   必须运行，不能跳过；
4. 首次稳定运行后评审并锁定暂定单机 P95 基线，确认 5xx 低于 1%、P95 回退不超过 20%、
   隔离泄漏为 0，连接池、SSE 和队列无持续增长；
5. 归档机器报告；报告和环境文件不得包含 Token、Prompt、文档或响应正文。

## 4. 交付资产

- `app/evaluation/phase6.py`、`app/agents/policies/output_security.py`
- `evals/phase6-*.json`、`evals/load/`
- `scripts/run_phase6_evaluation.py`、`scripts/run_phase6_load.py`
- `tests/evaluation/test_phase6_gate.py`、`tests/unit/test_output_security.py`
- 五类已有故障路径测试及安全 SSE 图测试

P6.3 不新增业务写能力，也不修改财务 Agent 的只读边界。下一步进入 P6.4：备份、恢复与
数据保留。
