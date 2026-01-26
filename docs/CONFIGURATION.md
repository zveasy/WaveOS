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
- `feature_flags`: map of flags (boolean)
- `schema_version`: config schema version
- `auth_tokens`: map of tokens to roles
- `secrets_provider`: env|vault|aws|gcp

## Example (TOML)
```toml
log_format = "json"
log_level = "INFO"
metrics_port = 9109
otel_endpoint = "http://localhost:4318/v1/traces"
alert_webhook_url = "https://example.com/webhook"
alert_slack_webhook_url = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
alert_email_to = "ops@example.com"
schema_version = 1
feature_flags = { explainability = true }
auth_tokens = { "token-1" = "admin", "token-2" = "operator" }
secrets_provider = "env"
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
  "schema_version": 1,
  "feature_flags": { "explainability": true },
  "auth_tokens": { "token-1": "admin", "token-2": "operator" },
  "secrets_provider": "env"
}
```
