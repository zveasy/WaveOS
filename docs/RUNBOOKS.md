# Runbooks

## Startup
1) Validate config and environment variables.
2) Ensure output directories are writable.
3) Run `waveos sim`/`baseline`/`run` or production pipeline.

## Shutdown
1) Send SIGTERM to allow graceful shutdown.
2) Confirm logs report graceful shutdown completion.

## Failure Recovery
- If normalization fails: inspect input schema and validation errors.
- If scoring fails: check baseline and run stats for missing entities.
- If report fails: verify Jinja templates and output directory permissions.

## Troubleshooting
- Missing outputs: confirm output directory permissions and disk space.
- Metrics endpoint not reachable: set `WAVEOS_METRICS_PORT` and ensure the port is open.
- Logging format unexpected: set `WAVEOS_LOG_FORMAT=json|text`.
- Dependency audit failures: check `pip-audit` output and update `.pip-audit.toml`.

## Incident Response
- Capture logs and outputs.
- Identify affected components and data inputs.
- Escalate to engineering with repro steps.

## On-Call Escalation
1) SEV-1: data loss, pipeline failure, or security incident → page primary + lead.
2) SEV-2: partial failure or degraded output quality → page primary.
3) SEV-3: non-blocking issues → file ticket and include logs.
