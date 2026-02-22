# WaveOS: Detailed Capability and Implementation Guide

This document provides an **in-depth** view of what the WaveOS repo does, how it works, and how it is implemented. Use it for onboarding, architecture review, or integration planning.

---

## 1. What WaveOS Is

**WaveOS** is a **vendor-neutral software control plane** for optical, energy-aware, and embedded networks. It sits above infrastructure (switches, chargers, inverters, microgrids) and provides:

- **Ingestion** of telemetry (file, HTTP, optional protocols)
- **Normalization** into a single canonical schema
- **Health and drift scoring** (baseline vs run, PASS/WARN/FAIL)
- **Policy reasoning** that produces recommended actions (reroute, rate-limit, QoS, thermal)
- **Actuation** (advisory by default; optional real actuator that writes JSONL or calls external APIs)
- **Recovery and watchdog** hooks for self-healing and supervisor integration
- **Secure software distribution**: signed/encrypted bundles, install, rollback, canary, air-gap
- **Compliance and audit**: RBAC, audit logs, compliance reports (NERC, SOC2, DoD), evidence packs

**Identity (production vision):** A DoD/industrial-grade **control-plane OS** for embedded and industrial systems—not a dashboard or monitoring tool, but the layer that **reasons**, **orchestrates**, and (when enabled) **controls** infrastructure.

**Tech stack:** Python 3.11+, Pydantic for models and validation, Rich for CLI, Jinja2 for HTML reports, optional Prometheus/OpenTelemetry for observability. Package: `waveos` (CLI entrypoint `waveos` in `pyproject.toml`).

---

## 2. High-Level Architecture and Data Flow

```
Telemetry sources (files, HTTP URL)
         ↓
Collectors (file: JSON/JSONL/CSV; HTTP: JSON array or JSONL)
         ↓
Normalization (raw → TelemetrySample; schema versioning, migration)
         ↓
Stats aggregation (per link/entity: baseline.json from baseline run; run stats from current run)
         ↓
Health & drift scoring (baseline vs run → HealthScore: score 0–100, PASS/WARN/FAIL, drivers)
         ↓
Policy engine (scores + feature flags + policy_rules → ActionRecommendation list)
         ↓
Actuator (MockActuator logs only; or RealActuator writes JSONL / POST / subprocess)
         ↓
Recovery (optional: ERROR/WARN events → recovery_actions.jsonl, optional restart/degrade/reboot)
         ↓
Reporting (health_summary.json, events.jsonl, actions.json, run_meta.json, report.html, evidence pack)
         ↓
Alerting (optional: webhook / Slack / email on WARN/ERROR)
```

**Design principles:** Vendor neutrality, modular components, explainable decisions, local-first execution, simulation before actuation.

---

## 3. Core Pipeline: How a Run Works

### 3.1 Commands That Drive the Pipeline

| Command | Purpose |
|--------|--------|
| `waveos sim --out <dir>` | Generate synthetic baseline + run telemetry (with optional fault/drift) into `<dir>/baseline` and `<dir>/run`. |
| `waveos baseline --in <dir>` | Read telemetry from `<dir>`, normalize, aggregate per link, write `baseline.json` (and optional config_fingerprint, normalized.jsonl) into `<dir>`. |
| `waveos run --in <dir> --baseline <dir> --out <dir>` | Load run telemetry (from `<dir>` or from `--in https://...`), normalize, build run stats, load baseline from `<dir>/baseline.json`, score links, run policy, (optionally) apply actuator and recovery, write all artifacts to `--out`. |
| `waveos report --in <dir> [--open]` | Re-render HTML report from existing `health_summary.json`, `events.jsonl`, `actions.json` in `<dir>`; optionally open in browser. |

### 3.2 Implementation Flow of `waveos run`

1. **Input resolution:** If `--in` is an HTTP(S) URL, `load_records_from_url()` fetches (chunked, max size 50 MB). Otherwise `_load_samples()` discovers `telemetry.*` or `*.jsonl`/`*.json` in the input dir and loads via file collector (with circuit breaker and retry).
2. **Ingestion auth (optional):** If `require_ingestion_token` is set, `verify_ingestion_token()` is called (token from file or env).
3. **Normalization:** `normalize_records(records, run_id=..., max_records=config.max_telemetry_records)` turns each raw record into a `TelemetrySample` (Pydantic). Schema version 0 is migrated to 1 (e.g. `power_w`→`power_kw`). Invalid records increment `normalize_errors` and are skipped.
4. **Stats:** `build_stats(samples)` aggregates metrics per `link_id` (errors, drops, temperature, power, current, voltage, SOC, charger faults, etc.) and returns baseline-shaped and run-shaped stats. For **run**, baseline is loaded from `baseline_dir/baseline.json` and keyed by entity_id; run stats are keyed the same.
5. **Scoring:** `score_links(baseline_map, run_map, run_id=...)` compares each run entity to its baseline: temperature drift (≥5°C warn, ≥10°C fail), charger faults, overcurrent (≥1.5× baseline), and generic metric spikes (≥1.5× or ≥3×). Severity is summed; score = max(0, 100 − severity). Status: PASS (≥85), WARN (≥60), FAIL (&lt;60). Output: list of `HealthScore` with drivers (e.g. `temperature_drift`, `overcurrent`).
6. **Policy:** `recommend_actions(scores, feature_flags, policy_rules)` produces `ActionRecommendation` list: on FAIL → REROUTE + RATE_LIMIT; on WARN → QOS_PRIORITIZATION; if temperature drivers → POWER_THERMAL_CONSTRAINT. Configurable `policy_rules` (metric, operator, threshold, action) extend this.
7. **Events:** `_build_events(scores)` and `_build_action_events(actions)` create `Event` objects (INFO/WARN/ERROR) for reporting and recovery.
8. **Actuator:** If `enforce_actions` is true, a real actuator (e.g. `SdnThermalActuator`) is instantiated; `apply_safe(actions)` validates each action then writes to `actuator/reroute_requests.jsonl`, `thermal_requests.jsonl`, etc., and optionally POSTs to `WAVEOS_ACTUATOR_SDN_URL` or runs `WAVEOS_ACTUATOR_THERMAL_CMD`. Otherwise `MockActuator().apply(actions)` only logs.
9. **Recovery:** If `recovery_enabled`, `RecoveryOrchestrator` handles events: ERROR → restart_command, WARN → degrade_command (with optional approval file or `WAVEOS_RECOVERY_APPROVED`). Commands are run via `shlex.split` + `subprocess.run(..., shell=False)` (no shell injection).
10. **Watchdog:** If `watchdog_enabled`, `watchdog_ping(config.watchdog_path)` writes current timestamp to a file for an external monitor (e.g. `scripts/waveos-watchdog-monitor.sh`) to detect stale runs and restart the service.
11. **Outputs:** `write_outputs()` writes `health_summary.json`, `events.jsonl`, `actions.json`, `explainability.json`, `run_meta.json`, `metrics.csv`, and renders `report.html` (Jinja2). Optional encryption at rest for run_meta; optional evidence pack zip.
12. **Alerting:** If alert routes are configured, WARN/ERROR events are sent to webhook, Slack, or email (with SSRF checks: HTTPS only, no private IPs).
13. **Idempotency:** If `idempotent_outputs` is true and output dir already contains a report, outputs are written to `out_dir / run_id` to avoid overwriting.

---

## 4. Key Modules and Implementation Details

### 4.1 Models (`src/waveos/models/core.py`)

- **TelemetrySample:** Canonical telemetry record: timestamp, link_id, port_id, errors/drops/retries, FEC, BER, tx/rx power, temperature, congestion, power_kw, energy_kwh, voltage_v, current_a, battery_soc_pct, charger_status, charger_fault_code, meta. All numeric fields have Pydantic bounds (e.g. temperature -50–150°C).
- **HealthScore:** entity_type, entity_id, score (0–100), status (PASS/WARN/FAIL), drivers list, details dict, window_start/end.
- **Event:** timestamp, level (INFO/WARN/ERROR), message, entity_type/entity_id, details.
- **ActionRecommendation:** action (REROUTE, RATE_LIMIT, QOS_PRIORITIZATION, POWER_THERMAL_CONSTRAINT), entity_type, entity_id, rationale, parameters.
- **BaselineStats / RunStats:** entity_type, entity_id, metrics dict, window_start/end (used for baseline.json and run aggregation).

### 4.2 Collectors

- **File (`collectors/file.py`):** Loads JSON (array or `{"records": [...]}`), JSONL, or CSV from path. Uses `CircuitBreaker` (max_failures, reset_after) and `retry()`. Supports multiple files per run (e.g. `telemetry.jsonl`, `*.json`).
- **HTTP (`collectors/http.py`):** `load_records_from_url(url, timeout, headers, max_response_bytes)`. Reads response in 64 KB chunks; caps total size (default 50 MB). Parses JSON array, `{"records": [...]}`, or newline-delimited JSON.
- **Auth (`collectors/auth.py`):** Optional ingestion token: `verify_ingestion_token(token_path, expected_env)`; raises `IngestionAuthError` if required and missing/invalid.

### 4.3 Normalization (`normalize/pipeline.py`)

- **normalize_record(record):** Maps raw dict to `TelemetrySample`; supports schema_version 0→1 migration (temp_c→temperature_c, power_w→power_kw, etc.); fills timestamp from `timestamp` or `ts` or now.
- **normalize_records(records, run_id, max_records):** Bulk normalize; optional cap via `max_records` (config: `WAVEOS_MAX_TELEMETRY_RECORDS`). Increments `telemetry_ingested` / `normalize_errors` counters and records span attributes for tracing.

### 4.4 Scoring (`scoring/health.py`)

- **_aggregate(samples):** Groups by link_id; sums/counts metrics and averages per link (errors, drops, temperature, power, current, voltage, SOC, charger_faults, etc.).
- **build_stats(samples):** Returns (baseline_list, run_list) of BaselineStats/RunStats with same structure (for run, baseline is loaded separately from file).
- **score_links(baseline_map, run_map, run_id):** For each run entity, compares to baseline; applies rules for temperature_drift, charger_fault, overcurrent, and generic ratio spikes; computes score and status; returns list of HealthScore.

### 4.5 Policy (`policy/engine.py`)

- **recommend_actions(scores, run_id, feature_flags, policy_rules):** Maps FAIL → REROUTE + RATE_LIMIT; WARN → QOS_PRIORITIZATION; temperature drivers → POWER_THERMAL_CONSTRAINT. Feature flags gate each action type. `_apply_policy_rules()` evaluates configurable rules (metric, operator, threshold) and appends extra actions.
- **Gates (`policy/gates.py`):** `check_health_gate`, `check_soc_limit`, `check_temp_limit`; `run_gates()` for deployment gates (e.g. no FAIL, or no WARN).

### 4.6 Actuators

- **Base (`actuators/base.py`):** `RealActuator` abstract base: `validate(action)`, `apply(actions)`, `apply_safe(actions)` (filters by validate then apply). `MockActuator` only logs; `NoopActuator` no-ops.
- **SdnThermal (`actuators/sdn_thermal.py`):** Real actuator: writes one JSONL per action type (reroute, thermal, rate_limit, qos) under output_dir; optionally POSTs to `WAVEOS_ACTUATOR_SDN_URL` or runs `WAVEOS_ACTUATOR_THERMAL_CMD` (single executable, no shell). Config can override with `actuator_class` (e.g. `"mymodule:MyActuator"`).

### 4.7 Recovery (`recovery.py`)

- **RecoveryOrchestrator:** Built from config (restart_command, degrade_command, reboot_command, require_approval, approval_path, env_approved). `handle_events(events, out_dir)` writes `recovery_actions.jsonl` and, if approved, runs commands via `shlex.split` + subprocess (no shell).
- **watchdog_ping(path):** Writes current ISO timestamp to file for external monitor.

### 4.8 Bundle and Update Agent

- **Bundle (`bundle.py`):** `build_manifest()` builds `BundleMetadata` (artifacts with path, sha256, size); `write_manifest()`, `sign_manifest(hmac_key)`, `verify_manifest()`. Optional `encrypt_bundle_artifacts` / `decrypt_bundle_artifacts` (Fernet) for DoD.
- **Update agent (`update_agent.py`):** `install_bundle(bundle_dir, active_dir, history_dir, state_dir, hmac_key, canary_percent, canary_dir, decryption_key)` copies bundle to active or canary; verifies manifest; decrypts if needed. Target dir must resolve under `active_dir.resolve().parent`. `install_bundle_from_cache()` for air-gap. `promote_canary_bundle()`, `rollback_bundle()`. State persisted in `state_dir/state.json`.

### 4.9 Licensing (`licensing.py`)

- **require_license():** Enforced at CLI startup unless `WAVEOS_LICENSE_SKIP=1`. Key from `WAVEOS_LICENSE_KEY` or `WAVEOS_LICENSE_PATH` file. Pattern: `WAVEOS-<ID>-<suffix>`; suffix can be YYYYMMDD (expiry). Raises `LicenseError` if missing, invalid, or expired.
- **get_license_tier():** Returns standard, enterprise, dod, or evaluation from key prefix (e.g. WAVEOS-ENTERPRISE-*).

### 4.10 Configuration (`utils/config.py`)

- **WaveOSConfig:** Pydantic model with 80+ fields: log_format, log_level, metrics_port, otel_endpoint, alert URLs, SMTP/SES, bundle paths, recovery/watchdog, actuator, feature_flags, auth_tokens, secrets_provider, audit, retry/breaker, max_memory_mb, max_cpu_seconds, max_telemetry_records, encrypt_artifacts, ingestion token/mTLS, etc.
- **load_config(path):** Loads TOML/JSON from path or `WAVEOS_CONFIG`; overlays env (WAVEOS_*); type-coerces ints, bools; returns validated WaveOSConfig. Config file size capped at 1 MB.

### 4.11 Security and Auth

- **RBAC (`utils/rbac.py`):** Roles (admin, operator, viewer), permissions (run_pipeline, view_reports, deploy_bundle, etc.). V3: clearance, DEPLOY_BUNDLE, MANAGE_NODES.
- **Auth (`utils/auth.py`):** `TokenAuth(token_to_role)`. Tokens from `WAVEOS_AUTH_TOKENS` (token1=admin,token2=operator) or config `auth_tokens`. CLI `--token` for automation.
- **Audit (`utils/audit.py`):** `append_audit(path, payload, max_bytes, max_files)` with rotation. Auth decisions and sensitive actions logged.
- **Secrets (`utils/secrets.py`):** `get_secret(key, provider)` with provider env, vault, aws, gcp. In production (no LICENSE_SKIP), no fallback to WAVEOS_*_SECRETS_JSON.

### 4.12 Observability

- **Logging (`utils/logging.py`):** JSON or text; level and format from config; optional spooler.
- **Metrics (`utils/metrics.py`):** Prometheus counters/histograms (telemetry_ingested, normalize_errors, normalize_duration, scoring_duration); optional HTTP server on WAVEOS_METRICS_PORT.
- **Tracing (`utils/tracing.py`):** OpenTelemetry spans (normalize_records, score_links, policy_recommendations, report_render); run_id on spans when provided.
- **Alerting (`utils/alerting.py`, `alerts.py`):** Routes (webhook, Slack, email); SSRF-safe URL validation (HTTPS only, no private IPs); retry with backoff.

### 4.13 Compliance and Reporting

- **Compliance (`compliance.py`):** `generate_report(framework=NERC|SOC2|DoD, run_meta, audit_path)`; `write_report()` with optional HMAC sign and retention_days; `build_auditor_package()` (zip with report, manifest, audit excerpt).
- **Reporting (`reporting/report.py`):** `write_outputs()` writes health_summary, events, actions, explainability, run_meta (optional encrypted), metrics.csv, and `render_report()` (Jinja2 HTML). Evidence pack zip of all artifacts.

### 4.14 Simulation (`sim/generator.py`)

- **build_demo_dataset(out_dir):** Creates `baseline/` and `run/` with `telemetry.jsonl` and `links.json`. Run data can apply drift (errors, temperature, overcurrent, charger fault) for fault-injection demos.
- **generate_telemetry():** Produces TelemetrySample list and writes JSONL; used by sim and load-test commands.

### 4.15 Extensions (V2/V3)

- **Plugins (`plugins/registry.py`):** `register_plugin()`, `get_plugin_instance()`, `discover_entry_points()` for waveos.plugins (collector, actuator, policy_extension, device_adapter).
- **Device API (`device_api/`):** DeviceDriver registry, stub adapters (charger, inverter, BESS); `list_devices`, capability:vendor keying.
- **Orchestration (`orchestration/nodes.py`):** NodeRole, NodeRecord, node registry from file; `list-nodes` CLI.
- **Scheduler (`scheduler.py`):** EnergyScheduler, ScheduledLoad, DispatchInstruction, Priority; V3 grid/island signals.
- **Compatibility (`compatibility/translator.py`):** RuntimeTranslator, translate_telemetry for multi-RTOS.
- **Heartbeat / node health:** `heartbeat.emit_heartbeat()`, `read_latest_heartbeats()`; `node_health.healthy_nodes()`, `unhealthy_node_ids()` for failover.
- **Shadow mode (`shadow.py`):** `run_shadow()` for what-if (no actuation; diff vs live run_meta).
- **GitOps (`gitops/state.py`):** Load desired state from file for federated deployment.
- **Quotas / SLA:** Tenant quotas, SLA success/failure recording with tenant_id/site_id.

---

## 5. Repo Layout (Summary)

| Area | Path | Purpose |
|------|------|--------|
| Core package | `src/waveos/` | All Python modules |
| CLI | `src/waveos/cli.py` | Argument parsing, command dispatch, main() |
| Models | `src/waveos/models/core.py` | Pydantic entities |
| Pipeline | `normalize/`, `scoring/`, `policy/`, `reporting/` | Normalize → score → policy → report |
| Collectors | `collectors/file.py`, `http.py`, `auth.py` | Telemetry ingestion |
| Actuators | `actuators/base.py`, `sdn_thermal.py` | Mock and real actuator |
| Recovery | `recovery.py` | RecoveryOrchestrator, watchdog_ping |
| Bundle / update | `bundle.py`, `update_agent.py` | Manifest, sign, verify, install, rollback, canary |
| Config / license | `utils/config.py`, `licensing.py` | Load config, license check |
| Security | `utils/auth.py`, `rbac.py`, `audit.py`, `secrets.py` | Tokens, roles, audit, secrets |
| Observability | `utils/logging.py`, `metrics.py`, `tracing.py`, `alerting.py`, `alerts.py` | Logs, Prometheus, OTEL, alerts |
| Compliance | `compliance.py` | NERC/SOC2/DoD reports, auditor package |
| Sim | `sim/generator.py` | Demo data, fault injection |
| Extensions | `plugins/`, `device_api/`, `orchestration/`, `compatibility/`, `scheduler.py`, `heartbeat.py`, `node_health.py`, `shadow.py`, `gitops/`, `quotas.py`, `sla.py` | V2/V3 features |
| Docs | `docs/` | Architecture, PRD, capability matrix, runbooks, deployment, compliance, integration kits |
| Scripts | `scripts/` | Watchdog monitor, actuator listener, fleet deploy |
| Tests | `tests/` | Pytest unit and integration tests |
| CI/CD | `.github/workflows/` | CI (lint, test, coverage, audit, SBOM, cosign), release, devsecops-delivery |

---

## 6. How It Is Deployed and Run

- **Local:** `pip install -e .` then `waveos sim --out demo_data`, `waveos baseline --in demo_data/baseline`, `waveos run --in demo_data/run --baseline demo_data/baseline --out out`. Optional `.env` and `WAVEOS_CONFIG` for config file.
- **Docker:** `docker build -t waveos .`; run with `WAVEOS_LICENSE_KEY` (or LICENSE_SKIP for dev). See `Dockerfile`, `docker-compose.yml`.
- **Kubernetes:** `waveos-k8s.yaml` with Deployment/Job/CronJob; liveness/readiness use `waveos health-check`. Secrets for license and config.
- **Release:** Tag `v*` triggers devsecops-delivery workflow: build, test, sign (cosign), push image to GHCR (and optional registry), create GitHub Release with distribution zip (wheel, SBOM, INSTALL.md). Air-gap: transfer zip, verify signatures, install per docs/INSTALL.md.

---

## 7. Summary

**WaveOS** is a production-oriented **software control plane** for optical and energy-aware infrastructure. It:

1. **Ingests** telemetry from files (JSON/JSONL/CSV) or HTTP URLs, with optional auth and size limits.
2. **Normalizes** into a single Pydantic schema (`TelemetrySample`) with versioning and migration.
3. **Aggregates** metrics per entity and **scores health** by comparing run to baseline (PASS/WARN/FAIL and drivers).
4. **Recommends actions** via a policy engine (reroute, rate-limit, QoS, thermal) and optional configurable rules.
5. **Applies actions** either in mock (log-only) or via a real actuator (JSONL + optional HTTP/subprocess).
6. **Integrates** recovery (restart/degrade/reboot with approval) and watchdog for supervisor integration.
7. **Produces** reports (HTML, JSON, JSONL, run_meta, evidence pack), optional encryption, and compliance reports (NERC, SOC2, DoD).
8. **Supports** secure software distribution (signed/encrypted bundles, install, rollback, canary, air-gap), RBAC, audit, secrets providers, and observability (logs, metrics, tracing, alerts).

The codebase is **modular** (clear separation: collectors → normalize → scoring → policy → actuators → reporting), **config-driven** (TOML/JSON + env), and **extensible** (plugins, device API, custom actuator class). Implementation status for the full 15-area DoD/industrial vision is tracked in **docs/CAPABILITY_MATRIX.md** and **docs/PRD_DOD_REQUIREMENTS.md**; the core pipeline and security/observability features are implemented and tested, with hardware validation and compliance sign-off remaining for full commercial deployment.
