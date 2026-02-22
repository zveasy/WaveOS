# WaveOS: What It Can Do Today & What’s Left for Commercial

One-page status: **current capabilities** and **remaining work** to make the product commercial.

---

## What This Repo Can Do Today

### Control-plane pipeline
- **Simulate** telemetry: `waveos sim --out <dir>` (baseline + run datasets).
- **Baseline** from a directory: `waveos baseline --in <dir>`.
- **Run** pipeline: `waveos run --in <dir> --baseline <dir> --out <dir>` (or **`--in https://...`** for live HTTP telemetry). Normalize → score → policy → health summary, events, actions, run_meta, evidence pack, HTML report.
- **Config:** TOML/JSON + `WAVEOS_*` env (policy rules, alerts, audit, feature flags, ingestion, mTLS paths).
- **Idempotent outputs** and config drift detection.

### Telemetry ingestion
- **File:** JSON/JSONL/CSV from a directory (with circuit breaker and retry).
- **HTTP pull:** `--in http(s)://url` or `load_records_from_url()`; gateway/adapter can expose telemetry as JSON or JSONL.
- **Ingestion auth:** Optional token check (`require_ingestion_token`, `ingestion_token_path`).
- **Schema:** Normalized model (links, power, voltage, current, temperature, charger status, etc.) per [TELEMETRY_SCHEMA.md](TELEMETRY_SCHEMA.md).

### Actuation and enforcement
- **Real actuator:** When `enforce_actions=true`, **SdnThermalActuator** writes `reroute_requests.jsonl`, `thermal_requests.jsonl`, `rate_limit_requests.jsonl`, `qos_requests.jsonl` to an output dir; optional POST to `WAVEOS_ACTUATOR_SDN_URL` and `WAVEOS_ACTUATOR_THERMAL_CMD` per action.
- **Custom actuator:** Config `actuator_class` (e.g. `"module:ClassName"`) to use your own RealActuator.
- **Actuator listener:** `scripts/actuator_listener.py` tails those JSONL files and POSTs or runs a command so your SDN/thermal controller receives requests in real time.
- **Enforced actions log:** `enforced_actions.jsonl` at output root for audit.

### Recovery and resilience
- **Recovery:** ERROR/WARN → `recovery_actions.jsonl` and optional restart/degrade/reboot commands, with **operator approval** (`recovery_require_approval`, approval file or `WAVEOS_RECOVERY_APPROVED`).
- **Watchdog:** Writes timestamp to a file each run; **watchdog monitor** script and **systemd examples** in repo (`scripts/waveos-watchdog-monitor.sh`, `docs/systemd/`) so a supervisor can restart WaveOS if the file goes stale.
- **Integration kit:** [RECOVERY_INTEGRATION_KIT.md](RECOVERY_INTEGRATION_KIT.md) for wiring to a real device supervisor and reset-reason.

### Bundles and updates
- **Build:** `waveos bundle build --dir <dir> [--sign] [--encrypt]` (HMAC sign; optional Fernet encrypt artifacts).
- **Install:** `waveos bundle install --dir <dir>` or `--from-cache <cache> --bundle-id <id>`; decrypts if `encrypted_artifacts` and `WAVEOS_ENCRYPTION_KEY` set.
- **Canary:** `--canary-percent`, `--canary-dir`, `waveos bundle promote`.
- **Rollback:** `waveos bundle rollback`.
- **Fleet deploy:** `scripts/fleet_deploy.py` to push a bundle to multiple hosts via SSH (from `--hosts` or `--nodes-file`).

### Security and compliance (software side)
- **Encryption at rest:** `encrypt_artifacts` + `WAVEOS_ENCRYPTION_KEY` for run/evidence artifacts.
- **mTLS config:** `ingestion_mtls_cert_path`, `ingestion_mtls_key_path`, `ingestion_mtls_ca_path`, `ingestion_url`; doc [MTLS_AND_ENCRYPTED_TELEMETRY.md](MTLS_AND_ENCRYPTED_TELEMETRY.md) (“bring your own gateway”).
- **Compliance reports:** `waveos compliance-report --framework DoD|NERC|SOC2 --out <path> [--auditor-package <zip>] [--sign-key ...] [--retention-days N]`; optional sign key from config (`compliance_report_sign_key`).
- **Auditor package:** Zip with report, manifest (chain of custody), optional audit excerpt.
- **Compliance mapping:** [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md) (DoD/NIST, NERC, SOC2, industrial); [CONTROL_MAPPING.md](CONTROL_MAPPING.md) (control ID → code/evidence links); [DOD_CERTIFICATION_PATH.md](DOD_CERTIFICATION_PATH.md).
- **RBAC and audit:** Roles, permissions, audit log, retention.

### Licensing and delivery
- **License:** Key format and expiry (suffix `YYYYMMDD`); tiers (e.g. evaluation, standard, enterprise, dod) from key; `WAVEOS_LICENSE_SKIP` for dev.
- **DevSecOps pipeline:** Build, sign (cosign), push image (GHCR + optional registry), distribution zip, GitHub Release, optional S3; [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md) and air-gap/DoD distribution notes.
- **Run locally:** [RUN_ON_YOUR_COMPUTER.md](RUN_ON_YOUR_COMPUTER.md), [QUICKSTART_EVALUATION.md](QUICKSTART_EVALUATION.md).

### Docs and scripts
- **Integration kits:** Actuator, Recovery, Hardware (protocols, ports, testbed, supervisor, fleet).
- **Hardware shopping list:** [HARDWARE_SHOPPING_LIST.md](HARDWARE_SHOPPING_LIST.md) (tiers ~$2k / ~$10k / ~$50k).
- **Legal/support templates:** [EULA_TEMPLATE.md](EULA_TEMPLATE.md), [SUPPORT_SLA.md](SUPPORT_SLA.md) (for legal review).

---

## What’s Left for the Product to Be Commercial

### 1. Technical / product (must-have for “production” sales)

| # | Gap | What to do |
|---|-----|------------|
| 1 | **Hardware-validated telemetry** | Validate schema against at least one real device or partner (charger, inverter, meter); document “Validated with &lt;vendor&gt;” and any limits. |
| 2 | **Watchdog/recovery on device** | Wire recovery + watchdog to a **real** device supervisor on target hardware; validate reset-reason capture. Deployment Readiness: No-Go until done (or integration kit proven at one site). |
| 3 | **One proven actuator path** | Prove one path where WaveOS actions **change physical behavior** (e.g. SDN switch reroute, relay/load, or one vendor API) on real or testbed hardware; document or certify it. |
| 4 | **Real telemetry adapters (optional but strong)** | Build at least one protocol adapter (e.g. Modbus TCP, OCPP) that outputs normalized schema so customers can connect real devices without building it themselves. HTTP pull is already there. |
| 5 | **Pub/sub and C2 (if needed)** | Add when you need multi-node or real-time control; not required for single-site/minimal commercial. |

### 2. Compliance and certification

| # | Item | What to do |
|---|------|------------|
| 1 | **Compliance mapping sign-off** | Formalize [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md) with legal/compliance; publish as customer-facing compliance guide. |
| 2 | **Field drill** | Run one documented incident/rollback drill on real or lab hardware; complete [FIELD_DRILL_REPORT](templates/FIELD_DRILL_REPORT.md) and retain. |
| 3 | **Certification path** | If selling to utilities or DoD, define and document path to relevant certs (e.g. UL, FedRAMP) per [DOD_CERTIFICATION_PATH.md](DOD_CERTIFICATION_PATH.md). |

### 3. Commercial operations

| # | Item | What to do |
|---|------|------------|
| 1 | **EULA / commercial terms** | Turn [EULA_TEMPLATE.md](EULA_TEMPLATE.md) into a signed commercial license (usage, liability, indemnification); legal review. |
| 2 | **Support SLA** | Finalize [SUPPORT_SLA.md](SUPPORT_SLA.md) (tiers, response/resolution); link runbooks and operator docs. |
| 3 | **Packaging** | One clear deliverable (e.g. “WaveOS Enterprise” or “WaveOS for Microgrid”): versioned image/installer, default config, install guide, release notes. |
| 4 | **License server (optional)** | For strict entitlement: license server or API for feature flags, expiry, seat/device limits (beyond current key + expiry). |
| 5 | **Data handling (if applicable)** | If you process customer/DoD data, define data handling, DPA, and flow-downs. |

### 4. Go-to-market (when selling)

| # | Item | What to do |
|---|------|------------|
| 1 | **Positioning** | One-pager and deck: what WaveOS is, who it’s for, why now. |
| 2 | **Pricing** | Model (per node/site/subscription) and quote process. |
| 3 | **Sales enablement** | Demo script, FAQ; when to recommend field trial vs production (see [DEPLOYMENT_READINESS_REPORT.md](DEPLOYMENT_READINESS_REPORT.md)). |

### 5. Operational (prove it works)

| # | Item | What to do |
|---|------|------------|
| 1 | **DevSecOps run** | Run the delivery pipeline once (tag or manual); confirm release/artifacts; optionally set registry/S3. |
| 2 | **Site verification** | At least one external site: download/pull, verify with cosign, install, run; document any env-specific steps. |
| 3 | **Physical testbed (recommended)** | Use [HARDWARE_SHOPPING_LIST.md](HARDWARE_SHOPPING_LIST.md) to build a minimal closed loop (sense → decide → enforce → verify) so you can demo and sell with confidence. |

---

## Summary

- **Today:** WaveOS is a **production-ready software control-plane**: pipeline, HTTP + file telemetry, real actuator (JSONL + optional POST/cmd), recovery with approval, watchdog + monitor + systemd examples, encrypted bundles, compliance reports and auditor package, mTLS config, fleet deploy script, and DoD-oriented docs and templates.
- **To be commercial:** (1) **Prove it on hardware** — one validated telemetry source, one proven actuator path, supervisor wired (or integration kit proven); (2) **Compliance** — formal mapping sign-off + one field drill (+ cert path if needed); (3) **Commercial ops** — EULA, support SLA, one clear package; (4) **Operational** — run DevSecOps once, verify at one site, and (recommended) a small physical testbed for demos.

Use [READINESS_REMAINING.md](READINESS_REMAINING.md), [COMMERCIALIZATION_ROADMAP.md](COMMERCIALIZATION_ROADMAP.md), and [HARDWARE_INTEGRATION_KIT.md](HARDWARE_INTEGRATION_KIT.md) for detailed checklists and next steps.
