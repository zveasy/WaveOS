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
- `alert_email_smtp_host`: SMTP host
- `alert_email_smtp_port`: SMTP port
- `alert_email_smtp_user`: SMTP username
- `alert_email_smtp_password_secret`: secret key for SMTP password
- `alert_email_ses_region`: SES region
- `feature_flags`: map of flags (boolean)
- `schema_version`: config schema version
- `auth_tokens`: map of tokens to roles
- `secrets_provider`: env|vault|aws|gcp
- `audit_log_path`: JSONL audit log path
- `audit_enabled`: enable/disable audit logging
- `audit_max_bytes`: rotate when file exceeds size
- `audit_max_files`: number of rotated files to keep

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
alert_email_smtp_host = "smtp.example.com"
alert_email_smtp_port = 587
alert_email_smtp_user = "smtp-user"
alert_email_smtp_password_secret = "SMTP_PASSWORD"
alert_email_ses_region = "us-east-1"
schema_version = 1
feature_flags = { explainability = true }
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
  "alert_email_smtp_host": "smtp.example.com",
  "alert_email_smtp_port": 587,
  "alert_email_smtp_user": "smtp-user",
  "alert_email_smtp_password_secret": "SMTP_PASSWORD",
  "alert_email_ses_region": "us-east-1",
  "schema_version": 1,
  "feature_flags": { "explainability": true },
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
