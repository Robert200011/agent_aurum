# P6.1 可观测性底座

开发环境默认只启用 JSON 日志和 `/metrics`，Trace 导出关闭，不依赖外部观测服务。

启动完整观测栈：

```powershell
docker compose -f compose.yaml -f compose.observability.yaml up -d --build
```

本机入口：Prometheus `http://127.0.0.1:9090`，Grafana `http://127.0.0.1:3000`。
`GRAFANA_ADMIN_PASSWORD` 必须在 `.env` 中设置。API 的 `/metrics` 只在 Compose
内部由 Prometheus 抓取；生产网关不得把该路径暴露到公网。

Collector 先执行尾部采样：错误 Trace 全部保留，成功 Trace 保留 5%。当前默认使用
`debug` exporter 验证链路；接入真实 Trace 后端时只需替换
`deploy/otel-collector/config.yaml` 的 exporter，不需要修改应用代码。

日志与 Trace 禁止记录请求体、用户问题、Prompt、回答、财务明细和文档正文。指标标签
只允许路由模板、状态、Provider、模型和工具名等低基数值。
