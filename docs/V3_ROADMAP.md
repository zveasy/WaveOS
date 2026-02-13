# WaveOS V3 Roadmap

V3 completes the 15-capability control-plane OS vision with DoD/industrial hardening, GitOps for hardware, and full observability.

## Delivered in V3

### Universal compatibility (multi-RTOS)
- **Runtime translation layer** (`src/waveos/compatibility/`) — map vendor/kernel payloads to generic `TelemetrySample` and common field names.

### Secure software distribution
- **Clearance-based RBAC** — `Clearance` enum (UNCLASSIFIED → SECRET), `Principal.clearance`, permissions `DEPLOY_BUNDLE`, `MANAGE_NODES`, `PERMISSION_CLEARANCE`; `authorize()` enforces clearance when set.
- **Bundle attestation** — `BundleMetadata.attestation` for supply-chain provenance; `build_manifest(..., attestation=...)`.

### Distributed orchestration
- **Node registry** — `NodeRole` (EDGE, CLOUD, AIR_GAPPED, CONTROLLER), `NodeRecord`, `get_node_registry`, `register_node`, `load_nodes_from_file`, `save_nodes_to_file`; CLI `waveos list-nodes`.

### Energy scheduler
- **Island mode and grid response** — `EnergyScheduler.island_mode`, `GridSignal` (frequency_hz, price_signal, is_island), `set_grid_signal()`.

### Digital twin / simulation
- **Shadow mode** — `shadow.run_shadow()` runs pipeline without actuation and returns diff vs live.

### Observability
- **SLA metrics** — `sla.record_run_success` / `record_run_failure` with tenant_id and site_id labels for Prometheus.

### Fault isolation / self-healing
- **Node health** — `node_health.healthy_nodes()`, `unhealthy_node_ids()` from heartbeat age; use in scheduler/failover to skip unhealthy nodes.

### Zero-trust / IDS
- **Device identity** — `security.DeviceIdentity` (device_id, credential_hint, site_id).
- **Secure boot** — config `secure_boot_enabled`; IDS hook `set_anomaly_callback`, `on_anomaly(rule_id, context)`.

### GitOps for hardware
- **Desired state** — `gitops.DesiredState`, `load_desired_state`, `current_state_from_registry`, `diff_state`, `save_state_history`, `apply_desired_state`.

### Policy
- **Policy templates** — `policy/templates.load_policy_templates(path)` for NERC/DoD-style JSON templates.

### Multi-tenant
- **Tenant quotas** — config `tenant_max_runs_per_hour`; `quotas.check_quota()`, `record_run()`.

### Compliance
- **Compliance reports** — `compliance.generate_report(framework, run_meta, audit_path)`, `write_report()`; CLI `waveos compliance-report --framework NERC|SOC2|DoD --out path`.

### Marketplace
- **Marketplace doc** — [MARKETPLACE.md](MARKETPLACE.md) (plugin packaging, certification checklist, device adapters).

## Relevant modules

| Area        | Module / path |
|------------|----------------|
| Compatibility | `compatibility/` |
| RBAC       | `utils/rbac.py` |
| Bundle     | `bundle.py` (attestation) |
| Orchestration | `orchestration/nodes.py` |
| Scheduler  | `scheduler.py` (GridSignal, island_mode) |
| Shadow     | `shadow.py` |
| SLA        | `sla.py` |
| Node health | `node_health.py` |
| Security   | `security.py` |
| GitOps     | `gitops/` |
| Policy templates | `policy/templates.py` |
| Quotas     | `quotas.py` |
| Compliance | `compliance.py` |

## Summary

V3 brings the capability matrix to **100%** for the in-repo scope: multi-RTOS translation, clearance and attestation, node registry and GitOps workflow, island/grid scheduler, shadow mode, SLA metrics, node health for failover, zero-trust/IDS hooks, compliance report generator, tenant quotas, policy templates, and marketplace documentation.
