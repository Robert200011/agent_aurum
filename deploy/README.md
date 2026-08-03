# Deployment assets

Production reverse-proxy, container, and infrastructure manifests belong in this directory.

P6.1 的 OpenTelemetry Collector、Prometheus、Grafana 和告警资源位于本目录对应
子目录，启动方式见 [observability/README.md](observability/README.md)。

P6.2 的配额与检索缓存复用运行时 Redis，不新增服务。部署前必须按实例容量显式审阅
`AURUM_QUOTA_*` 与 `AURUM_RETRIEVAL_CACHE_*`；Redis 故障时模型和上传入口拒绝新任务，
检索缓存则自动旁路。

P6.4 的加密备份、隔离恢复、数据保留与每日任务入口位于 `deploy/scripts/`，完整密钥边界、
RPO/RTO 和演练流程见 [backup-policy.md](backup-policy.md)。

P6.5 的单机生产栈位于 `compose.production.yaml`，蓝绿发布、观测决策和回滚入口位于
`scripts/release.ps1`、`scripts/rollback.ps1`。正式发布步骤与边界见
[release-runbook.md](release-runbook.md)。
