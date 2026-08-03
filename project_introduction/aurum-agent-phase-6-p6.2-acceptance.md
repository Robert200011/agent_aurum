# 阶段六 P6.2 验收报告：用户/模型配额与最小安全缓存

> 验收日期：2026-08-02  
> 结论：基本完成，可进入 P6.3；计费套餐后台、最终回答缓存和财务聚合缓存不在本批范围。

## 1. 本批交付

- Redis Lua 在同一原子操作内检查并占用用户/全局问答次数、每日模型 Token 和 Agent
  并发；所有并发租约带 TTL；
- 问答前预留 Token，DashScope Provider 返回用量后按一次业务运行的全部模型调用累计
  实际 Token；成功、异常和显式取消都会结算并释放租约；
- 普通与 SSE 问答都在创建 Agent Run 和调用模型前占用额度；超限返回稳定错误码、429 与
  `Retry-After`；Redis 不可用时拒绝聊天和上传；
- 文档上传在对象存储写入前检查用户次数、每日容量和用户/全局处理并发，租约随任务 ID
  交给 Worker，在任务成功或最终失败时释放，异常进程由 TTL 兜底；
- 只缓存项目内已发布知识库检索结果中的 Chunk/版本/知识库标识、分数和算法状态；不缓存
  查询、正文、最终回答、Token、流水、Checkpoint 或 SSE；
- Cache Key 包含用户不可逆哈希、项目、知识库配置与发布时间、当前文档版本状态、查询哈希、
  Embedding、Reranker 和检索参数；短 TTL 加随机抖动，并使用 `SET NX EX` 单飞锁；
- 缓存命中后仍从 PostgreSQL 重新加载 Chunk，并检查活动项目绑定、知识库发布状态、当前
  发布版本及文档启用/删除状态；Redis 缓存故障自动旁路；
- Prometheus 新增配额拒绝、当前并发和配额存储错误，复用 P6.1 缓存命中与耗时指标。

## 2. 稳定错误码

用户与全局请求、Token、Agent 并发以及上传次数、容量和处理并发均有独立
`quota_*_exceeded` 错误码。配额存储不可用返回 503 和
`quota_store_unavailable`，不会静默放行新的高成本任务。

## 3. 验证结果

```powershell
.\.venv\Scripts\python.exe -m pytest
ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
docker compose config --quiet
```

- 后端共收集 181 项测试，174 项通过，真实 PostgreSQL 凭据未提供的 7 项集成测试按预期
  跳过；
- Ruff 与 Mypy 通过；
- 使用本地 Redis 7.4 验证并发租约无法绕过、实际 Token 结算后可重新占用；
- 使用本地 Redis 7.4 验证上传任务租约绑定、并发拒绝和 Worker 终态释放；
- 使用真实 Redis 验证缓存写入/命中、单飞锁持有者校验释放及测试键清理；
- 单元测试覆盖稳定拒绝码、重复结算、配额存储 fail-closed、跨 Provider Token 累计和缓存
  值不包含查询/正文/回答。

## 4. 已知边界

- 第一版为环境变量统一策略，不提供套餐、计费账单、配额管理后台和动态热更新；
- Redis 是临时配额与缓存状态，不替代 PostgreSQL 中的消息、Agent Run 和引用审计事实；
- 仅缓存已发布知识检索结果。财务聚合需先证明性能收益并补齐写后版本失效，最终回答继续
  明确禁止缓存；
- 当前单飞等待采用短时有界轮询，锁失效或 Redis 故障时允许回源，以可用性优先且不绕过
  数据库权限检查。
