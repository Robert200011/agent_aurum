# 阶段五个人财务 Agent API 与工具契约

> 契约版本：P5.6 / `finance-agent-p5.6-v1`
> 更新日期：2026-08-02

## 1. 安全边界

- 所有 Agent 财务工具均为只读白名单，当前共 10 个；
- 工具输入不存在 `user_id`，用户身份只从已验证 Access Token 和服务端运行上下文注入；
- 会话、消息、运行、工具审计和财务证据均按当前用户查询，并由 PostgreSQL RLS 加固；
- 模型不能直接访问数据库，也不能注册、选择或执行财务写工具；
- 模型回答中的数字、日期、行情和工具名必须存在于本轮受控财务结果或可信知识片段；
- 首次回答校验失败时最多执行一次同证据受控重答，第二次失败则返回安全错误。

## 2. 只读工具白名单

| 工具 | 主要输入 | 主要输出 |
| --- | --- | --- |
| `get_finance_summary` | 含首尾日期、可选目标币种 | 分币种收入、支出、净现金流、余额和预算摘要 |
| `get_account_balances` | 可选目标币种 | 有效账户和分币种余额 |
| `search_transactions` | 日期、类型、分类、账户、币种、关键词、`limit<=50` | 有界流水明细和截断标志 |
| `get_income_expense_report` | 主区间、可选对比区间和目标币种 | 收支合计及分类明细 |
| `get_budget_status` | 日期、分类和目标币种 | 预算额度、已用、剩余和执行率 |
| `get_portfolio_summary` | 目标币种、`holding_limit<=100` | 成本、市值、未实现盈亏和价格完整性 |
| `get_holding_performance` | 唯一的持仓 ID 或证券代码、`limit<=100` | 单持仓成本、行情和收益表现 |
| `get_market_snapshot` | 证券代码和可选币种 | 价格、来源、观测时间或明确缺失状态 |
| `analyze_expense_anomalies` | 日期、目标币种、`history_window_count<=24` | 区间变化、分类贡献和稳健异常结论 |
| `get_budget_advice` | 预算区间、截至日期、分类、历史期数和 `limit<=25` | 期末预测、超支额、日均额度和调整代码 |

统一结果包含 `call_id`、工具名、规范化参数、状态、`data_as_of`、耗时、结构化数据、
警告和错误。金额、数量、比例及汇率使用 `Decimal`/数据库定点数；缺失、过期、超时和
空结果使用结构化警告或错误表达，不使用模型补值。

## 3. Chat HTTP 契约

所有路径以 `/api/v1` 为前缀并要求 Bearer Access Token。

| 方法与路径 | 用途 |
| --- | --- |
| `GET /chat/projects` | 返回至少含一个已发布、启用且具备 Embedding Chunk 的可问答项目 |
| `POST /conversations` | 创建固定绑定项目的会话 |
| `GET /conversations` | 分页查询当前用户会话 |
| `GET /conversations/{conversation_id}` | 返回历史消息、可信引用、财务证据和风险提示 |
| `POST /conversations/{conversation_id}/messages` | 非流式问答 |
| `POST /conversations/{conversation_id}/messages/stream` | 启动 SSE 问答 |
| `GET /conversations/{conversation_id}/runs/latest` | 查询最近一次运行 |
| `GET /conversations/{conversation_id}/runs/{run_id}/stream?after=N` | 断线后按序号恢复 SSE |
| `POST /conversations/{conversation_id}/runs/{run_id}/cancel` | 显式停止运行 |
| `POST /conversations/{conversation_id}/messages/{message_id}/regenerate/stream` | 重新生成或失败重试 |

跨用户的 `conversation_id`、`run_id` 或 `message_id` 一律表现为 404，不返回资源是否存在、
运行状态或证据内容。

## 4. SSE 与回答结构

SSE 事件为 `start`、`status`、`delta`、`complete` 和 `error`。`status.stage` 只允许：

```text
understanding
retrieving
querying_finance
analyzing
generating
finalizing
```

`complete` 及历史助手消息按向后兼容方式返回：

- `answer`：通过数值 Grounding、引用和风险策略校验的最终文本；
- `citations[]`：后端从本轮检索白名单映射出的知识引用；
- `evidence[]`：来源工具、统计期间、币种、事实、警告和计算口径；
- `data_as_of`：本轮财务工具中最新的数据时间；
- `risk_notice`：高风险投资问题的统一风险提示。

前端必须把财务证据与知识引用分区展示，不能把工具结果伪装成文档引用。

## 5. 错误与降级

- 参数不完整：要求用户澄清，不扩大时间范围或猜测对象；
- 财务查询失败：返回安全错误，不泄露数据库异常；
- 行情或汇率缺失/过期：保留原始分币种结果并展示警告；
- 知识检索为空：明确说明无可用资料，不生成引用；
- 伪造引用、金额、行情、工具名或内部标识：首次拒绝并允许一次受控重答，仍失败则终止；
- 不同币种：只有存在满足新鲜度要求的直接或反向汇率证据时才生成换算汇总。
