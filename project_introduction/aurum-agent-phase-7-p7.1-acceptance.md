# Aurum Agent P7.1 计划与回答协议验收报告

> 验收日期：2026-08-16  
> 范围：财务领域化升级 P7.1，不包含 P7.2 确定性指标与数据质量、P7.3 Graph 节点拆分

## 1. 交付结论

P7.1 已完成。Agent 在进入现有能力调用循环前，会由服务端生成并校验版本化的
`FinancialAnalysisPlan`；回答深度支持显式指定和自动判断；深度回答必须经过稳定章节解析、内部
`FinancialAnswerDraft` 构建、Markdown 重渲染以及原有财务 Grounding、引用和输出安全校验。

本阶段没有增加额外 Planner 模型调用，也没有提前引入 P7.2 指标计算或 P7.3 多节点编排。

## 2. 已实现能力

- 新增 `auto/brief/standard/deep` 请求契约；未指定时保持 `auto`，兼容现有 API 和前端调用；
- 自动深度规则把单事实查询识别为 `brief`，一般分析识别为 `standard`，详细、全面、诊断、比较和
  改善类请求识别为 `deep`；显式深度优先于自动判断；
- 新增不可变 `FinancialAnalysisPlan`，只允许白名单分析类型、数据类别、指标名、时间范围、输出
  章节和风险等级，不接受 SQL、任意工具名、内部 UUID 或可执行代码；
- Planner 在模型执行前运行，并把计划和回答协议作为受控服务端上下文传入现有能力循环；模型仍不能
  因计划内容绕过工具注册表、参数 Schema、用户隔离或只读权限；
- 单一最近交易、账户余额和通用概念查询可进入快捷路径，最多 2 个模型决策轮和 1 次能力调用；复杂
  问题即使显式要求简短，也不会错误进入单调用快捷路径；
- `deep` 回答固定使用“核心结论、数据范围与口径、关键指标、主要发现、风险和异常、行动建议、
  数据限制”章节，高风险投资问题额外要求“投资风险提示”；
- 深度回答先解析为 `FinancialAnswerDraft`，服务端验证章节完整性、顺序和非空内容后重新渲染；失败时
  复用现有一次受控修复，第二次失败返回安全错误；
- 投资风险策略、财务数值 Grounding、文档引用校验和输出安全校验继续作用于最终渲染文本；
- `AgentRun.detail` 保存计划版本、分析类型、最终深度、快捷路径、白名单计划和协议校验状态，不保存
  用户问题、回答正文或隐藏思维链；
- 重新生成会继承原运行请求的回答深度；最新运行诊断接口新增 `analysis_type`、`response_depth` 和
  `fast_path` 字段；
- Graph 版本升级为 `finance-domain-plan-v1`，便于发布 Manifest、灰度和回滚区分。

## 3. 主要代码位置

| 位置 | 职责 |
| --- | --- |
| `app/agents/contracts.py` | 财务计划、时间范围、白名单枚举和内部回答草稿契约 |
| `app/agents/financial_protocol.py` | 深度判断、确定性 Planner、章节解析和 Markdown 渲染 |
| `app/agents/capability_agent.py` | 执行前建计划、注入协议和快捷路径预算 |
| `app/agents/graph.py` | 深度回答协议校验、一次修复和原安全链组合 |
| `app/services/answering.py` | 在非流式与流式图输入输出间传递计划和草稿 |
| `app/services/chat.py` | 持久化安全计划摘要并在重新生成时继承深度 |
| `app/api/schemas/chat.py` | 公开请求深度与运行诊断字段 |
| `web/src/services/chat.ts` | 向后兼容地发送回答深度 |

## 4. 自动化验收

P7.1 新增测试覆盖：

- 自动深度判断和显式覆盖；
- 复杂问题的分析类型、时间范围、数据白名单和稳定章节；
- 简单查询快捷路径及复杂查询不误入快捷路径；
- 账户余额查询只规划所需的私有数据；
- 高风险计划强制风险提示；
- 深度回答解析、草稿字段、稳定重渲染、缺失及乱序章节拒绝；
- API 深度枚举校验。

验收命令：

```powershell
pytest
ruff check .
mypy app
cd web
npm run type-check
```

执行结果：

| 检查 | 结果 |
| --- | --- |
| `pytest` | 188 passed，7 skipped（外部集成条件未提供） |
| `ruff check .` | 通过 |
| `mypy app` | 144 个源文件通过 |
| `npm run check` | 14 个测试文件、47 个前端测试通过，TypeScript 与 ESLint 通过 |
| `git diff --check` | 通过，仅有仓库既有 CRLF 转换提示 |

## 5. 兼容性与已知边界

- `brief` 和 `standard` 保持模型自然文本兼容；本阶段只对 `deep` 强制稳定 Markdown 章节；
- P7.1 的 `calculations` 仅描述后续需要的白名单指标，不授权模型自行计算；具体公式、版本和证据标识
  在 P7.2 实现；
- 当前 Planner 是低延迟确定性规则，不增加一次模型规划调用。随着领域评测集扩大，可以扩展规则或
  引入受约束的模型分类，但输出仍必须通过同一 Schema 和服务端能力映射；
- 本阶段复用现有 `AgentRun.detail`，未增加数据库表；是否引入独立计划表留待审计和恢复需求稳定后决定；
- SSE 仍沿用现有阶段事件。真实 `plan_created` 等细粒度事件属于 P7.3，不在本次范围；
- 财务数据完整性、币种、同步状态和确定性指标尚未由统一层评估，属于 P7.2。

## 6. 下一阶段入口

P7.2 应直接消费本阶段的 `FinancialAnalysisPlan.required_data` 和 `calculations`，实现数据完整性报告、
版本化财务指标与证据 ID。P7.2 不应把指标计算重新交给模型，也不应改变 P7.1 已建立的计划白名单、
回答深度和安全校验顺序。
