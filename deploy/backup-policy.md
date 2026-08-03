# P6.4 备份、恢复与数据保留策略

## 恢复目标与权威数据

- 单机生产基线：RPO 24 小时，RTO 4 小时，每日执行一次全量备份。
- PostgreSQL 与 MinIO 是权威数据；Redis 只保存可重建的配额、租约、缓存和队列状态。
- 正式备份必须复制到不同磁盘、主机或受控对象存储。仅在同一目录复制不算异地副本。

## 备份格式与密钥

`deploy/scripts/backup.ps1` 生成 PostgreSQL custom dump、MinIO 对象版本/删除标记及对象
SHA-256 清单，并将数据库计数、Alembic、RLS、Git/模型/迁移版本和密钥标识写入加密清单。
整个归档使用随机 nonce 的 AES-256-GCM 加密，外部只留下密文 SHA-256、大小、时间和
`key_id`。脚本不会输出数据库密码、S3 密钥、JWT、checkpoint 密钥或备份密钥。

正式环境必须从外部密钥系统注入以下值：

- `AURUM_BACKUP_ENCRYPTION_KEY`：随机 32 字节的 base64 编码值；
- `AURUM_BACKUP_KEY_ID`、`AURUM_LANGGRAPH_KEY_ID`、`AURUM_JWT_KEY_ID`：可审计标识；
- 可选的最小权限 `AURUM_BACKUP_OBJECT_STORAGE_ACCESS_KEY/SECRET_KEY`。

本地基线未配置专用备份 S3 账户时会使用 MinIO 管理凭据；生产环境不得沿用此降级方式。
密钥值不得放入仓库、任务参数、日志、备份清单或演练报告。

## 运行与调度

```powershell
$env:AURUM_BACKUP_ENCRYPTION_KEY = '<external-secret>'
.\deploy\scripts\backup.ps1 `
  -OutputDirectory 'C:\AurumBackups\primary' `
  -ReplicaDirectory 'D:\AurumBackups\replica' `
  -RetentionDays 30
```

`install-backup-task.ps1` 可注册每日 02:00 的 Windows 计划任务，任务本身不保存密钥；运行
账户必须从机器级密钥注入或外部密钥代理获得密钥。Linux 部署应以相同参数建立 systemd
timer/cron。备份成功会原子更新 `aurum_backup.prom`，由 node-exporter textfile collector
采集；缺少或超过 25 小时未更新会触发 `AurumBackupOverdue`。

## 安全恢复

恢复只允许全新数据库和全新 bucket；目标与源同名或目标已经存在都会在写入前失败。失败后
保留隔离目标供排查，不自动删除或覆盖任何实例。

```powershell
$env:AURUM_BACKUP_ENCRYPTION_KEY = '<external-secret>'
.\deploy\scripts\restore.ps1 `
  -Backup 'D:\AurumBackups\replica\aurum-....aurum-backup' `
  -DestinationDatabase 'aurum_restore_20260802' `
  -DestinationBucket 'aurum-restore-20260802' `
  -Report '.test-results\p6.4\restore.json' `
  -ConfirmNewTargets
```

恢复后自动校验密文及内部文件哈希、Alembic Head、所有关键表计数、RLS/Policy、财务汇总、
引用外键、聊天关联、checkpoint 解密、当前对象 SHA-256，以及已发布原始文档的数据库键/
哈希。解析文本属于可从原始文档重建的派生缓存，缺失会记录但不阻止恢复，并计算实际
RPO/RTO。真实发布前
还应让隔离 API 指向恢复目标，执行 P6.3 候选环境的小流量聊天冒烟。

## 数据保留

机器可读策略位于 `deploy/retention-policy.json`。首版自动清理仅包含过期 30 天以上的 refresh
token 和 90 天以上的检索日志；默认命令只预览，`-Apply` 后才执行，并新增
`operations.retention_applied` 审计记录。聊天、审计日志需先完成归档或主体请求审批；Trace、
Prometheus、容器日志和备份由各自后端生命周期控制。

```powershell
.\deploy\scripts\retention.ps1
.\deploy\scripts\retention.ps1 -Apply -Operator 'ops-user'
```

加密备份默认保留 30 天且始终保留最新一份。任何保留周期变更都应修改策略版本、评审后再
应用；不要使用宽范围文件删除命令代替脚本限定的备份后缀清理。
