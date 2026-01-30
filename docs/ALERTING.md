# Alerting

## Destinations
- Webhook (JSON POST)
- Slack webhook (via `alert_slack_webhook_url`)
- Email via SMTP or SES

## Routing Rules
Define destinations per environment:

### Dev
- Webhook only (WARN/ERROR)

### Staging
- Webhook + Slack (WARN/ERROR)

### Prod
- Webhook + Slack + Email (ERROR only)

### Severity Tuning
- `alert_min_level` sets the default threshold for all destinations.
- Per-destination overrides: `alert_webhook_min_level`, `alert_slack_min_level`, `alert_email_min_level`.

## Configuration Example (TOML)
```toml
alert_min_level = "WARN"
alert_webhook_url = "https://example.com/webhook"
alert_webhook_min_level = "WARN"
alert_slack_webhook_url = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
alert_slack_min_level = "WARN"
alert_email_to = "ops@example.com"
alert_email_min_level = "ERROR"
alert_email_from = "waveos@example.com"
alert_email_provider = "smtp"
alert_email_smtp_host = "smtp.example.com"
alert_email_smtp_port = 587
alert_email_smtp_user = "smtp-user"
alert_email_smtp_password_secret = "SMTP_PASSWORD"
alert_email_ses_region = "us-east-1"
```
