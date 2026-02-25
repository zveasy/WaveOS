# WaveOS Audit Model

## Overview

WaveOS produces comprehensive audit trails for all deployment and operational activities. This supports compliance requirements (RMF, NIST, NERC, SOC2, DoD).

## Audit Events

### Pipeline Events
- Telemetry ingestion
- Baseline computation
- Health scoring
- Policy recommendations
- Action enforcement

### Deployment Events
- Bundle verification
- Preflight checks
- Installation steps
- Activation
- Health monitoring
- Rollback events

## Evidence Packs

Each deployment produces a device-local evidence pack containing:

```json
{
  "bundle_id": "bundle-abc123",
  "timestamp": "2025-01-15T10:30:00Z",
  "agent_state": "MONITOR",
  "steps": [
    {"step": "verify", "ok": true},
    {"step": "preflight", "ok": true},
    {"step": "install", "ok": true},
    {"step": "activate", "ok": true}
  ],
  "verification_result": {...},
  "preflight_result": {...},
  "health_timeline": [...],
  "rollback_events": [...]
}
```

## Hash Chain Audit Log

WaveOS audit logs support hash-chain integrity for tamper detection. Each entry includes a hash of the previous entry.

## Compliance Reports

```bash
waveos compliance-report --framework DoD --out report.json --auditor-package audit.zip
```

Supported frameworks: NERC, SOC2, DoD.

## CLI Commands

```bash
waveos verify-evidence-attestation <path>
waveos change-log
waveos access-review-export --out review.json
waveos agent-v2 logs
```
