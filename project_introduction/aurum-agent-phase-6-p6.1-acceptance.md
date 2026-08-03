# Aurum Agent P6.1 日志脱敏与可观测性验收报告

> 验收日期：2026-08-02  
> 范围：阶段六 P6.1，不包含 P6.2 配额和业务缓存

## 1. 交付结论

P6.1 基础范围已完成，可以进入 P6.2。应用在 Trace 导出关闭时不依赖任何观测后端；
启用观测 Compose 后，API、Worker、Collector、Prometheus 和 Grafana 均能正常启动。

## 2. 已实现能力

- `contextvars` 自动传播 `request_id`、`trace_id`、`conversation_id`、`agent_run_id` 和
  用户不可逆 HMAC 哈希；请求结束恢复上下文，拒绝不安全的外部 Request ID；
- JSON 日志字段白名单和统一过滤器，覆盖凭据、JWT、数据库 URL、银行卡号及正文类字段；
- 异常仅记录异常类型和脱敏摘要，不输出请求体、Prompt、Provider 响应或原始 traceback；
- FastAPI、SQLAlchemy、Redis、Celery 自动 Trace，以及模型、Embedding、Reranker、
  Retrieval 和财务工具的受控业务 Span；
- `/metrics` 覆盖 API、SSE、模型 Token、检索、工具、Worker、队列、数据库池，并为
  P6.2 预留缓存指标；所有标签均为有限枚举或路由模板；
- Collector 成功 Trace 5% 尾部采样、错误 Trace 全保留；默认开发环境关闭 Trace 导出；
- 3 个 Grafana 面板和 6 条 Prometheus 告警规则；备份超时规则将在 P6.4 指标发布后生效。

## 3. 自动化验收

执行结果：

| 检查 | 结果 |
| --- | --- |
| `pytest` | 167 passed，7 skipped（外部集成条件未提供） |
| `ruff check .` | 通过 |
| `mypy app` | 121 个源文件通过 |
| `git diff --check` | 通过 |
| Compose 合并配置 | 通过 |
| Prometheus `promtool check config` | 配置通过，加载 6 条规则 |
| Prometheus `promtool test rules` | Worker 离线告警触发和恢复测试通过 |
| Collector `validate` | 通过 |
| Grafana dashboard JSON/YAML | 通过 |

新增单元测试覆盖敏感日志、异常摘要、异步上下文传播、用户哈希、指标低基数路由和跨异步
任务同 Trace。日志测试输入包含 Token、Provider Key、数据库密码、银行卡号、Prompt 和
流水描述，输出中均未出现原文。

## 4. 本地容器冒烟

使用 `compose.yaml + compose.observability.yaml` 完成真实启动：

- API 健康检查为 `ok`，`/metrics` 可读取 P6.1 指标族；
- Prometheus target 为 `up`，6 条告警规则已加载；
- Grafana 数据库为 `ok`，3 个 P6.1 面板均已自动 provision；
- Collector 已接收并经尾部采样导出 Trace；应用 JSON 日志包含对应 `trace_id`；
- Worker、Beat、Prometheus、Grafana 和 Collector 在验收期间均保持运行；验收结束后已停止
  使用临时密码的观测附加容器，并恢复原基础开发 Compose。

本次验收使用临时本地 Grafana 密码，仅注入当前进程，未写入仓库或 `.env.example`。

## 5. 已知边界

- Collector 当前使用 `debug` exporter，不保存可检索的长期 Trace；正式后端在生产环境
  确定后通过 Collector 配置接入；
- Worker 任务计数在 Worker 进程内产生，当前 API `/metrics` 以心跳与队列深度作为
  Worker 主监控；跨进程聚合留到生产监控拓扑确定后处理；
- 备份成功时间指标属于 P6.4，当前只预置对应告警规则；
- 未调用真实付费模型做聊天冒烟；同 Trace 串联由自动化 Span 测试和真实 API/数据库
  Trace 冒烟验证，后续真实 Provider 发布门禁继续覆盖完整 Agent 链路。
