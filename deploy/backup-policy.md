# PostgreSQL 备份、恢复与数据保留策略

## 恢复目标与权威数据

- 单机生产基线：RPO 24 小时，RTO 4 小时，每日执行一次全量备份；
- PostgreSQL 是用户、财务、会话、长期记忆、审计和 Checkpoint 的权威存储；
- Redis 只保存可重建的配额、租约和缓存状态，不进入正式备份；
- 正式备份必须复制到不同磁盘、主机或受控远端存储。

## 备份格式与密钥

`deploy/scripts/backup.ps1` 生成 PostgreSQL custom dump，并把关键表计数、Alembic、RLS、财务
汇总、配置白名单和密钥标识写入清单。整个归档使用随机 nonce 的 AES-256-GCM 加密，外部只
留下密文 SHA-256、大小、时间和 `key_id`。

正式环境必须从外部密钥系统注入：

- `AURUM_BACKUP_ENCRYPTION_KEY`：随机 32 字节的 base64 编码值；
- `AURUM_BACKUP_KEY_ID`、`AURUM_LANGGRAPH_KEY_ID`、`AURUM_JWT_KEY_ID`：可审计标识。

密钥值不得写入仓库、任务参数、日志、备份清单或演练报告。

## 运行与调度

```powershell
$env:AURUM_BACKUP_ENCRYPTION_KEY = '<external-secret>'
.\deploy\scripts\backup.ps1 `
  -OutputDirectory 'C:\AurumBackups\primary' `
  -ReplicaDirectory 'D:\AurumBackups\replica' `
  -RetentionDays 30
```

`install-backup-task.ps1` 可注册每日任务。备份成功会更新 `aurum_backup.prom`，供监控检查备份
是否超过 25 小时未刷新。

## 安全恢复

恢复只允许写入不存在的新数据库；目标与源同名或已经存在都会在写入前失败。

```powershell
$env:AURUM_BACKUP_ENCRYPTION_KEY = '<external-secret>'
.\deploy\scripts\restore.ps1 `
  -Backup 'D:\AurumBackups\replica\aurum-....aurum-backup' `
  -DestinationDatabase 'aurum_restore_20260824' `
  -Report '.test-results\restore.json' `
  -ConfirmNewTargets
```

恢复后自动校验密文及内部文件哈希、Alembic Head、关键表计数、RLS/Policy 和财务汇总，并计算
实际 RPO/RTO。真实发布前还应让隔离 API 指向恢复目标执行财务查询和长期记忆冒烟。

## 数据保留

机器可读策略位于 `deploy/retention-policy.json`。加密备份默认保留 30 天且始终保留最新一份。
任何保留周期变更都必须先修改策略版本并评审；不得使用宽范围文件删除命令代替脚本限定的备份
后缀清理。
