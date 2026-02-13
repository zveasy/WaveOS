# Production Go-Live Checklist

Use this checklist before deploying Wave OS to production. See [Deployment](DEPLOYMENT.md) and [Rollout Checklist](ROLLOUT_CHECKLIST.md) for detailed steps.

## Pre-deployment

- [ ] **License** — Set `WAVEOS_LICENSE_KEY` or `WAVEOS_LICENSE_PATH` in the deployment environment. Do not use `WAVEOS_LICENSE_SKIP` in production.
- [ ] **Secrets** — Configure a secrets provider (Vault/AWS/GCP) and least-privilege access. No secrets in config files or image.
- [ ] **Config** — Use a validated config file or env; set `WAVEOS_CONFIG` if using a file. Verify with `waveos health-check`.
- [ ] **RBAC** — Set `WAVEOS_AUTH_TOKENS` (or equivalent) and use `--token` or equivalent for automated calls. Restrict admin tokens.
- [ ] **Audit** — Enable audit logging (`WAVEOS_AUDIT_ENABLED=true`) and set `WAVEOS_AUDIT_LOG_PATH`. Ensure log rotation (`WAVEOS_AUDIT_LOG_MAX_BYTES`, `WAVEOS_AUDIT_LOG_MAX_FILES`).

## Observability

- [ ] **Logging** — Use `WAVEOS_LOG_FORMAT=json` and `WAVEOS_LOG_LEVEL=INFO` (or `WARN` in prod). Ship logs to your aggregation pipeline.
- [ ] **Metrics** — Set `WAVEOS_METRICS_PORT` (e.g. 9109) and configure Prometheus (or equivalent) to scrape the `/metrics` endpoint.
- [ ] **Tracing** — Optional: set `WAVEOS_OTEL_ENDPOINT` and install the `otel` extra so spans are exported.
- [ ] **Alerting** — Configure at least one alert route (webhook, Slack, or email) and set the corresponding `WAVEOS_ALERT_*` variables. Test in staging.

## Runtime

- [ ] **Health checks** — Use `waveos health-check` for K8s liveness/readiness probes (see [Deployment](DEPLOYMENT.md#health-and-readiness-k8s)).
- [ ] **Resource limits** — Set `max_memory_mb` and `max_cpu_seconds` in config if you use resource limits; align with K8s requests/limits.
- [ ] **Graceful shutdown** — Ensure orchestrator sends SIGTERM and allows a short grace period so Wave OS can flush logs and shut down cleanly.

## Post-deployment

- [ ] **Verify** — Run a single pipeline (sim → baseline → run) and confirm outputs (e.g. `report.html`, `health_summary.json`) and metrics.
- [ ] **Runbooks** — Confirm [Runbooks](RUNBOOKS.md) and escalation paths are known to on-call.
- [ ] **Backup/retention** — Apply [Backup and Retention](BACKUP_RETENTION.md) policy for reports, events, and audit logs.

## CLI exit codes (for automation)

All commands use the same convention so scripts and orchestrators can react consistently:

| Code | Meaning |
|------|--------|
| 0    | Success |
| 1    | Usage or input error (e.g. missing baseline, invalid args, no subcommand) |
| 2    | Configuration error (invalid config file, missing config, missing HMAC key) |
| 3    | License or authorization error (license invalid, access denied) |

Use these in scripts or orchestrators to decide retries or alerts. See also [Operator Guide](OPERATOR_GUIDE.md#exit-codes-automation).
