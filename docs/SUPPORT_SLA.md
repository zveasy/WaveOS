# WaveOS Support SLA (Template)

Use this template to define support tiers and SLA for WaveOS when providing it to the DoD or commercial customers. Customize tiers, response/resolution times, and escalation paths to match your offering.

---

## Support Tiers

| Tier | Scope | Response (business hours) | Resolution target | Escalation |
|------|--------|----------------------------|--------------------|------------|
| **Standard** | Email support; documentation and runbooks | 2 business days | Best effort | — |
| **Enterprise** | Standard + designated contact; config and deployment guidance | 1 business day | 5 business days for P2 | To engineering |
| **DoD / Mission-critical** | Enterprise + prioritized handling; incident bridge available | 4 hours (P1), 8 hours (P2) | Per severity below | To senior engineering and program |

*Business hours:* Define per contract (e.g. 08:00–18:00 ET, Mon–Fri, excluding federal holidays).

---

## Severity Definitions

- **P1 (Critical):** Production down or unsafe; no workaround. Example: control plane unreachable, safety-related failure.
- **P2 (High):** Major feature impaired; workaround exists but operationally costly. Example: report generation failing, actuator path broken.
- **P3 (Medium):** Minor feature or documentation issue; workaround available.
- **P4 (Low):** Request for information, enhancement, or cosmetic fix.

---

## Response and Resolution Targets (Example)

| Severity | First response | Resolution target |
|----------|----------------|--------------------|
| P1 | 4 hours | 24 hours (or per contract) |
| P2 | 8 hours | 5 business days |
| P3 | 2 business days | Next release or patch |
| P4 | 5 business days | Backlog |

---

## Escalation Path

1. **L1:** Support team (email, portal) — triage and runbook execution.
2. **L2:** Engineering — code/config analysis, patches, workarounds.
3. **L3:** Senior engineering / program — architecture, DoD-specific or contract issues.

Define contact channels (e.g. support email, ticket system, POC for DoD) and after-hours process if required.

---

## Operator and Runbook References

- [Change Management](CHANGE_MANAGEMENT.md) — release and rollback.
- [Recovery Integration Kit](RECOVERY_INTEGRATION_KIT.md) — watchdog and recovery.
- [DevSecOps Delivery](DEVSECOPS_DELIVERY.md) — updates and air-gap.
- [Secrets Rotation](SECRETS_ROTATION.md) — key and credential handling.

Retain this SLA in contract exhibits and update when tiers or targets change.
