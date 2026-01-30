# Compliance Mapping (Draft)

This is a **draft** mapping to common standards. Confirm with your compliance team.

## EV Charging
- **IEC 61851 / UL 2202**: safety envelope + fault handling
  - Evidence: policy rules, recovery commands, audit logs, evidence packs.
- **UL 2231**: personnel protection
  - Evidence: fault detection in telemetry + alerting routes.

## Microgrid
- **UL 1741 / IEEE 1547**: interconnection safety
  - Evidence: power/voltage/current telemetry bounds + alerts.

## Security & Audit
- Logging/audit evidence: `audit.jsonl`, `run_meta.json`, evidence packs.
- Secrets rotation: `docs/SECRETS_ROTATION.md`

## Required Proof Artifacts
- Field trial evidence packs
- Audit logs
- Recovery drill reports
