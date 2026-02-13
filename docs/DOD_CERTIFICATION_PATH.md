# DoD Certification Path

This document outlines a **path to DoD-relevant certifications** for WaveOS. It is guidance for program and compliance teams; actual certification depends on scope, deployment context, and accreditor.

## Relevant Frameworks

| Framework | Scope | Notes |
|-----------|--------|--------|
| **FedRAMP** | Cloud (IaaS/PaaS/SaaS) | If WaveOS or its control plane runs in a federal cloud (AWS GovCloud, Azure Government), the overall system may require FedRAMP Moderate/High. WaveOS as a component would be part of the system boundary and documentation. |
| **NIST 800-53** | Security controls (RMF) | DoD and federal systems use NIST 800-53 (Risk Management Framework). Map WaveOS capabilities to controls (e.g. AC, IA, SC, AU, SI) and document in [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md). |
| **STIG / SRG** | Hardening (DoD) | DoD STIGs and Security Requirements Guides apply to OS, middleware, and applications. For WaveOS: lock down config, TLS, logging, audit, and dependencies; align with applicable STIG for your baseline (e.g. application server, Linux). |
| **FIPS 140-2/3** | Cryptography | Use FIPS-validated crypto modules for TLS and encryption where required. WaveOS uses standard libraries (e.g. OpenSSL, cryptography); ensure the runtime stack is FIPS-capable if the contract mandates it. |
| **Program-specific** | Contract / ATO | Many DoD programs have their own Authority to Operate (ATO) and control sets. Align with the program’s security requirements and document how WaveOS satisfies them. |

## Recommended Steps

1. **Define boundary:** Decide whether WaveOS is a standalone product seeking its own ATO or a component within a larger system (e.g. microgrid controller, vehicle system). This drives scope.
2. **Map controls:** Maintain a control mapping (NIST 800-53, program-specific) to WaveOS features: audit logging, RBAC, signed/encrypted bundles, recovery, ingestion auth, mTLS, etc. See [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md).
3. **Evidence and runbooks:** Use WaveOS audit logs, compliance reports, signed reports, and field drill reports as evidence. Keep runbooks (change management, recovery, secrets rotation) up to date.
4. **Hardening:** Apply STIG/SRG guidance to the host OS and WaveOS config (no default secrets, TLS only, retention, etc.).
5. **Third-party assessment:** Engage an accredited assessor (3PAO for FedRAMP, or program-appointed) when pursuing formal certification or ATO.
6. **Continuous monitoring:** Plan for ongoing monitoring and re-authorization (e.g. annual review, change management, incident response).

## WaveOS Capabilities That Support Certification

- **Audit and accountability (AU):** Audit log, retention, compliance report signing.
- **Access control (AC):** RBAC, clearance-based bundle deploy, ingestion token.
- **Identification and authentication (IA):** Device identity, optional mTLS for ingestion.
- **System and communications protection (SC):** Encrypted artifacts, mTLS config, signed bundles.
- **Configuration management (CM):** Signed updates, rollback, config drift detection.
- **Incident response (IR):** Recovery hooks, field drill template, runbooks.

Use this path to prioritize control implementation and documentation; final certification scope is determined by the acquiring organization and accreditor.
