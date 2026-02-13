# What Else Needs to Be Done for Readiness

Single checklist for **WaveOS** and **DevSecOps delivery** to be “ready” (production, commercial, no-physical-media).

---

## DevSecOps pipeline (delivery without disks)

| # | Item | Status / action |
|---|------|------------------|
| 1 | **First run** | Push a tag (e.g. `v0.1.1`) or run “DevSecOps Delivery” manually; confirm all jobs pass and Release (or artifacts) are created. |
| 2 | **Registry (optional)** | To push to a customer registry: set repo secrets `REGISTRY_URL`, `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` (and optional `REGISTRY_IMAGE`). |
| 3 | **S3 (optional)** | To upload zip to S3: set `DELIVERY_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (and optional `AWS_REGION`). |
| 4 | **Site verification** | At least one external site: download zip or pull image, verify with cosign (see INSTALL.md), install; document any env-specific steps. |
| 5 | **Air-gap (if needed)** | Document your approved transfer process for the signed zip (one-way transfer, courier, etc.) and add to [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md) if not already there. |

Pipeline and format are implemented; remaining work is configuration, one successful run, and site-side verification.

---

## Technical / product (for “production” sales)

| # | Gap | Action |
|---|-----|--------|
| 1 | **Hardware-validated telemetry** | Validate schema against at least one real device or partner protocol; note “Validated with &lt;vendor&gt;” in release notes. |
| 2 | **Watchdog / recovery on device** | Wire `recovery.py` to a real device supervisor (or document integration kit); validate reset-reason capture. ([DEPLOYMENT_READINESS_REPORT](DEPLOYMENT_READINESS_REPORT.md): No-Go until done.) |
| 3 | **One real actuator path** | Ship or certify one real actuator adapter, or finalize and publish the [Actuator Integration Kit](ACTUATOR_INTEGRATION_KIT.md) so partners can plug control. |
| 4 | **mTLS / encrypted telemetry** | Implement or document mTLS (and/or “bring your own gateway”) for ingestion/C2. |
| 5 | **Pub/sub and C2** | Still planned; add when multi-node or real-time control is required. |

Encryption at rest, ingestion auth, canary, and offline cache are already implemented.

---

## Compliance and certification

| # | Item | Action |
|---|------|--------|
| 1 | **Compliance mapping** | Formalize [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md) (IEC/UL/ISO, NERC/DoD if needed); get sign-off; publish as customer compliance guide. |
| 2 | **Field drill** | Run one documented incident/rollback drill on real or lab hardware; fill [FIELD_DRILL_REPORT](templates/FIELD_DRILL_REPORT.md) and retain. |
| 3 | **Certification path** | If targeting utilities or DoD, define path to relevant certs (e.g. UL, FedRAMP). |

Compliance report signing and retention metadata are implemented.

---

## Commercial operations

| # | Item | Action |
|---|------|--------|
| 1 | **License server / entitlement** | Optional: add license server or API for feature flags, expiry, seat/device limits (beyond current key pattern + expiry). |
| 2 | **EULA / subscription terms** | Add formal commercial license agreement (usage, liability, indemnification). |
| 3 | **Support SLA** | Define support tiers and SLA (response/resolution); link runbooks and operator guide. |
| 4 | **Packaging** | One clear “WaveOS Enterprise” (or similar) deliverable: versioned image + install guide + release notes. |

Quick start and evaluation path exist ([QUICKSTART_EVALUATION](QUICKSTART_EVALUATION.md)).

---

## Go-to-market (if selling)

| # | Item | Action |
|---|------|--------|
| 1 | **Positioning** | One-pager and deck: what WaveOS is, who it’s for, why now. |
| 2 | **Pricing** | Model (per node/site/subscription) and quote process. |
| 3 | **Sales enablement** | Demo script, FAQ; when to recommend field trial vs production (per [DEPLOYMENT_READINESS_REPORT](DEPLOYMENT_READINESS_REPORT.md)). |

---

## Summary: minimum to be “ready”

- **DevSecOps (no disks):** Run pipeline once, set registry/S3 if needed, verify at one site (and document air-gap process if used).
- **Production (technical):** At least one validated device integration, watchdog/recovery wired (or integration kit), and one real actuator path (or finalized integration kit).
- **Production (compliance):** Formalized compliance mapping + one field drill + retention of drill report.
- **Commercial (legal/support):** EULA and support SLA; optional license server and GTM materials.

Use this list to prioritize by first customer or first deployment; the rest can follow in phases.
