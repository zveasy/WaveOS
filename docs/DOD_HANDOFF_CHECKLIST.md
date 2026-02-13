# DoD Handoff Checklist

What still needs to be implemented or completed before WaveOS can be handed off to the DoD (or DoD-style closed networks). The pipeline you ran (sim → baseline → run → report + real actuator with `enforce_actions`) is in place; below are the remaining gaps for DoD acceptance.

---

## 1. Safety and control (Deployment Readiness: No-Go until done)

| # | Item | Status | Action |
|---|------|--------|--------|
| 1 | **Hardware supervisor integration** | Documented | Wire `recovery.py` to the actual device supervisor per [RECOVERY_INTEGRATION_KIT.md](RECOVERY_INTEGRATION_KIT.md). Validate reset-reason capture on target hardware. |
| 2 | **Operator approval for recovery** | Implemented | `recovery_require_approval` and `recovery_approval_path` (or `WAVEOS_RECOVERY_APPROVED`); explicit process in [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md). |
| 3 | **Fail-safe defaults** | Done | `enforce_actions=false`, `recovery_enabled=false` in default/production configs. |

---

## 2. Security (DoD-grade)

| # | Item | Status | Action |
|---|------|--------|--------|
| 1 | **mTLS / encrypted telemetry** | Documented + config | Implement or document mutual TLS (and encrypted payloads) for ingestion and C2. PRD v2: “Mutual TLS; key management; encrypted telemetry.” |
| 2 | **Zero-trust device identity** | Partial | `DeviceIdentity` and IDS hooks exist; integrate with secure boot and device attestation where required. |
| 3 | **Encrypted bundle delivery** | Implemented | `waveos bundle build --encrypt` and install with `WAVEOS_ENCRYPTION_KEY`; artifact payloads encrypted (Fernet). |
| 4 | **DoD certification path** | Documented | [DOD_CERTIFICATION_PATH.md](DOD_CERTIFICATION_PATH.md) — FedRAMP, NIST 800-53, STIG, program ATO. |

---

## 3. Compliance and audit (DoD, NERC, SOC2-ready)

| # | Item | Status | Action |
|---|------|--------|--------|
| 1 | **Formal compliance mapping** | Formalized | [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md) — DoD (NIST 800-53), NERC CIP, SOC2, industrial; obtain legal/compliance sign-off. |
| 2 | **DoD/NERC/SOC2-ready report packages** | Implemented | Compliance report generator and signing exist; define “auditor-ready” package (retention, format, chain of custody) and optional continuous compliance job. |
| 3 | **Field drill evidence** | Missing | Run at least one **documented** incident/rollback drill on real or lab hardware; complete [FIELD_DRILL_REPORT](templates/FIELD_DRILL_REPORT.md) and retain for audit. |

---

## 4. Delivery and distribution (no physical media)

| # | Item | Status | Action |
|---|------|--------|--------|
| 1 | **DevSecOps delivery pipeline** | Done | Signed builds, SBOM, cosign, distribution zip, optional registry/S3. Run once, verify at a target site. |
| 2 | **Air-gapped transfer process** | Documented | Document approved process (one-way transfer, courier, or classified network) in [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md); have at least one site perform it. |
| 3 | **Clearance-based distribution** | Partial | RBAC with clearance (e.g. DEPLOY_BUNDLE gated by clearance) exists; define “formal DoD distribution compliance” (who can push what, where) and enforce in process or tooling. |

---

## 5. Telemetry and device validation

| # | Item | Status | Action |
|---|------|--------|--------|
| 1 | **Real-device telemetry validation** | Missing | Validate schema and normalization against **at least one real device** (or partner protocol); document “Validated with &lt;vendor&gt;” and any limits. |
| 2 | **Actuator on real systems** | Partial | Real actuator (SDN/thermal request files + optional URL/command) is implemented; **certify or document** one path where those requests are consumed by real SDN/device API. |

---

## 6. Legal and contractual (for DoD handoff)

| # | Item | Status | Action |
|---|------|--------|--------|
| 1 | **Contract / EULA** | Template | [EULA_TEMPLATE.md](EULA_TEMPLATE.md) — customize and have legal review before use. |
| 2 | **Support and SLA** | Template | [SUPPORT_SLA.md](SUPPORT_SLA.md) — tiers, response/resolution, escalation; link runbooks. |
| 3 | **Data handling** | Pending | If DoD data transits your systems, define data handling and any required DPAs/flow-downs. |

---

## Summary: minimum for DoD handoff

- **Safety:** Hardware supervisor integration (or documented integration kit) and operator approval process for recovery.
- **Security:** Path to mTLS/encrypted telemetry and (if required) encrypted bundle delivery; document DoD certification path.
- **Compliance:** Formal compliance mapping (DoD + NERC/ISO as needed) and at least one documented field drill with retained report.
- **Delivery:** DevSecOps pipeline verified; air-gap transfer process documented and exercised.
- **Validation:** At least one real-device telemetry validation and one certified/documentable actuator path (SDN or device API).
- **Legal:** Contract/EULA and support SLA suitable for DoD or prime.

Use this checklist to prioritize; many items are “document and validate” rather than new code. Reference: [PRD_DOD_REQUIREMENTS.md](PRD_DOD_REQUIREMENTS.md), [DEPLOYMENT_READINESS_REPORT.md](DEPLOYMENT_READINESS_REPORT.md), [READINESS_REMAINING.md](READINESS_REMAINING.md).
