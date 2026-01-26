# Alerting

## Destinations
- Webhook (JSON POST)
- Slack webhook (via `alert_slack_webhook_url`)
- Email stub (placeholder)

## Routing Rules
Define destinations per environment:

### Dev
- Webhook only (WARN/ERROR)

### Staging
- Webhook + Slack (WARN/ERROR)

### Prod
- Webhook + Slack + Email (ERROR only)

## Configuration Example (TOML)
```toml
alert_webhook_url = "https://example.com/webhook"
alert_slack_webhook_url = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
alert_email_to = "ops@example.com"
```
