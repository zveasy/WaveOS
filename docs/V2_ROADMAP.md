# WaveOS V2 Roadmap — Implementation Status

V2 targets **100% of the PRD V2 milestones** across the 15 capability areas. This document tracks what is implemented and what remains.

---

## Implemented (V2)

### 1. Universal compatibility layer
- **Compatibility matrix:** `state_registry.load_compatibility_matrix` / `save_compatibility_matrix` (kernel/firmware/software versions). Config: `WAVEOS_COMPATIBILITY_MATRIX_PATH`.
- **Protocol adapters:** Plugin API allows registering collector/actuator/device_adapter plugins; compatibility matrix can drive which adapter to use per vendor.

### 2. Hardware abstraction + device API
- **Standard device API:** `waveos.device_api` — `DeviceDriver`, `DeviceCommand`, `DeviceTelemetry`, `DeviceCapability` (charger, inverter, BESS, microgrid, relay, meter).
- **Device registry:** `get_device_registry`, `register_driver`, `get_driver_instance`.
- **Stub adapters:** Charger, inverter, BESS stub drivers in `device_api/adapters.py`; registered by default. CLI: `waveos list-devices [--devices]`.

### 3. Secure software distribution
- **Config:** `bundle_canary_percent`, `bundle_offline_cache_path` in config and env. Implementation of canary rollout and offline cache is next (bundle install path + cache dir).

### 4. Distributed orchestration
- **State registry:** `state_registry.record_device_state`, `read_device_states` — record device state per node. Config: `WAVEOS_STATE_REGISTRY_PATH`.
- **Heartbeat:** `heartbeat.emit_heartbeat`, `read_latest_heartbeats` for device/node liveness. Config: `WAVEOS_HEARTBEAT_INTERVAL_SECONDS`.

### 5. Energy scheduler
- **Scheduler API:** `scheduler.EnergyScheduler` — `ScheduledLoad`, `DispatchInstruction`, `Priority`, `add_load`, `schedule()`. Config: `WAVEOS_SCHEDULER_ENABLED`.

### 6. Communications fabric
- **Foundation:** File-based persistence and state registry; real-time pub/sub and C2 channels are V2 follow-on (e.g. optional Redis or in-process bus).

### 7. Policy engine + governance
- **Enforcement gates:** `policy/gates.py` — `check_soc_limit`, `check_temp_limit`, `check_health_gate`, `run_gates(gates_config, scores, telemetry_aggregates)` for hard limits and deployment gates.

### 8. Digital twin + simulation
- **Foundation:** Existing sim + baseline/run; what-if and digital twin API can call sim with parameter overrides (next step).

### 9. Observability
- **Heartbeat:** Emit and read heartbeats for device/node liveness (see above).

### 10. Fault isolation
- **Foundation:** State registry and heartbeat support “last seen” per node; isolation/failover logic can use these (next step).

### 11. Cybersecurity
- **Foundation:** mTLS and encrypted telemetry are V2 follow-on (optional TLS helpers).

### 12. Version control for infrastructure
- **State registry:** Device state records; compatibility matrix (see above).

### 13. Plugin / module system
- **Plugin API:** `waveos.plugins` — `PluginMetadata`, `PluginKind` (collector, actuator, policy_extension, device_adapter), `get_registry`, `register_plugin`, `get_plugin_instance`, `list_plugins`, `discover_entry_points`. CLI: `waveos list-plugins [--kind]`. Config: `WAVEOS_PLUGIN_DIRS`.

### 14. Multi-tenant
- **Config:** `tenant_id` in config and `WAVEOS_TENANT_ID`; audit and data paths can be scoped by tenant in callers.

### 15. Compliance
- **Foundation:** Policy gates (SOC, temp, health) support deployment gates; NERC/SOC2 report templates are a follow-on.

---

## Config (V2)

| Env / config | Purpose |
|--------------|--------|
| `WAVEOS_TENANT_ID` | Multi-tenant isolation |
| `WAVEOS_PLUGIN_DIRS` | Comma-separated plugin directories |
| `WAVEOS_DEVICE_API_ENABLED` | Enable device API usage in pipeline |
| `WAVEOS_SCHEDULER_ENABLED` | Enable energy scheduler |
| `WAVEOS_HEARTBEAT_INTERVAL_SECONDS` | Heartbeat emit interval |
| `WAVEOS_COMPATIBILITY_MATRIX_PATH` | Compatibility matrix JSON path |
| `WAVEOS_STATE_REGISTRY_PATH` | Device state registry JSONL path |
| `WAVEOS_BUNDLE_CANARY_PERCENT` | Canary rollout percentage (0–100) |
| `WAVEOS_BUNDLE_OFFLINE_CACHE_PATH` | Offline bundle cache directory |

---

## CLI (V2)

- `waveos list-plugins [--kind collector|actuator|policy_extension|device_adapter]`
- `waveos list-devices [--devices]`

---

## Remaining (V2 follow-on)

- Bundle: implement canary rollout and offline cache in `update_agent`.
- Pub/sub: optional in-process or Redis-backed bus for telemetry and C2.
- mTLS/encrypted telemetry: optional TLS and encryption hooks.
- Digital twin API: function that runs sim with overrides and returns what-if result.
- NERC/SOC2 report template generator.
- Wire policy gates into `cmd_run` (run gates after scoring; block or warn on failure).

---

See [PRD_DOD_REQUIREMENTS.md](PRD_DOD_REQUIREMENTS.md) and [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) for full V2/V3 scope.
