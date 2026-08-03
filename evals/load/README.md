# P6.3 load profiles

两档配置均由 `scripts/run_phase6_load.py` 执行，并输出不含请求/响应正文的 JSON 报告。
阈值固定为 5xx/非预期状态低于 1%、网络错误和隔离标记为 0、P95 不得超过锁定基线的
120%，同时检查 SSE、入库队列和数据库连接池是否在运行后持续增长。

## local-smoke

默认只要求本机 API 已启动，可直接运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\local-smoke.json
```

Fake SSE 场景需要显式提供以下隔离夹具；缺少时会在报告中标为可选跳过：

- `AURUM_LOAD_ACCESS_TOKEN`
- `AURUM_LOAD_CONVERSATION_ID`
- `AURUM_LOAD_OTHER_USER_MARKER`：另一个测试用户专属且绝不应出现在响应中的标记

运行 Fake SSE 前应确认测试实例使用 Fake Chat Provider。不要把 Token 写入配置或报告。

## single-node-release

候选发布档的所有场景都是必选。先创建隔离测试用户、管理员、已发布知识库、会话、一份小型
Markdown 文档和一个可查询的入库任务，再通过进程环境注入：

- `AURUM_LOAD_BASE_URL`
- `AURUM_LOAD_ACCESS_TOKEN`、`AURUM_LOAD_ADMIN_TOKEN`
- `AURUM_LOAD_CONVERSATION_ID`、`AURUM_LOAD_KNOWLEDGE_BASE_ID`
- `AURUM_LOAD_DOCUMENT_PATH`、`AURUM_LOAD_INGESTION_JOB_ID`、`AURUM_LOAD_RUN_ID`
- `AURUM_LOAD_OTHER_USER_MARKER`、`AURUM_LOAD_OTHER_PROJECT_MARKER`

文档上传使用 `AURUM_LOAD_RUN_ID` 构造幂等键；重复执行时必须换新 Run ID。入库恢复轮询可
使用预先制造并恢复的任务 ID，报告还会记录运行后的队列深度。候选环境必须另行保存 API、
Worker、PostgreSQL、Redis、MinIO 和模型版本；配置文件中的首版单机基线是暂定值，首次
稳定候选运行后应只通过评审更新，不能为了让回归通过而静默放宽。
