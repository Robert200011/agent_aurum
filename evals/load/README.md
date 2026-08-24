# HTTP/SSE 负载配置

配置由 `scripts/run_phase6_load.py` 执行，并输出不含请求或响应正文的 JSON 报告。阈值固定为
5xx/非预期状态低于 1%、网络错误和隔离标记为 0、P95 不超过锁定基线的 120%，同时检查 SSE
连接和数据库连接池是否在运行后持续增长。

## local-smoke

```powershell
.\.venv\Scripts\python.exe scripts\run_phase6_load.py `
  --profile evals\load\local-smoke.json
```

可选 SSE 场景需要通过进程环境提供：

- `AURUM_LOAD_ACCESS_TOKEN`
- `AURUM_LOAD_CONVERSATION_ID`
- `AURUM_LOAD_OTHER_USER_MARKER`

不要把 Token 或用户数据写入配置、基线或报告。

## single-node-release

候选发布档要求隔离测试用户和会话，并验证会话列表、真实模型财务问答和 SSE。通过进程环境注入
`AURUM_LOAD_BASE_URL`、`AURUM_LOAD_ACCESS_TOKEN`、`AURUM_LOAD_CONVERSATION_ID` 和
`AURUM_LOAD_OTHER_USER_MARKER`。首次稳定候选运行后只能通过评审更新基线，不能为通过回归而
静默放宽阈值。
