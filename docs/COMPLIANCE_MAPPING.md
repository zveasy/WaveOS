# Compliance Mapping (Formal Draft)

This document maps WaveOS capabilities to common standards for **DoD, NERC, SOC2, and industrial** use. Obtain sign-off from your compliance or legal team before relying on this as an authoritative compliance guide.

---

## DoD / Federal (NIST 800-53, RMF, STIG)

| Control family | Representative controls | WaveOS evidence / capability |
|----------------|-------------------------|-----------------------------|
| **AC (Access Control)** | AC-2, AC-3, AC-6 | RBAC (operator, viewer, etc.); clearance-based bundle deploy; audit log of access attempts; ingestion token. |
| **AU (Audit & Accountability)** | AU-2, AU-3, AU-6, AU-9 | `audit.jsonl`, configurable retention; compliance report with signing; evidence packs; runbooks. |
| **IA (Identification & Authentication)** | IA-2, IA-5 | Device identity; optional mTLS client cert paths; ingestion token; secrets from env/vault. |
| **SC (System & Communications Protection)** | SC-8, SC-13, SC-28 | Encrypted artifacts (Fernet); mTLS config for ingestion; signed bundles (HMAC/cosign); TLS for proxies. |
| **CM (Configuration Management)** | CM-3, CM-5, CM-11 | Signed updates; rollback; config drift detection; idempotent outputs. |
| **IR (Incident Response)** | IR-4, IR-6 | Recovery hooks; watchdog; operator approval for recovery; field drill template; runbooks. |
| **SI (System Integrity)** | SI-3, SI-7 | Signed software distribution; SBOM in DevSecOps pipeline; optional secure boot / IDS flags in config. |

**STIG / SRG:** Harden the host OS and WaveOS configuration per applicable STIG (e.g. application server, Linux). Use TLS-only, no default secrets, and documented retention. See [DOD_CERTIFICATION_PATH.md](DOD_CERTIFICATION_PATH.md).

---

## NERC CIP (Critical Infrastructure Protection)

| Topic | WaveOS evidence |
|-------|------------------|
| **CIP-003 (Security)** | Change management ([CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md)); access control; audit. |
| **CIP-005 (Electronic Security)** | Optional mTLS and encrypted telemetry; ingestion auth; network segmentation via config. |
| **CIP-007 (Systems Security)** | Patch/update via signed bundles; audit; logging; recovery and field drill. |
| **CIP-008 (Incident Response)** | Incident response runbooks; recovery; field drill report template. |

Policy templates (e.g. NERC-oriented) can be loaded from `policy_templates_path`; sample in `docs/templates/policy/nerc.json`.

---

## SOC 2 (Trust Services)

| Criteria | WaveOS evidence |
|----------|------------------|
| **Security** | RBAC, audit log, signed updates, encrypted artifacts, mTLS config, ingestion auth. |
| **Availability** | Recovery, watchdog, rollback, runbooks. |
| **Confidentiality** | Encryption at rest (artifacts), mTLS, access control. |
| **Processing integrity** | Signed bundles, config drift detection, evidence packs. |

Compliance report (framework=DoD/NERC/SOC2) with optional signing and retention supports auditor review.

---

## Industrial (EV Charging, Microgrid)

### EV Charging
- **IEC 61851 / UL 2202:** Safety envelope and fault handling — policy rules, recovery commands, audit logs, evidence packs.
- **UL 2231:** Personnel protection — fault detection in telemetry and alerting routes.

### Microgrid
- **UL 1741 / IEEE 1547:** Interconnection safety — power/voltage/current telemetry bounds and alerts.

### Security & Audit (all)
- Logging/audit: `audit.jsonl`, `run_meta.json`, evidence packs.
- Secrets rotation: [SECRETS_ROTATION.md](SECRETS_ROTATION.md).

---

## Required Proof Artifacts (Summary)

- Field trial evidence packs (run outputs, reports).
- Audit logs with retention.
- Compliance reports (signed, with retention_days).
- Recovery / incident drill reports ([FIELD_DRILL_REPORT](templates/FIELD_DRILL_REPORT.md)).
- Runbooks and change management documentation.

---

**Status:** Draft for compliance review. Formalize and obtain sign-off for your deployment region and contract.
