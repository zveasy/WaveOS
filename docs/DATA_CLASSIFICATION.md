# Data Classification

## Classes
- **Public**: marketing content, public docs.
- **Internal**: operational metadata, non-sensitive metrics.
- **Confidential**: telemetry samples, events, audit logs, run reports.
- **Restricted**: secrets, auth tokens, keys, signing material.

## Handling Rules
- **Public/Internal**: no special controls beyond standard logging policies.
- **Confidential**: encrypt at rest where available; limit access to operators.
- **Restricted**: never log; store only in secrets manager; rotate on schedule.

## WaveOS Data Mapping
- Telemetry samples (`telemetry.jsonl`): Confidential
- Health summaries (`health_summary.json`): Confidential
- Events (`events.jsonl`): Confidential
- Audit logs (`audit.jsonl`): Confidential
- Bundles (`bundle.json`, `bundle.sig`): Confidential
- Secrets (`WAVEOS_*_SECRET*`, tokens): Restricted
