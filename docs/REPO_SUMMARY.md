# WaveOS: Repository Summary

A single-page overview of the WaveOS repo: what it is, what’s implemented, and what it can do.

---

## What WaveOS Is

**WaveOS** is a **vendor-neutral software control plane** for optical, energy-aware, and embedded networks. It sits above infrastructure (switches, chargers, inverters, microgrids) and provides:

- **Ingestion** of telemetry (file, HTTP, optional protocols)
- **Normalization** into a single canonical schema
- **Health and drift scoring** (baseline vs run → PASS/WARN/FAIL)
- **Policy reasoning** that produces recommended actions (reroute, rate-limit, QoS, thermal)
- **Actuation** (advisory by default; optional real actuator writing JSONL or calling external APIs)
- **Recovery and watchdog** for self-healing and supervisor integration
- **Secure software distribution**: signed/encrypted bundles, install, rollback, canary, air-gap
- **Compliance and audit**: RBAC, audit logs, compliance reports (NERC, SOC2, DoD), evidence packs

**Identity:** A DoD/industrial-grade **control-plane OS** for embedded and industrial systems—the layer that **reasons**, **orchestrates**, and (when enabled) **controls** infrastructure.

**Tech stack:** Python 3.11+, Pydantic, Rich CLI, Jinja2 reports, optional Prometheus/OpenTelemetry. Package: `waveos`; CLI: `waveos` (see `pyproject.toml`).

---

## What’s Implemented (High Level)

| Area | Status | Notes |
|------|--------|--------|
| **Core pipeline** | ✅ | Sim → baseline → run → report; normalize → score → policy → actuator → recovery → outputs |
| **Telemetry ingestion** | ✅ | File (JSON/JSONL/CSV), HTTP pull; optional ingestion token; circuit breaker + retry |
| **Normalization** | ✅ | Raw → `TelemetrySample`; schema versioning and migration (v0→v1) |
| **Health & drift scoring** | ✅ | Baseline vs run; temperature, overcurrent, charger faults, generic spikes; PASS/WARN/FAIL + drivers |
| **Policy engine** | ✅ | FAIL→REROUTE+RATE_LIMIT; WARN→QOS; thermal→POWER_THERMAL_CONSTRAINT; configurable rules |
| **Actuators** | ✅ | Mock (log-only); real `SdnThermalActuator` (JSONL + optional POST/cmd); custom via `actuator_class` |
| **Recovery** | ✅ | ERROR/WARN → recovery_actions.jsonl; restart/degrade/reboot with approval; no shell injection |
| **Watchdog** | ✅ | Ping file + monitor script + systemd examples |
| **Bundles & updates** | ✅ | Build, sign (HMAC), optional encrypt; install, canary, rollback; fleet deploy script |
| **Licensing** | ✅ | Key format + expiry; tiers (evaluation, standard, enterprise, dod); `WAVEOS_LICENSE_SKIP` for dev |
| **Configuration** | ✅ | TOML/JSON + `WAVEOS_*` env; 80+ fields; validate-config |
| **Security & auth** | ✅ | RBAC (admin/operator/viewer), token auth, audit log, secrets (env/vault/aws/gcp) |
| **Observability** | ✅ | JSON/text logging, Prometheus metrics, OpenTelemetry tracing, alerting (webhook/Slack/email, SSRF-safe) |
| **Compliance** | ✅ | NERC/SOC2/DoD reports, auditor package, encryption at rest, mTLS config |
| **Simulation** | ✅ | Synthetic baseline + run with optional fault/drift injection |
| **Extensions (V2/V3)** | ✅ | Plugins, device API (charger/inverter/BESS stubs), orchestration nodes, scheduler, compatibility layer, heartbeat, node health, shadow mode, GitOps state, quotas/SLA |

---

## What It Can Do (Commands & Capabilities)

### Core commands

| Command | Purpose |
|--------|--------|
| `waveos sim --out <dir>` | Generate synthetic baseline + run telemetry (optional fault/drift) into `<dir>/baseline` and `<dir>/run`. |
| `waveos baseline --in <dir>` | Read telemetry from `<dir>`, normalize, aggregate per link, write `baseline.json` (and optional outputs) into `<dir>`. |
| `waveos run --in <dir> --baseline <dir> --out <dir>` | Load run telemetry (dir or `--in https://...`), normalize, score vs baseline, run policy, optionally actuate/recover, write artifacts to `--out`. |
| `waveos report --in <dir> [--open]` | Re-render HTML report from existing artifacts; optionally open in browser. |
| `waveos health-check` | Liveness/readiness for containers/K8s. |
| `waveos validate-config [--config path]` | Validate config before running. |

### Bundle & compliance

- **Bundle:** `waveos bundle build --dir <dir> [--sign] [--encrypt]`; `waveos bundle install --dir <dir>`; canary, rollback; fleet deploy via `scripts/fleet_deploy.py`.
- **Compliance:** `waveos compliance-report --framework DoD|NERC|SOC2 --out <path> [--auditor-package <zip>] [--sign-key ...]`.

### Outputs (per run)

- `health_summary.json`, `events.jsonl`, `actions.json`, `explainability.json`, `run_meta.json`, `metrics.csv`, `report.html`
- Optional evidence pack zip, optional encryption at rest for run_meta
- Actuator: `reroute_requests.jsonl`, `thermal_requests.jsonl`, etc.; `enforced_actions.jsonl` for audit

---

## Repo Layout (Summary)

| Area | Path | Purpose |
|------|------|--------|
| **Core package** | `src/waveos/` | All Python modules |
| **CLI** | `src/waveos/cli.py` | Argument parsing, command dispatch, `main()` |
| **Models** | `src/waveos/models/core.py` | Pydantic: TelemetrySample, HealthScore, Event, ActionRecommendation, BaselineStats/RunStats |
| **Pipeline** | `normalize/`, `scoring/`, `policy/`, `reporting/` | Normalize → score → policy → report |
| **Collectors** | `collectors/file.py`, `http.py`, `auth.py` | Telemetry ingestion |
| **Actuators** | `actuators/base.py`, `sdn_thermal.py`, `adapters/` | Mock, real SDN/thermal, OCPP/Modbus adapters |
| **Recovery** | `recovery.py` | RecoveryOrchestrator, watchdog_ping |
| **Bundle / update** | `bundle.py`, `update_agent.py` | Manifest, sign, verify, install, rollback, canary |
| **Config / license** | `utils/config.py`, `licensing.py` | Load config, license check |
| **Security** | `utils/auth.py`, `rbac.py`, `audit.py`, `secrets.py` | Tokens, roles, audit, secrets |
| **Observability** | `utils/logging.py`, `metrics.py`, `tracing.py`, `alerting.py`, `alerts.py` | Logs, Prometheus, OTEL, alerts |
| **Compliance** | `compliance.py` | NERC/SOC2/DoD reports, auditor package |
| **Sim** | `sim/generator.py` | Demo data, fault injection |
| **Extensions** | `plugins/`, `device_api/`, `orchestration/`, `compatibility/`, `scheduler.py`, `heartbeat.py`, `node_health.py`, `shadow.py`, `gitops/`, `quotas.py`, `sla.py` | V2/V3 features |
| **Docs** | `docs/` | Architecture, PRD, capability matrix, runbooks, deployment, compliance, integration kits |
| **Scripts** | `scripts/` | Watchdog monitor, actuator listener, fleet deploy |
| **Tests** | `tests/` | Pytest unit and integration |
| **CI/CD** | `.github/workflows/` | CI (lint, test, coverage, audit, SBOM, cosign), release, devsecops-delivery |

---

## Quick Start (Local Demo)

```bash
pip install -e .

# 1) Generate simulated baseline + run telemetry
waveos sim --out demo_data

# 2) Build baseline from baseline telemetry
waveos baseline --in demo_data/baseline

# 3) Run pipeline: score run vs baseline, policy, outputs
waveos run --in demo_data/run --baseline demo_data/baseline --out out

# 4) Re-render and open report
waveos report --in out --open
```

Outputs (including `report.html`) are under `out/`. For production: Docker, Kubernetes (`waveos-k8s.yaml`), and config via `WAVEOS_CONFIG` or env; see [DEPLOYMENT.md](DEPLOYMENT.md), [RUN_ON_YOUR_COMPUTER.md](RUN_ON_YOUR_COMPUTER.md), [QUICKSTART_EVALUATION.md](QUICKSTART_EVALUATION.md).

---

## Key Documentation

| Doc | Purpose |
|-----|--------|
| [README.md](../README.md) | Project intro, vision, quick start, env vars |
| [CAPABILITY_AND_IMPLEMENTATION_GUIDE.md](CAPABILITY_AND_IMPLEMENTATION_GUIDE.md) | In-depth architecture, data flow, modules, deployment |
| [PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md](PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md) | What works today vs what’s left for commercial |
| [PRD_DOD_REQUIREMENTS.md](PRD_DOD_REQUIREMENTS.md) | Full 15-area DoD/industrial product requirements |
| [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) | Implementation status per capability area |
| [TELEMETRY_SCHEMA.md](TELEMETRY_SCHEMA.md) | Normalized telemetry schema |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, K8s, production checklist |
| [ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md), [RECOVERY_INTEGRATION_KIT.md](RECOVERY_INTEGRATION_KIT.md), [HARDWARE_INTEGRATION_KIT.md](HARDWARE_INTEGRATION_KIT.md) | Integration and hardware guidance |
| [IMPLEMENTATION_PRIORITIES.md](IMPLEMENTATION_PRIORITIES.md) | Six production gaps: real adapters, action lifecycle, closed-loop verification, fleet, persistence/audit, ops hardening |

---

## Summary

WaveOS is a **production-oriented software control plane** that:

1. **Ingests** telemetry from files or HTTP (with optional auth and limits).
2. **Normalizes** into a single Pydantic schema with versioning.
3. **Scores health** by comparing run to baseline (PASS/WARN/FAIL and drivers).
4. **Recommends actions** via a policy engine (reroute, rate-limit, QoS, thermal).
5. **Applies actions** via mock or real actuator (JSONL + optional HTTP/subprocess).
6. **Integrates** recovery (with approval) and watchdog for supervisors.
7. **Produces** reports (HTML, JSON, JSONL, evidence pack) and compliance reports (NERC, SOC2, DoD).
8. **Supports** secure distribution (signed/encrypted bundles, install, rollback, canary), RBAC, audit, secrets, and observability.

The repo is **modular**, **config-driven**, and **extensible** (plugins, device API, custom actuators). Core pipeline and security/observability are implemented and tested; hardware validation and formal compliance sign-off remain for full commercial deployment (see [PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md](PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md)).

---

## Remaining implementation priorities (production gaps)

The following **six areas** are not yet implemented and are required for production-grade “control-plane OS” and vendor-neutral device control. Full spec and deliverables: **[IMPLEMENTATION_PRIORITIES.md](IMPLEMENTATION_PRIORITIES.md)**.

| # | Priority | Deliverable |
|---|----------|-------------|
| **1** | **Real device adapters** | At least 2 real adapters (e.g. OCPP EV charging, Modbus/SunSpec BESS/inverter, or gNMI/NETCONF/REST SDN) with end-to-end: send command → receive ACK → confirm device state changed. |
| **2** | **Action transaction model** | Action lifecycle (PROPOSED → DISPATCHED → ACKED → VERIFIED); idempotency; ACK/timeout/retry; reconciliation (desired vs actual); rollback/compensation; cooldowns to prevent oscillation. |
| **3** | **Closed-loop verification** | Post-action verification windows; outcome classification (effective / no-effect / harmful / unknown); escalation if system doesn’t stabilize; reports include “what we did” and “what happened after.” |
| **4** | **Fleet: agent + coordinator** | Edge agent per site/node; coordinator to distribute policies/bundles; staged rollout (canary, health-gated promotion); offline-safe local behavior. |
| **5** | **Persistence + audit at scale** | DB-backed runs/events/actions/incidents; retention policies; tamper-evident audit (hash chain); deterministic replay from evidence pack. |
| **6** | **Operations hardening** | Real readiness (ingest freshness, actuator connectivity); resource ceilings; soak/load tests; runbooks; upgrade/migration story so WaveOS can run 24/7 and be operated by someone else. |
