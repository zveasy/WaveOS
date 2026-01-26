# Rollout Checklist

## Pre-Deploy
- Validate config schema version and feature flags.
- Verify secrets provider connectivity (Vault/AWS/GCP).
- Run `pytest -q` and confirm CI green.
- Confirm alert destinations and routing rules.
- Validate audit log path write permissions.

## Deploy
- Use staging config first: `docs/config/staging.toml`.
- Confirm metrics/traces/logs in observability stack.
- Trigger a test run and verify alerts + report output.

## Post-Deploy
- Promote to prod config: `docs/config/prod.toml`.
- Validate email delivery (SMTP/SES) and Slack webhook.
- Confirm audit logs are written and retained.
- Capture release notes and artifacts checksum verification.

## Promotion Workflow
- Tag release candidate (`vX.Y.Z-rc1`) from staging.
- Run smoke tests and verify alerts/audit logs.
- Promote to prod by tagging `vX.Y.Z` and deploying with `docs/config/prod.toml`.

## Rollback Procedure
- Revert to previous tag and config profile.
- Validate outputs + audit logs.
- Document incident and recovery timeline.
