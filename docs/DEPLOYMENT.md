# Deployment Guide

## Local
1) Install dependencies: `pip install -e .`
2) Generate demo data: `waveos sim --out ./demo_data`
3) Build baseline: `waveos baseline --in ./demo_data/baseline`
4) Run analysis: `waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out`
5) Render report: `waveos report --in ./out --open`

## Container (Local)
Use `docker-compose.yml` for a local container runtime. Mounts the repo and runs a placeholder command.

## Configuration
- `WAVEOS_LOG_FORMAT=json|text` (default: json)
- `WAVEOS_LOG_LEVEL=INFO|DEBUG|...`
- `WAVEOS_METRICS_PORT=9109` to enable Prometheus metrics endpoint
- `WAVEOS_OTEL_ENDPOINT=http://localhost:4318/v1/traces` to enable tracing
- `WAVEOS_CONFIG=path/to/config.toml` to load config file
- `WAVEOS_ALERT_WEBHOOK_URL=https://example.com/webhook` for WARN/ERROR alerts
- `WAVEOS_ALERT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`
- `WAVEOS_ALERT_EMAIL_TO=ops@example.com`
- `WAVEOS_ALERT_EMAIL_FROM=waveos@example.com`
- `WAVEOS_ALERT_EMAIL_PROVIDER=smtp|ses`
- `WAVEOS_ALERT_EMAIL_SMTP_HOST=smtp.example.com`
- `WAVEOS_ALERT_EMAIL_SMTP_PORT=587`
- `WAVEOS_ALERT_EMAIL_SMTP_USER=smtp-user`
- `WAVEOS_ALERT_EMAIL_SMTP_PASSWORD_SECRET=SMTP_PASSWORD`
- `WAVEOS_ALERT_EMAIL_SES_REGION=us-east-1`
- `WAVEOS_SECRETS_PROVIDER=env|vault|aws|gcp`
- `WAVEOS_AUDIT_LOG_PATH=out/audit.jsonl`
- `WAVEOS_AUDIT_ENABLED=true|false`
- `WAVEOS_AUDIT_LOG_MAX_BYTES=5000000`
- `WAVEOS_AUDIT_LOG_MAX_FILES=5`

## Secrets
Wave OS currently reads secrets from environment variables only.
Planned integrations: Vault, AWS Secrets Manager, GCP Secret Manager.

## Authentication
- `WAVEOS_AUTH_TOKENS=token1=admin,token2=operator` to map tokens to roles.
- `--token <token>` on CLI to authenticate.

## Secrets Managers
- Vault: set `WAVEOS_VAULT_ADDR`, `WAVEOS_VAULT_PATH`. `WAVEOS_VAULT_TOKEN` is **dev-only**; prefer workload identity in production.
- AWS Secrets Manager: set `WAVEOS_AWS_REGION`, optionally `WAVEOS_AWS_SECRET_ID`.
- GCP Secret Manager: set `WAVEOS_GCP_PROJECT`.
- JSON test adapters (**dev/testing only**; not recommended for production):
  - `WAVEOS_VAULT_SECRETS_JSON='{"key":"value"}'`
  - `WAVEOS_AWS_SECRETS_JSON='{"key":"value"}'`
  - `WAVEOS_GCP_SECRETS_JSON='{"key":"value"}'`
