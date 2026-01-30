# Backup and Retention

## Retention Policy
- Output artifacts: retain for `retention_days` (configurable).
- Audit logs: rotate via `audit_max_bytes` and `audit_max_files`.

## Cleanup Procedure
Use the cleanup command to purge old files:
```
waveos cleanup --path ./out --days 7
```

## Backup Recommendations
- Store evidence packs in object storage.
- Keep at least one previous bundle in history for rollback.
