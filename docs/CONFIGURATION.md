# Configuration

Wave OS supports config via:
- `--config path/to/config.toml|json`
- `WAVEOS_CONFIG` environment variable
- Environment variables (override file)

## Supported keys
- `log_format`: `json` or `text`
- `log_level`: `INFO`, `DEBUG`, etc.
- `metrics_port`: integer to enable Prometheus endpoint
- `otel_endpoint`: OTLP HTTP endpoint for traces
- `alert_webhook_url`: optional webhook for WARN/ERROR events
- `alert_slack_webhook_url`: optional Slack webhook
- `alert_email_to`: optional email recipient
- `alert_email_from`: email sender
- `alert_email_provider`: smtp|ses
- `alert_min_level`: INFO|WARN|ERROR default threshold for alerts
- `alert_webhook_min_level`: per-destination override
- `alert_slack_min_level`: per-destination override
- `alert_email_min_level`: per-destination override
- `alert_email_smtp_host`: SMTP host
- `alert_email_smtp_port`: SMTP port
- `alert_email_smtp_user`: SMTP username
- `alert_email_smtp_password_secret`: secret key for SMTP password
- `alert_email_ses_region`: SES region
- `waveos_version`: override version string used in run metadata
- `policy_version`: policy bundle version
- `bundle_id`: active bundle identifier
- `bundle_dir`: path to a bundle to build/sign
- `bundle_active_dir`: active bundle install path
- `bundle_history_dir`: bundle history path
- `bundle_state_dir`: bundle state path
- `bundle_hmac_key_secret`: secret name for bundle HMAC key
- `evidence_pack_enabled`: enable evidence pack export
- `enforce_actions`: write enforced actions and emit policy_enforced event
- `recovery_enabled`: enable recovery orchestrator
- `recovery_restart_command`: command to run on ERROR (restart)
- `recovery_degrade_command`: command to run on WARN (degrade)
- `recovery_reboot_command`: command to run for reboot actions
- `watchdog_enabled`: enable watchdog heartbeat file
- `watchdog_path`: watchdog heartbeat file path
- `schedule_interval_seconds`: scheduler interval (seconds)
- `log_spool_path`: append-only log spool path
- `proxy_enabled`: enable proxy stub
- `proxy_mode`: proxy mode (`sanitize`, `tcp_forward`, `http_forward`)
- `proxy_listen_host`: proxy listen host
- `proxy_listen_port`: proxy listen port
- `proxy_target_host`: proxy upstream host
- `proxy_target_port`: proxy upstream port
- `drop_privileges_user`: user to drop privileges to (if running as root)
- `drop_privileges_group`: group to drop privileges to (if running as root)
- `WAVEOS_REDACT_VALUES` (env only): comma-separated values to redact from logs
- `feature_flags`: map of flags (boolean)
- `policy_rules`: list of declarative policy rules
- `schema_version`: config schema version
- `auth_tokens`: map of tokens to roles
- `secrets_provider`: env|vault|aws|gcp
- `audit_log_path`: JSONL audit log path
- `audit_enabled`: enable/disable audit logging
- `audit_max_bytes`: rotate when file exceeds size
- `audit_max_files`: number of rotated files to keep
- `collector_threads`: number of parallel collector threads
- `max_memory_mb`: memory limit (MB)
- `max_cpu_seconds`: CPU time limit (seconds)
- `idempotent_outputs`: write to run-specific subdir if outputs exist
- `retention_days`: cleanup retention window for outputs/logs

## Example (TOML)
```toml
log_format = "json"
log_level = "INFO"
metrics_port = 9109
otel_endpoint = "http://localhost:4318/v1/traces"
alert_webhook_url = "https://example.com/webhook"
alert_slack_webhook_url = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
alert_email_to = "ops@example.com"
alert_email_from = "waveos@example.com"
alert_email_provider = "smtp"
alert_min_level = "WARN"
alert_webhook_min_level = "WARN"
alert_slack_min_level = "WARN"
alert_email_min_level = "ERROR"
alert_email_smtp_host = "smtp.example.com"
alert_email_smtp_port = 587
alert_email_smtp_user = "smtp-user"
alert_email_smtp_password_secret = "SMTP_PASSWORD"
alert_email_ses_region = "us-east-1"
waveos_version = "0.1.0"
policy_version = "policy-1"
bundle_id = "bundle-1"
bundle_active_dir = "out/bundles/active"
bundle_history_dir = "out/bundles/history"
bundle_state_dir = "out/bundles/state"
bundle_hmac_key_secret = "BUNDLE_HMAC_KEY"
evidence_pack_enabled = true
enforce_actions = false
recovery_enabled = false
recovery_restart_command = "/usr/local/bin/restart-service"
recovery_degrade_command = "/usr/local/bin/degrade-mode"
recovery_reboot_command = "/sbin/reboot"
watchdog_enabled = false
watchdog_path = "out/watchdog.txt"
schedule_interval_seconds = 300
log_spool_path = "out/spool.log"
proxy_enabled = false
proxy_mode = "sanitize"
proxy_listen_host = "127.0.0.1"
proxy_listen_port = 9000
proxy_target_host = "127.0.0.1"
proxy_target_port = 9001
drop_privileges_user = "waveos"
drop_privileges_group = "waveos"
collector_threads = 4
max_memory_mb = 2048
max_cpu_seconds = 300
idempotent_outputs = true
retention_days = 7
schema_version = 1
feature_flags = { explainability = true }
policy_rules = [
  { metric = "score", operator = "<=", threshold = 60, action = "RATE_LIMIT", message = "Policy rule triggered." },
  { metric = "meta.charger_faults", operator = ">=", threshold = 1, action = "REROUTE", message = "Charger fault detected." },
  { metric = "meta.current_a", operator = ">", threshold = 200, action = "RATE_LIMIT", message = "Overcurrent detected." }
]
auth_tokens = { "token-1" = "admin", "token-2" = "operator" }
secrets_provider = "env"
audit_log_path = "out/audit.jsonl"
audit_enabled = true
audit_max_bytes = 5000000
audit_max_files = 5
```

## Example Config File
Save as `waveos.toml`:
```toml
log_format = "text"
log_level = "DEBUG"
metrics_port = 9109
otel_endpoint = "http://localhost:4318/v1/traces"
alert_webhook_url = "https://example.com/webhook"
```

## Example (JSON)
```json
{
  "log_format": "json",
  "log_level": "INFO",
  "metrics_port": 9109,
  "otel_endpoint": "http://localhost:4318/v1/traces",
  "alert_webhook_url": "https://example.com/webhook",
  "alert_slack_webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ",
  "alert_email_to": "ops@example.com",
  "alert_email_from": "waveos@example.com",
  "alert_email_provider": "smtp",
  "alert_min_level": "WARN",
  "alert_webhook_min_level": "WARN",
  "alert_slack_min_level": "WARN",
  "alert_email_min_level": "ERROR",
  "alert_email_smtp_host": "smtp.example.com",
  "alert_email_smtp_port": 587,
  "alert_email_smtp_user": "smtp-user",
  "alert_email_smtp_password_secret": "SMTP_PASSWORD",
  "alert_email_ses_region": "us-east-1",
  "waveos_version": "0.1.0",
  "policy_version": "policy-1",
  "bundle_id": "bundle-1",
  "bundle_active_dir": "out/bundles/active",
  "bundle_history_dir": "out/bundles/history",
  "bundle_state_dir": "out/bundles/state",
  "bundle_hmac_key_secret": "BUNDLE_HMAC_KEY",
  "evidence_pack_enabled": true,
  "enforce_actions": false,
  "recovery_enabled": false,
  "recovery_restart_command": "/usr/local/bin/restart-service",
  "recovery_degrade_command": "/usr/local/bin/degrade-mode",
  "recovery_reboot_command": "/sbin/reboot",
  "watchdog_enabled": false,
  "watchdog_path": "out/watchdog.txt",
  "schedule_interval_seconds": 300,
  "log_spool_path": "out/spool.log",
  "proxy_enabled": false,
  "proxy_mode": "sanitize",
  "proxy_listen_host": "127.0.0.1",
  "proxy_listen_port": 9000,
  "proxy_target_host": "127.0.0.1",
  "proxy_target_port": 9001,
  "drop_privileges_user": "waveos",
  "drop_privileges_group": "waveos",
  "collector_threads": 4,
  "max_memory_mb": 2048,
  "max_cpu_seconds": 300,
  "idempotent_outputs": true,
  "retention_days": 7,
  "schema_version": 1,
  "feature_flags": { "explainability": true },
  "policy_rules": [
    { "metric": "score", "operator": "<=", "threshold": 60, "action": "RATE_LIMIT", "message": "Policy rule triggered." },
    { "metric": "meta.charger_faults", "operator": ">=", "threshold": 1, "action": "REROUTE", "message": "Charger fault detected." },
    { "metric": "meta.current_a", "operator": ">", "threshold": 200, "action": "RATE_LIMIT", "message": "Overcurrent detected." }
  ],
  "auth_tokens": { "token-1": "admin", "token-2": "operator" },
  "secrets_provider": "env",
  "audit_log_path": "out/audit.jsonl",
  "audit_enabled": true,
  "audit_max_bytes": 5000000,
  "audit_max_files": 5
}

## Dev-only Notes
- `WAVEOS_VAULT_TOKEN` should be considered **dev-only**; prefer workload identity in production.
- `WAVEOS_*_SECRETS_JSON` adapters are **debug/testing only**, not recommended for production.
```
collector_threads = 4
