# In-Depth: What Has Been Implemented and What Should Work

This document explains every DoD-ready and production feature that exists in WaveOS: what was implemented, how it works, and what you can expect when you use it.

---

## 1. Run pipeline (sim → baseline → run → report)

**What’s implemented**

- **`waveos sim`** — Generates demo telemetry (baseline and run) under an output directory.
- **`waveos run --in <run> --baseline <baseline> --out <out>`** — Ingests telemetry, normalizes, scores links, runs the policy engine, produces health summary, events, actions, run_meta, evidence pack, and HTML report.
- **Config** — Loaded from TOML/JSON (e.g. `--config`) and environment variables (`WAVEOS_*`). Policy rules, alerting, audit, and feature flags are all config-driven.

**What should work**

- Run with demo data: `waveos sim --out ./demo_data` then `waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out`. You get `out/run_meta.json`, `out/health_summary.json`, `out/events.jsonl`, `out/actions.json`, `out/report.html`, and (if evidence pack enabled) `out/run_meta.json` and related artifacts.
- **Idempotent outputs:** If `out/` already has a prior run (run_meta or report), the next run writes under `out/<run_id>/` so you don’t overwrite.
- **Config drift:** If baseline and run configs differ, a WARNING is logged; the run continues.

---

## 2. Real actuator (SDN + thermal) and enforced actions

**What’s implemented**

- **`SdnThermalActuator`** (`src/waveos/actuators/sdn_thermal.py`): a real actuator that:
  - Accepts action types: **REROUTE**, **POWER_THERMAL_CONSTRAINT**, **RATE_LIMIT**, **QOS_PRIORITIZATION**.
  - Writes one JSON line per action to files under an actuator output directory:
    - `reroute_requests.jsonl`
    - `thermal_requests.jsonl` (only when at least one thermal action exists)
    - `rate_limit_requests.jsonl`
    - `qos_requests.jsonl`
  - Each line is JSON: `timestamp`, `run_id`, `entity_type`, `entity_id`, `action`, `rationale`, `parameters`.
  - **Optional hooks:** If `WAVEOS_ACTUATOR_SDN_URL` is set, each REROUTE is POSTed to that URL. If `WAVEOS_ACTUATOR_THERMAL_CMD` is set, each POWER_THERMAL_CONSTRAINT is passed as JSON on stdin to that command.
- **Pipeline wiring:** When **`enforce_actions=true`** (config or `WAVEOS_ENFORCE_ACTIONS=true`):
  - The run uses `SdnThermalActuator` instead of `MockActuator`.
  - Actuator output dir = `actuator_output_dir` or `WAVEOS_ACTUATOR_OUTPUT_DIR`, else `<run out>/actuator`.
  - **`enforced_actions.jsonl`** is written to the **output root** (e.g. `./out/enforced_actions.jsonl`), not under `run-*/`. It lists every action that was passed to the actuator (after `apply_safe` validation).
- **Safety:** `apply_safe()` runs each action through `validate()`; only actions that pass are applied. The built-in actuator validates that `entity_id` and `entity_type` are present.

**What should work**

- With `WAVEOS_ENFORCE_ACTIONS=true` and `WAVEOS_ACTUATOR_OUTPUT_DIR=./out/actuator-$(date +%Y%m%d-%H%M%S)` (or default), after a run:
  - You see `./out/actuator/` (or your dir) with `reroute_requests.jsonl`, `rate_limit_requests.jsonl`, `qos_requests.jsonl` (and `thermal_requests.jsonl` only if policy recommended thermal actions).
  - You see `./out/enforced_actions.jsonl` with one JSON object per line for every recommended action.
- If you set `WAVEOS_ACTUATOR_SDN_URL=https://your-sdn/api/reroute`, each REROUTE line is also POSTed there (and logged on failure).
- If you set `WAVEOS_ACTUATOR_THERMAL_CMD=/opt/thermal/handle.sh`, each thermal action is passed as JSON to that script’s stdin.

**Docs:** [ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md) — how to plug your SDN or device API and how to implement a custom actuator (e.g. charger) using `RealActuator`.

---

## 3. Recovery and operator approval (DoD)

**What’s implemented**

- **RecoveryOrchestrator** (`src/waveos/recovery.py`):
  - Consumes **events** from the run (ERROR → restart_service, WARN → degrade_features).
  - Always appends **`RecoveryAction`** records to **`recovery_actions.jsonl`** in the run output directory.
  - Optionally runs **commands**:
    - `restart_command` for ERROR
    - `degrade_command` for WARN
    - `reboot_command` (present in API; not auto-triggered by event level in current logic; you can extend or call from a script)
  - **Operator approval:** If `require_approval=True` (default when recovery is used):
    - Commands are **not** executed unless approval is granted.
    - Approval is granted if: (1) `WAVEOS_RECOVERY_APPROVED=true` in the environment for that run, or (2) a file at `recovery_approval_path` exists and its content (trimmed, lowercased) is exactly `approved`.
    - If approval is missing, a WARNING is logged: “Recovery commands not run: operator approval required”.
- **Config:** `recovery_enabled`, `recovery_require_approval` (default True), `recovery_approval_path`, `recovery_restart_command`, `recovery_degrade_command`, `recovery_reboot_command`.
- **Watchdog:** `watchdog_ping(path)` writes the current UTC timestamp to a file. When `watchdog_enabled=true` and `watchdog_path` is set, the run pipeline calls it after each run so an external supervisor can detect a stale timestamp and trigger reset/recovery.

**What should work**

- With `recovery_enabled=true` and commands set: every run that produces ERROR/WARN events writes `recovery_actions.jsonl`. If `recovery_require_approval=true` and you do **not** set `WAVEOS_RECOVERY_APPROVED=true` or create the approval file, no restart/degrade command runs; you still get the log and the JSONL.
- With approval: create a file (e.g. `out/recovery_approved`) containing the single line `approved`, or run with `WAVEOS_RECOVERY_APPROVED=true`; then the configured restart/degrade commands run (e.g. `systemctl restart waveos` or a supervisor script).
- Watchdog: set `watchdog_enabled=true` and `watchdog_path=out/watchdog.txt`; after each run that file is updated. Your device supervisor should monitor that path and treat “no update within N seconds” as unhealthy.

**Docs:** [RECOVERY_INTEGRATION_KIT.md](RECOVERY_INTEGRATION_KIT.md) (hardware supervisor contract, reset-reason, approval process), [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md) (operator sign-off).

---

## 4. Encrypted bundle delivery (DoD)

**What’s implemented**

- **Build:** `waveos bundle build --dir <dir> --sign --encrypt`
  - Builds the manifest from plain artifact files (e.g. policy JSONs), writes `bundle.json`.
  - If `--encrypt`: uses `WAVEOS_ENCRYPTION_KEY` (Fernet key), encrypts each artifact file (except `bundle.json` and `bundle.sig`), writes `<file>.enc` and removes the plain file; then sets `encrypted_artifacts: true` in `bundle.json`.
  - If `--sign`: signs `bundle.json` with the HMAC key (e.g. from config or `WAVEOS_BUNDLE_HMAC_KEY_SECRET`).
- **Install:** `waveos bundle install --dir <dir>` or `--from-cache <cache> --bundle-id <id>`
  - Verifies the manifest signature if HMAC key is configured.
  - If the bundle has `encrypted_artifacts: true` and `WAVEOS_ENCRYPTION_KEY` is set, **decrypts** all `*.enc` files back to plain names (e.g. `policy.json.enc` → `policy.json`) after copying to the target directory.
  - Supports canary install (`--canary-percent`, `--canary-dir`) and `waveos bundle promote` / `waveos bundle rollback`.

**What should work**

- **Encrypted bundle:** Generate a Fernet key (e.g. `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Set `WAVEOS_ENCRYPTION_KEY` and run `waveos bundle build --dir ./my-bundle --sign --encrypt`. The bundle directory will contain `bundle.json`, `bundle.sig`, and `*.enc` files (no plain policy/artifact files). On the target, set the same `WAVEOS_ENCRYPTION_KEY` and run `waveos bundle install --dir ./my-bundle` (or install from cache); artifacts are decrypted in place and used normally.
- **Without encryption:** Build/sign/install as before; no `--encrypt` and no key required.

---

## 5. Compliance reports and auditor package

**What’s implemented**

- **Report generation:** `waveos compliance-report --framework DoD|NERC|SOC2 --out <path> [--audit-path <audit.jsonl>]`
  - Builds a **ComplianceReport** (framework, period, run counts, audit event count, findings) and writes JSON to `--out`.
  - Optional **signing:** `--sign-key <key>` (or key from secrets) adds `signed_at` and `signature` (HMAC-SHA256 of canonical JSON).
  - Optional **retention:** `--retention-days N` (or config `retention_days`) stored in the report for auditors.
- **Auditor package:** `waveos compliance-report ... --auditor-package <zip path>`
  - After writing the report JSON, builds a zip containing:
    - `report.json` (the compliance report)
    - `manifest.json` (package_type, framework, period, generated_at, retention_days, signed_at, list of contents)
    - `audit_excerpt.jsonl` (if `--audit-path` was provided; up to 10,000 lines of the audit log)
  - Gives a single artifact for auditors with chain-of-custody metadata.

**What should work**

- Run: `waveos compliance-report --framework DoD --out out/dod-report.json --audit-path out/audit.jsonl --auditor-package out/dod-auditor.zip --retention-days 2555`.
- You get `out/dod-report.json` and `out/dod-auditor.zip`. Unzipping the latter shows `report.json`, `manifest.json`, and optionally `audit_excerpt.jsonl`.

---

## 6. mTLS and encrypted telemetry (DoD) — configuration and docs

**What’s implemented**

- **Config fields:** `ingestion_mtls_cert_path`, `ingestion_mtls_key_path`, `ingestion_mtls_ca_path`, `ingestion_url` (and env: `WAVEOS_INGESTION_MTLS_CERT_PATH`, etc.). These are **stored and passed** so that any outbound ingestion client (or gateway) can use them. WaveOS does not implement the TLS handshake itself; it provides the configuration for “bring your own gateway” or a future client that uses these paths.
- **Documentation:** [MTLS_AND_ENCRYPTED_TELEMETRY.md](MTLS_AND_ENCRYPTED_TELEMETRY.md) — how to use mTLS for ingestion/C2, key management, and FIPS/STIG notes.

**What should work**

- You can set the env vars or config so that downstream code or your own gateway has the paths to client cert, key, and CA. No built-in collector currently performs outbound mTLS; the wiring is ready for when you add one or use an external gateway that reads these settings.

---

## 7. Encryption at rest (run artifacts)

**What’s implemented**

- **Config:** `encrypt_artifacts=true` (or `WAVEOS_ENCRYPT_ARTIFACTS=true`).
- **Behavior:** When writing run outputs (e.g. `run_meta.json`), if encryption is enabled and `WAVEOS_ENCRYPTION_KEY` is set (Fernet), the code can write an encrypted blob (e.g. `run_meta.json.enc`) instead of plain JSON. The reporting module uses `write_json_encrypted` with a fallback to plain if encryption is unavailable.

**What should work**

- With `encrypt_artifacts=true` and a valid `WAVEOS_ENCRYPTION_KEY`, run artifacts that go through the encryption path are stored encrypted. Read path supports both `.enc` and plain files.

---

## 8. DevSecOps delivery and air-gap

**What’s implemented**

- **Pipeline:** `.github/workflows/devsecops-delivery.yml` — on tag or manual: test, build, sign (cosign), push image (GHCR + optional custom registry), create distribution zip, GitHub Release, optional S3 upload.
- **Documentation:** [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md) — pipeline steps, registry/S3 config, how to receive updates (pull image, download zip, verify with cosign). **Air-gapped transfer process:** steps for build → transfer via approved process → install on the air-gapped side. **DoD distribution compliance:** who can push what, RBAC, pipeline and registry restrictions.

**What should work**

- Pushing a tag (e.g. `v1.0.0`) or running the workflow manually produces signed artifacts and a release. Sites can pull the image or download the zip and verify with cosign. For air-gap, you follow the documented steps (transfer signed zip via approved process, verify and install on the closed network).

---

## 9. Compliance mapping and DoD certification path

**What’s implemented**

- **Compliance mapping:** [COMPLIANCE_MAPPING.md](COMPLIANCE_MAPPING.md) — tables mapping WaveOS capabilities to DoD (NIST 800-53), NERC CIP, SOC2, and industrial (EV/microgrid) standards, with evidence pointers (audit, RBAC, signed bundles, recovery, etc.).
- **DoD certification path:** [DOD_CERTIFICATION_PATH.md](DOD_CERTIFICATION_PATH.md) — FedRAMP, NIST 800-53, STIG, FIPS, program ATO, and recommended steps. No automated certification; guidance only.

**What should work**

- You use these as living docs for control mapping and certification planning; sign-off and actual ATO remain with your compliance team and accreditor.

---

## 10. Legal and support templates

**What’s implemented**

- **EULA template:** [EULA_TEMPLATE.md](EULA_TEMPLATE.md) — placeholder sections (grant, restrictions, compliance, confidentiality, disclaimer, liability, indemnification, term, government rights). Marked for legal review.
- **Support SLA template:** [SUPPORT_SLA.md](SUPPORT_SLA.md) — tiers, severity definitions, response/resolution targets, escalation, links to runbooks.

**What should work**

- You customize and send to legal; once approved, they become your contractual and support documents. No code depends on them.

---

## 11. Other behaviors (audit, RBAC, licensing, config)

**What’s implemented**

- **Audit:** Audit log path and rotation (config); CLI and pipeline log auth and sensitive actions to the audit log.
- **RBAC:** Roles and permissions (e.g. run_pipeline, DEPLOY_BUNDLE); clearance-based gating for bundle deploy.
- **Licensing:** License check on CLI entry; optional expiry and tier (e.g. evaluation, DoD) from key format.
- **Config:** All of the above (recovery, actuator, mTLS, encryption, retention, etc.) are driven by `WaveOSConfig` and env; no hardcoded production secrets.

**What should work**

- With a valid license (or skip for dev), config file and env vars control recovery, actuator, encryption, and compliance options. Audit and RBAC apply where wired in the CLI and run path.

---

## Quick reference: config and env that affect DoD behavior

| Feature | Config / env | Effect |
|--------|----------------|--------|
| Real actuator | `enforce_actions`, `WAVEOS_ENFORCE_ACTIONS` | Use SdnThermalActuator; write `*_requests.jsonl` and `enforced_actions.jsonl`. |
| Actuator output dir | `actuator_output_dir`, `WAVEOS_ACTUATOR_OUTPUT_DIR` | Where `*_requests.jsonl` are written. |
| SDN/thermal hooks | `WAVEOS_ACTUATOR_SDN_URL`, `WAVEOS_ACTUATOR_THERMAL_CMD` | Optional POST / subprocess per action type. |
| Recovery | `recovery_enabled`, `recovery_restart_command`, etc. | Run recovery commands on ERROR/WARN. |
| Recovery approval | `recovery_require_approval`, `recovery_approval_path`, `WAVEOS_RECOVERY_APPROVED` | Gate execution of recovery commands. |
| Watchdog | `watchdog_enabled`, `watchdog_path` | Write timestamp file each run. |
| Encrypted bundles | `WAVEOS_ENCRYPTION_KEY`, `--encrypt` / install | Encrypt artifacts on build; decrypt on install. |
| Encryption at rest | `encrypt_artifacts`, `WAVEOS_ENCRYPTION_KEY` | Encrypt run artifacts (e.g. run_meta). |
| mTLS (ingestion) | `ingestion_mtls_*`, `ingestion_url` | Config for client cert/key/CA and endpoint. |
| Compliance report | `--auditor-package`, `--sign-key`, `--retention-days` | Auditor zip and signing/retention. |

---

## Additional software implementations (live data, actuator consumer, fleet, supervisor)

| Feature | What was added | How to use |
|--------|----------------|------------|
| **HTTP telemetry** | `load_records_from_url()` in `waveos.collectors.http`; run accepts **`--in http(s)://url`** | Point `--in` at a URL that returns JSON array or JSONL; pipeline fetches once and runs. Use for gateways or adapters that expose telemetry over HTTP. |
| **Config-driven actuator** | Config `actuator_class` (and `WAVEOS_ACTUATOR_CLASS`) — `"module:ClassName"` | Set in config; when `enforce_actions=true`, the CLI instantiates your class (with `output_dir`, `run_id`) instead of `SdnThermalActuator`. |
| **Compliance sign key from config** | `compliance_report_sign_key` / `WAVEOS_COMPLIANCE_REPORT_SIGN_KEY`; fallback to bundle HMAC key | Omit `--sign-key` on CLI; report is signed using the configured secret. |
| **Watchdog monitor** | `scripts/waveos-watchdog-monitor.sh` | Run as systemd service or cron; if watchdog file is older than `WAVEOS_WATCHDOG_STALE_SECONDS`, writes reset reason and restarts `WAVEOS_SERVICE_NAME`. |
| **Systemd examples** | `docs/systemd/` — waveos.service, waveos.timer, waveos-watchdog.service, waveos-watchdog.timer | Copy to `/etc/systemd/system/`, set paths and env, enable timers. |
| **Actuator listener** | `scripts/actuator_listener.py` | Daemon: tails `*_requests.jsonl` in `WAVEOS_ACTUATOR_DIR`; POSTs reroute to `WAVEOS_ACTUATOR_SDN_URL`, runs `WAVEOS_ACTUATOR_THERMAL_CMD` with JSON stdin for thermal. |
| **Fleet deploy** | `scripts/fleet_deploy.py` | `--hosts node1,node2` or `--nodes-file out/nodes.json` with `--cache` and `--bundle-id` (or `--bundle-dir`); SSHs to each host and runs `waveos bundle install`. |

---

## From software to physical world (the "body")

To make WaveOS real on-site (microgrid, chargers, DoD embedded), you need the **hardware integration and testbed** described in:

- **[HARDWARE_INTEGRATION_KIT.md](HARDWARE_INTEGRATION_KIT.md)** — Edge node, telemetry collectors (Modbus, OCPP, etc.), real actuator execution (SDN switch, load, relay), microgrid testbed, supervisor, fleet model, edge install and evidence.
- **[HARDWARE_SHOPPING_LIST.md](HARDWARE_SHOPPING_LIST.md)** — Tiered hardware list (~$2k / ~$10k / ~$50k) to prove the closed loop: sense → decide → enforce → verify.

---

**Summary:** On the software side, the run pipeline, real actuator, recovery with operator approval, watchdog, encrypted bundles, compliance reports and auditor package, mTLS config and docs, encryption at rest, DevSecOps and air-gap docs, compliance mapping, DoD certification path, and legal/support templates are all implemented. What “should work” is described above for each area; remaining work is hardware integration (supervisor wiring, reset-reason), operational drills, and legal/compliance sign-off.
