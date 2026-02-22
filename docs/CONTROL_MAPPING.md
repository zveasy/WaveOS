# Control Mapping: Control ID → Code & Evidence (Compliance Phase 1)

This document maps **control identifiers** (SOC2, DoD/NIST, NERC CIP) to **code/operational controls** in WaveOS and to **evidence artifacts** (files, CLI outputs, API). Use it to satisfy auditor requests for “where is the evidence for control X?”

See also [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md) for high-level capability-to-framework mapping.

---

## Control ID → Code / Ops → Evidence

| Control ID | Code / operational control | Evidence artifact / link |
|------------|----------------------------|--------------------------|
| **DoD AC-2** (Account Mgmt) | RBAC roles (operator, viewer, etc.); token-based access | `waveos` with `--role`, `--token`; [ACCESS_CONTROL.md](ACCESS_CONTROL.md); audit log of access |
| **DoD AC-3** (Access Enforcement) | `authorize(principal, permission)` before sensitive ops | `src/waveos/utils/rbac.py`; audit entries for denied access |
| **DoD AU-2** (Audit Events) | Audit log for runs, actions, config changes | `audit_log_path` / `out/audit.jsonl`; `WAVEOS_AUDIT_ENABLED` |
| **DoD AU-9** (Protection of Audit Info) | Hash-chained audit; append-only; retention | `audit_hash_chain`; `audit.jsonl` + `.last_hash`; retention config |
| **DoD IA-2** (Identification) | Ingestion token; mTLS client cert paths | `require_ingestion_token`, `ingestion_token_path`; `*_mtls_*` config |
| **DoD SC-8 / SC-13** (Transmission Confidentiality) | mTLS for actuator and ingestion | `actuator_mtls_*`, `ingestion_mtls_*`; [MTLS_AND_ENCRYPTED_TELEMETRY.md](MTLS_AND_ENCRYPTED_TELEMETRY.md) |
| **DoD SC-28** (Protection at Rest) | Encrypted artifacts (Fernet) | `encrypt_artifacts`, `WAVEOS_ENCRYPTION_KEY`; bundle `--encrypt` |
| **DoD CM-3 / CM-5** (Config Change) | Signed bundles; rollback; config drift detection | `waveos bundle build --sign`, `waveos bundle rollback`; idempotent outputs |
| **DoD IR-4 / IR-6** (Incident Handling) | Recovery hooks; runbooks; incidents in persistence | `recovery_*` config; `waveos runbook list/run`; `waveos last-runs`; incidents table |
| **DoD SI-7** (Software Integrity) | Signed distribution; SBOM in pipeline | [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md); cosign/sbom |
| **NERC CIP-003-3** (Security) | Change management; access control; audit | [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md); RBAC; audit log |
| **NERC CIP-005** (Electronic Security) | mTLS; ingestion auth; network config | mTLS config; `require_ingestion_token`; docs |
| **NERC CIP-007** (Systems Security) | Patches via signed bundles; audit; logging | Bundle install/promote/rollback; audit; log_level / log_spool_path |
| **NERC CIP-008** (Incident Response) | Runbooks; recovery; incident records | [RUNBOOKS.md](RUNBOOKS.md); recovery approval; `get_recent_incidents()` / `last-runs` |
| **SOC2 CC6.1** (Logical Access) | Roles and permissions; audit of access | Same as DoD AC-2/AC-3; compliance report |
| **SOC2 CC7.1** (System Monitoring) | Health checks; readiness; watchdog | `waveos health-check`; health_http_port; watchdog file + monitor script |
| **SOC2 A1.2** (Availability) | Recovery; rollback; runbooks | Recovery config; bundle rollback; runbooks |
| **SOC2 PI1.1** (Processing Integrity) | Signed bundles; evidence packs; drift detection | Bundle sign; evidence pack; idempotent outputs |

---

## Evidence Artifact Quick Reference

| Artifact | Location / how to obtain |
|----------|--------------------------|
| Audit log | Config `audit_log_path` or `out/audit.jsonl`; hash chain: same path + `.last_hash` |
| Compliance report | `waveos compliance-report --framework NERC|SOC2|DoD --out <path>`; optional `--auditor-package` |
| Recent runs & incidents | `waveos last-runs` (requires `persistence_db_path`) |
| Run evidence pack | Per-run output dir: `run_meta.json`, `scores.json`, `actions.json`, etc. |
| Bundle manifest (signed) | `waveos bundle build --dir <dir> --sign` → manifest in bundle dir |
| RBAC / auth config | `--role`, `--token`; token roles from env or config; [ACCESS_CONTROL.md](ACCESS_CONTROL.md) |
| Runbooks | `waveos runbook list`; definitions in `src/waveos/runbooks/registry.py` |
| Change management | [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md); bundle install/promote/rollback |
| Recovery approval | `recovery_approval_path` or `WAVEOS_RECOVERY_APPROVED`; recovery_actions.jsonl |

---

**Status:** Phase 1 control mapping for audit support. Update as new controls or evidence paths are added.
