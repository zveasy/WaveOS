# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added (V2)
- **Plugin API:** `waveos.plugins` — registry, `PluginKind` (collector, actuator, policy_extension, device_adapter), `register_plugin`, `list_plugins`, `discover_entry_points`. CLI: `waveos list-plugins [--kind]`.
- **Device API:** `waveos.device_api` — `DeviceDriver`, `DeviceCommand`, `DeviceTelemetry`, `DeviceCapability`; registry and stub adapters (charger, inverter, BESS). CLI: `waveos list-devices [--devices]`.
- **State registry & compatibility matrix:** `state_registry.load/save_compatibility_matrix`, `record_device_state`, `read_device_states`. Config: `WAVEOS_STATE_REGISTRY_PATH`, `WAVEOS_COMPATIBILITY_MATRIX_PATH`.
- **Energy scheduler:** `scheduler.EnergyScheduler`, `ScheduledLoad`, `DispatchInstruction`, `Priority` for load prioritization and dispatch.
- **Policy gates:** `policy/gates.py` — SOC min, temp max, health gate; `run_gates()` for deployment gates and hard limits.
- **Heartbeat:** `heartbeat.emit_heartbeat`, `read_latest_heartbeats` for device/node liveness. Config: `WAVEOS_HEARTBEAT_INTERVAL_SECONDS`.
- **V2 config:** `tenant_id`, `plugin_dirs`, `device_api_enabled`, `scheduler_enabled`, `bundle_canary_percent`, `bundle_offline_cache_path`. See [V2_ROADMAP](docs/V2_ROADMAP.md).

### Added
- Production Dockerfile (multi-stage build, non-root user) and docker-compose using it.
- `waveos health-check` for K8s liveness/readiness probes.
- `waveos validate-config` to validate config and env (exits 0/2 for automation).
- License check: `WAVEOS_LICENSE_KEY`, `WAVEOS_LICENSE_PATH`, `WAVEOS_LICENSE_SKIP` (see docs).
- Optional OpenTelemetry: tracing works when `opentelemetry` is not installed (e.g. minimal image).
- CI: Ruff lint, pytest-cov coverage gate, Docker build and smoke test job.
- SECURITY.md (responsible disclosure, supported versions).
- docs/PRODUCTION_CHECKLIST.md and CLI exit code documentation.
- Makefile targets: `lint`, `test`, `coverage`, `docker-build`, `docker-smoke`.
- `.env.example` for local and production env vars.
- README "Production deployment" section (Docker, K8s, validate-config, checklist).
- `waveos -V` / `--version` (no license required).
- Report and run: validate input dirs and required files; exit 1 with clear messages when missing.
- Alert failure logging: log exception type only (no URLs/secrets).
- Webhook timeout constant (10s) in alerts.
- RUNBOOKS expanded: startup, shutdown, probes, recovery, troubleshooting, version check.
- API reference: health-check, validate-config, --version.
- PRODUCTION_READINESS: implementation summary for V1 production use.
- Tests: CLI validation (version, report/run missing inputs).

### Changed
- docker-compose builds from Dockerfile and runs health-check by default; optional volume for data.
- Release workflow: package version now correctly set from GitHub tag.

### Security
- License enforcement at startup (production); CI and tests use test license key.
- Keyless artifact signing via GitHub OIDC (existing).

## [0.1.0] - 2026-01-26

### Added
- Initial Wave OS demo pipeline and CLI.
