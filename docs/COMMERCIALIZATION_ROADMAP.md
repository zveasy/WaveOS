# Commercialization Roadmap

What to add so WaveOS is ready to sell, support, and deploy in production at customer sites. The codebase is already **proprietary** (Omni & Luci, LLC) with license enforcement at startup; this doc focuses on product, safety, legal, and go-to-market gaps.

---

## Implemented (this pass)

- **Canary rollout + offline cache:** `update_agent.install_bundle(..., canary_percent=, canary_dir=)`, `install_bundle_from_cache(cache_dir, bundle_id, ...)`, `promote_canary_bundle()`. CLI: `waveos bundle install --canary-percent 10 --canary-dir ...`, `--from-cache <path> --bundle-id <id>`, `waveos bundle promote`.
- **License expiry and tier:** Keys with suffix `YYYYMMDD` are checked for expiry; `get_license_tier()` returns standard/enterprise/dod/evaluation from key prefix.
- **Encryption at rest:** `waveos.utils.encryption` (Fernet); `write_json_encrypted` / `read_json_encrypted`. Config `encrypt_artifacts=true` + `WAVEOS_ENCRYPTION_KEY` (Fernet key). Optional dep: `pip install waveos[encryption]`.
- **Compliance report signing:** `compliance.write_report(..., sign_key=, retention_days=)`; report includes `signed_at`, `signature` (HMAC-SHA256), `retention_days`.
- **Collector ingestion auth:** Config `require_ingestion_token`, `ingestion_token_path`. `collectors.auth.verify_ingestion_token()`; token from `WAVEOS_INGESTION_TOKEN` or secrets.
- **Actuator integration:** `actuators.RealActuator` base class (`validate`, `apply`, `apply_safe`); [ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md).
- **Quick start and field drill:** [QUICKSTART_EVALUATION.md](QUICKSTART_EVALUATION.md), [templates/FIELD_DRILL_REPORT.md](templates/FIELD_DRILL_REPORT.md).

---

## 1. Technical & product gaps (must-have for “production” sales)

### 1.1 Real device integration and safety

| Gap | Why it matters | Suggested add |
|-----|----------------|---------------|
| **No hardware-validated telemetry** | Customers need proof the schema works with real chargers/inverters/BESS. | Validate telemetry against at least one real device or partner protocol; document “Validated with &lt;vendor&gt;” in release notes. |
| **Watchdog / recovery not wired to device** | Deployment Readiness Report: “No-Go” until safety envelope is enforced by a real supervisor. | Integrate `recovery.py` with at least one device supervisor (e.g. vendor API or local daemon); document reset-reason capture. |
| **Actuator is mock-only** | Pipeline is advisory only; no provable “control” story. | Ship or certify **one** real actuator adapter (e.g. one charger or inverter vendor) or a clearly documented “actuator integration kit” so customers/partners can plug real control. |

### 1.2 Security (still planned in capability matrix)

| Gap | Why it matters | Suggested add |
|-----|----------------|---------------|
| **No mTLS / encrypted telemetry** | Enterprises and DoD will require encrypted ingestion and C2. | Implement or document mTLS for collector/API and encrypted payloads for telemetry (or a clear “bring your own gateway” story). |
| **Encryption at rest** | Threat model lists “Encryption at rest for reports” as open. | Option to encrypt report/evidence artifacts (e.g. with customer-managed keys or envelope encryption). |
| **Auth for collectors** | Threat model: “Authentication/authorization for collectors” open. | Authenticated (and optionally authorized) ingestion so only trusted sources can push telemetry. |

### 1.3 Remaining capability gaps

- **Pub/sub and C2 channels** — Still “Planned”; needed for multi-node and real-time control stories.
- **Staged/canary rollout** — Config exists (`bundle_canary_percent`); implement in `update_agent` so customers can do canary deployments.
- **Offline/air-gapped bundle cache** — Config exists; implement so air-gapped sites can stage and apply updates from a cache.

---

## 2. Compliance and certification (required for regulated / industrial buyers)

| Item | Status | What to add |
|------|--------|-------------|
| **Compliance mapping** | Draft in `COMPLIANCE_MAPPING.md`; Deployment Readiness: “No-Go” (not validated). | Formalize mapping to IEC/UL/ISO (and NERC/DoD if selling there); get legal/compliance sign-off; publish as “Compliance guide” for customers. |
| **Compliance reports** | V3 generates NERC/SOC2/DoD-style reports from run_meta + audit. | Define “auditor-ready” format (e.g. signed report, retention policy); optionally integrate with a continuous compliance job. |
| **Field drills** | Runbooks exist; no evidence from real hardware. | Run at least one documented incident/rollback drill on real or lab hardware; publish a short “Field drill report” template. |
| **Certification** | None referenced. | If targeting utilities or DoD, plan for or document path to relevant certs (e.g. UL, FedRAMP, or customer-specific). |

---

## 3. Commercial operations (so you can sell and support it)

### 3.1 Licensing and packaging

| Item | Current state | What to add |
|------|----------------|-------------|
| **License key** | Pattern check only (`WAVEOS-&lt;id&gt;-&lt;suffix&gt;`); no server validation. | For commercial tiers: optional license server or entitlement API (feature flags, expiry, seat/device limits). |
| **Editions / tiers** | Single codebase. | If you have tiers (e.g. Standard / Enterprise / DoD): document feature matrix and gate features by license or config. |
| **Packaging** | Docker, PyPI (or internal), K8s manifest. | Customer-facing “WaveOS Enterprise” or “WaveOS for Microgrid” package: versioned image, default config, one-command or scripted install; release notes per version. |

### 3.2 Legal and terms

| Item | What to add |
|------|-------------|
| **Commercial license agreement** | Formal EULA or subscription terms (usage, restrictions, liability, indemnification). |
| **Support terms** | SLA definitions (response time, resolution targets) for each support tier. |
| **Privacy policy** | If you collect any usage/telemetry from the product, publish a privacy policy and honor it. |
| **Data processing** | If customers send you data (e.g. support), DPA and subprocessor list if required. |

### 3.3 Support and SLA

| Item | What to add |
|------|-------------|
| **Support tiers** | Define e.g. Community / Standard / Premium (or similar) and what each includes (email, ticket, phone, TAM). |
| **SLA definitions** | Uptime %, response times, exclusions; align with `docs/SLO_SLI.md` where relevant. |
| **Escalation and runbooks** | Link RUNBOOKS and OPERATOR_GUIDE to support; define when to escalate to engineering. |
| **Release support policy** | Already in SECURITY.md (current + previous minor); extend to “commercial support” window (e.g. security fixes for N months). |

### 3.4 Onboarding and success

| Item | What to add |
|------|-------------|
| **Evaluation / trial** | Time-limited or capability-limited trial license; “Quick start for evaluators” (minimal steps to first report). |
| **First-run experience** | Clear message when license is missing or invalid; link to licensing@ or docs. |
| **Documentation for buyers** | Evaluation guide, comparison vs “build yourself,” ROI/use-case one-pagers; reference to PRD and Capability Matrix for technical buyers. |

---

## 4. Go-to-market and positioning

| Item | What to add |
|------|-------------|
| **Positioning and messaging** | One-pager and slide deck: what WaveOS is, who it’s for (microgrid operators, DoD, EV networks), and why now. |
| **Pricing and packaging** | Model (per node, per site, subscription, one-time) and list/quote process. |
| **Sales enablement** | Demo script, FAQ, objection handling; link to DEPLOYMENT_READINESS_REPORT and when to recommend field trial vs production. |
| **Channel / partners** | If selling via OEMs or integrators: partner pack (docs, license provisioning, support handoff). |
| **Website and collateral** | Landing page, docs portal (or clear link to GitHub/docs), SECURITY.md and licensing contact. |

---

## 5. Summary: minimum to be “commercialization ready”

**Technical**

- At least one **validated** device integration or protocol (telemetry + optional actuator).
- **Safety**: Watchdog/recovery integrated with a real supervisor (or documented integration kit).
- **Security**: Path to mTLS/encrypted telemetry and encryption at rest (or documented “customer gateway” approach).
- **Canary/offline**: Implement canary rollout and offline bundle cache so config is usable in the field.

**Compliance**

- **Compliance mapping** signed off and published; **field drill** at least once and documented.
- **Auditor-ready** compliance report workflow (retention, format, optional signing).

**Commercial**

- **License**: Either keep pattern-only keys or add entitlement server/API for tiers and expiry.
- **Legal**: EULA/subscription terms, support SLA, privacy (and DPA if needed).
- **Support**: Defined tiers, SLA, escalation; runbooks and operator guide linked.
- **Packaging**: One clear “commercial” artifact (e.g. Docker image + install guide + release notes).

**GTM**

- **Positioning** (one-pager), **pricing**, **evaluation path** (trial + quick start).
- **Buyer docs**: Evaluation guide, when to use field trial vs production (per Deployment Readiness).

Use this as a checklist; prioritize by first target customer (e.g. microgrid vs DoD) and close the gaps that unblock their procurement and compliance requirements first.
