# P6.5 生产发布与回滚运行手册

本手册适用于首版单机 Docker Compose 生产基线。应用域名和对象下载域名只公开同一个 Caddy
Gateway 的 80/443 端口；API、Web、
Redis、Grafana 和 MinIO Console 不绑定宿主机端口，PostgreSQL、MinIO API 与 Prometheus
维护端口仅绑定 `127.0.0.1`。该方案不是 Kubernetes 或多地域容灾方案。

## 1. 发布前准备

1. 从 `deploy/production.env.example` 创建服务器专用环境文件并从密钥系统注入密钥；不得提交环境文件。
2. 使用 Git SHA 对应的不可变镜像标签或 digest，禁止生产清单使用 `latest`。
3. 将 `deploy/gateway/active-upstream.example.caddy` 复制到持久化发布状态目录作为初始蓝槽配置。
4. 为 MinIO 配置含 `minio` DNS SAN 的服务端证书和受信 CA，确认主备两个备份位置可写、
   备份加密密钥可用，并确认应用域名、对象域名和证书解析正确。
5. CI 必须通过后端/前端测试、迁移检查、阶段六门禁、依赖审计、SBOM 和镜像漏洞扫描。

先验证渲染后的 Compose 配置：

```powershell
docker compose --env-file C:\Aurum\production.env `
  -f deploy\compose.production.yaml config --quiet
```

## 2. 蓝绿发布

候选镜像先在非活动槽启动，一次性迁移任务采用 Expand-Migrate-Contract，自动创建发布前加密
备份并执行候选实例健康检查和阶段六门禁。生产切流必须显式传入 `-ApproveCutover`。

```powershell
.\deploy\scripts\release.ps1 -Mode production -CandidateSlot green `
  -ApiImage registry.example/aurum-api@sha256:<digest> `
  -WebImage registry.example/aurum-web@sha256:<digest> `
  -EnvFile C:\Aurum\production.env `
  -StateDirectory C:\Aurum\release-state `
  -EvidenceDirectory C:\Aurum\release-evidence `
  -BackupDirectory D:\AurumBackups\primary `
  -BackupReplicaDirectory E:\AurumBackups\replica `
  -StartStack -ApproveCutover
```

切流后脚本连续检查槽位、HTTP 错误率、P95、API 5xx、模型失败、队列深度和数据库连接池。
任一观测命令异常或阈值拒绝都会立即调用回滚脚本。SSE 通过 Caddy 流式转发，旧连接由
Gateway 的 30 秒优雅窗口排空。

## 3. 人工回滚

```powershell
.\deploy\scripts\rollback.ps1 -EnvFile C:\Aurum\production.env `
  -StateDirectory C:\Aurum\release-state `
  -EvidenceDirectory C:\Aurum\release-evidence
```

回滚只原子切换 Gateway 到上一槽并验证健康，不自动执行 Alembic `downgrade`。不兼容数据变更
必须通过前滚修复；需要恢复数据时按 `backup-policy.md` 恢复到隔离目标，经校验和审批后处理。

## 4. 发布证据与停止条件

每次发布保留 Manifest、质量门禁、HTTP 观测、Prometheus 指标、决策、备份 sidecar 和回滚
观测。Manifest 记录 Git、镜像、迁移、Graph、Prompt、数据集、配置、备份和操作人。以下任一
情况停止发布：错误率达到 1%、P95 超过 1000ms、模型错误率达到 1%、队列深度超过 20、
数据库连接池比例达到 90%、槽位不一致、备份/迁移/观测失败或出现数据隔离异常。

## 5. 本地演练

本地演练使用独立 Compose 项目和独立数据卷，不修改开发环境数据：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File deploy\scripts\rehearse-release.ps1 -ReuseApiImage -ReuseWebImage
```

脚本完成绿槽成功切换后主动停止候选 API，随后验证回滚到蓝槽。演练专用 Web 镜像可通过
`-OfflineWebImage` 从已构建的 `web/dist` 创建；生产镜像必须使用 `Dockerfile.web` 的可复现构建。
