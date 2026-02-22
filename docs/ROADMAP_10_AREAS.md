# WaveOS: 10-Area Production Roadmap

This document plans the **10 capability areas** that take WaveOS from “production-ready software” to **real device control, closed-loop verification, fleet orchestration, and full productization**. Each area is broken into phases, dependencies, and concrete deliverables.

---

## Overview

| # | Area | Goal | Blocker / priority |
|---|------|------|--------------------|
| 1 | **Real device control** | WaveOS reliably executes actions against real infrastructure (SDN, charger, inverter/BESS) with reliability and safety. | **#1 blocker** |
| 2 | **Closed-loop control & verification** | Every action has measured effect; control plane proves it worked. | Depends on 1 |
| 3 | **Fleet / multi-node orchestration** | WaveOS runs across sites with coordinator, node agents, staged rollout. | Depends on 1 |
| 4 | **Stronger policy engine** | Policies as auditable operational doctrine (schema, validation, explainability, conflict resolution). | Parallel |
| 5 | **Production-grade data plane** | Streaming ingestion (Kafka/MQTT/NATS), schema registry, time sync. | Parallel |
| 6 | **Persistence, state, and audit** | Durable storage (Postgres/SQLite), immutable audit, verifiable evidence packs. | Parallel |
| 7 | **Security hardening** | mTLS everywhere, first-class secrets, supply chain, AuthN/AuthZ. | Parallel |
| 8 | **SRE/operations maturity** | Health probes, runbooks, golden signals, performance budgets. | Parallel |
| 9 | **Compliance that passes audit** | Control mapping, access reviews, change management. | Depends on 6, 7 |
| 10 | **Productization essentials** | Installer, reference integrations, minimal admin UX. | Depends on 1, 3 |

---

## 1. Real device control (#1 blocker)

**Goal:** WaveOS can reliably execute actions against real infrastructure, not just write JSONL.

### 1.1 Device adapters (drivers) for real targets

| Target | Protocol / API | Actions | Status / deliverable |
|--------|----------------|---------|----------------------|
| **SDN switch** | gNMI / NETCONF / REST | Reroute, QoS, rate limits, port ops | Phase 1: REST adapter + interface for gNMI/NETCONF |
| **EV charger** | OCPP 1.6 / 2.0.1 | Throttle/limit, pause/resume, fault readback | Phase 1: Adapter interface + OCPP stub; Phase 2: real OCPP client |
| **Inverter / BESS** | Modbus TCP/RTU, SunSpec, vendor APIs | Setpoints, curtailment, SOC constraints | Phase 1: Modbus/SunSpec adapter interface + stub; Phase 2: real Modbus/SunSpec |

**Implementation:** `actuators/adapters/` with base class and per-protocol adapters; config selects adapter(s). At least one “real” path (e.g. SDN REST) that performs HTTP with ACK/retry.

### 1.2 Actuation reliability layer

| Capability | Description | Deliverable |
|------------|-------------|-------------|
| **ACK / timeout / retry** | Every device call has timeout; retry with backoff; record ACK/failure | `actuators/reliability.py`: wrapper that retries and records outcome |
| **Idempotency keys** | Per-action key (e.g. hash of action + entity + params) to avoid duplicate execution | Store last N keys with TTL; skip if key seen |
| **State reconciliation** | “Desired state” vs “actual state” (read-back after apply) | Optional: post-apply read; diff; report drift |
| **Rollback / compensation** | When partial apply happens, run compensating actions or rollback list | On failure after N retries: run configurable rollback_actions or mark “partial” and persist |

**Implementation:** `ActuationReliabilityLayer` wraps any `RealActuator`; uses config for retry_count, timeout_sec, idempotency_ttl; writes `action_outcomes.jsonl` (action_id, outcome: succeeded | no_effect | degraded | unknown).

### 1.3 Safety interlocks

| Capability | Description | Deliverable |
|------------|-------------|-------------|
| **Hard limits** | Temp, SOC, current, breaker limits enforced before apply | `actuators/safety.py`: check against current telemetry or last known state; reject if over limit |
| **Two-person rule / approval** | High-risk actions require approval (file, API, or workflow) | Approval callback or file; list of action types that require approval |
| **Rate limiting & cooldown** | Max N actions per minute; cooldown window after certain actions | Per entity_type/entity_id or global; cooldown_seconds after e.g. REROUTE |

**Implementation:** `SafetyInterlock` with config: max_temp_c, min_soc_pct, max_current_a; approval_required_action_types; max_actions_per_minute; cooldown_seconds. Called before apply.

### Phase 1 (implemented in this pass)

- [x] Actuation reliability: retry, timeout, idempotency keys, outcome recording (succeeded / no_effect / degraded / unknown), optional rollback on partial.
- [x] Safety interlocks: hard limits (temp, SOC, current), approval workflow (file or env), rate limit + cooldown.
- [x] Device adapter base + SDN REST adapter (POST with retry, outcome).
- [x] OCPP and Modbus adapter interfaces (stubs) for future real implementations.

### Phase 2 (follow-on)

- [ ] gNMI/NETCONF SDN adapter (or gateway that translates WaveOS actions to gNMI).
- [ ] Real OCPP 1.6/2.0.1 client for EV charger (throttle, pause/resume, fault readback).
- [ ] Real Modbus TCP/RTU or SunSpec client for inverter/BESS.
- [ ] Desired vs actual state reconciliation (read-back and diff).

---

## 2. Closed-loop control & verification

**Goal:** Every action has measured effect; WaveOS knows whether the system improved.

### 2.1 Post-action verification

- After applying actions, re-check telemetry within a configurable window.
- Mark action outcome: **succeeded** / **no_effect** / **degraded** / **unknown** (foundation in place via reliability layer).
- Persist outcomes for incident and reporting.

### 2.2 Control-loop evaluation

- Latency budgets: detect → decide → act → stabilize (metrics and SLOs).
- “Confidence” scoring and fallback: shadow mode → enforce mode when confidence is high.

### 2.3 Incident workflow

- Generate incident objects: timeline, actions taken, outcomes, recommended next steps.
- Store in persistence layer (see area 6).

**Dependencies:** Real device control (1); optional persistence (6).  
**Phases:** Phase 1: post-action verification hook and outcome in run_meta. **Done.** Phase 2: incident model and workflow. **Done:** `build_incident_from_run()` when run has FAIL scores or failed action outcomes; incidents persisted to SQLite (incidents table); timeline, actions_taken, outcomes, recommended_next_steps.

---

## 3. Fleet / multi-node orchestration

**Goal:** WaveOS as an OS across sites and nodes with centralized policy and distributed execution.

### 3.1 Node agent

- Lightweight runtime on each node (edge): heartbeats, local watchdog, local fallback behavior.
- Current: heartbeat + node_health; extend to “agent” that runs pipeline and reports to coordinator.

### 3.2 Coordinator

- Fleet registry, node roles, leader election (or coordinator service).
- Policy distribution and version pinning per site.

### 3.3 Config + bundle rollout at scale

- Staged deployments (canary by site / percentage).
- Health-gated promotion.
- Automatic rollback on FAIL or KPI regression.

**Dependencies:** Real device control (1); persistence (6) for registry and state.  
**Phases:** Phase 1: node registry + coordinator API (or file-based). **Done:** Node registry (orchestration/nodes.py), list-nodes, **fleet-status** (nodes + health from heartbeats). Phase 2: canary by site. **Done:** `get_nodes_by_site(site_id)`, `get_nodes_in_sites(site_ids)`; `bundle_canary_sites` config and `WAVEOS_BUNDLE_CANARY_SITES`; `waveos list-nodes --canary-sites` / `--sites`; `fleet_deploy.py --canary-sites`; fleet-status shows site_id. Phase 3: health-gated promotion and auto-rollback.

---

## 4. Stronger policy engine

**Goal:** Policies become auditable operational procedures.

### 4.1 Policy authoring + validation

- Policy schema, linting, unit tests for policies.
- Simulation harness: “if these events happen, actions must be X.”

### 4.2 Policy explainability contract

- Every recommendation: rule IDs, thresholds, evidence.
- Deterministic replay from stored evidence pack.

### 4.3 Conflict resolution

- Multiple rules firing → priority, merging, inhibition, cooldowns.

**Dependencies:** None. Can run in parallel.  
**Phases:** Phase 1: rule IDs and evidence in recommendations. **Done:** `ActionRecommendation.rule_id` (e.g. `health_fail_reroute`, `thermal_constraint`, `policy_rule_<id>`); explainability JSON includes `rule_id` per action. Phase 2: policy schema and lint. **Done:** `waveos policy lint <file>`; `policy/schema.py` validates rules (metric/operator/threshold, action type, template-style type). Phase 3: conflict resolution and simulation harness.

---

## 5. Production-grade data plane

**Goal:** Ingestion and normalization survive real-world chaos.

### 5.1 Streaming ingestion

- Kafka / MQTT / NATS support (optional).
- Backpressure, dedup, ordering, late-arriving data handling.

### 5.2 Schema governance

- Explicit schema registry + version negotiation.
- Per-source adapters + test fixtures.

### 5.3 Time sync + clock skew

- Monotonic windows, drift-tolerant aggregation.

**Dependencies:** None. Parallel.  
**Phases:** Phase 1: Kafka or MQTT connector. **Done:** MQTT connector `load_records_from_mqtt()` in `collectors/mqtt.py` (optional `paho-mqtt`); `waveos ingest-mqtt --broker <host> --topic <topic> --out <path>` pulls JSON messages and writes JSONL; supports `--timeout`, `--max-messages`, `--port`. Phase 2: schema registry. **Done:** `schema_registry.TELEMETRY_SCHEMA_VERSIONS`, `validate_telemetry_schema(records, version)`; `waveos validate-schema <file> [--version 1]`. Phase 3: time-window and skew handling.

---

## 6. Persistence, state, and audit

**Goal:** State isn’t just files; production needs durable storage and searchable audit.

### 6.1 Persistent storage layer

- Postgres (fleet) and/or SQLite (local) for: runs, scores, events, actions, deployments, incidents.

### 6.2 Immutable audit trails

- Append-only logs with hash chaining (tamper evidence).
- Retention + legal hold policies.

### 6.3 Verifiable evidence packs

- Manifest signing + provenance (SLSA-style).
- Reproducible “run replay” bundle.

**Dependencies:** None. Parallel.  
**Phases:** Phase 1: SQLite backend. **Done.** Phase 2: hash-chained audit. **Done:** `audit_hash_chain` config / `WAVEOS_AUDIT_HASH_CHAIN`; each audit line has `prev_hash` and `hash` (SHA-256 chain); sidecar `.last_hash` for rotation. Phase 3: evidence pack attestation. **Done:** `build_evidence_attestation(out_dir, run_id)` writes `evidence_attestation.json` (artifact path + SHA-256); included in evidence pack zip; `verify_evidence_attestation(path)`; `waveos verify-evidence-attestation <path>`.

---

## 7. Security hardening

**Goal:** WaveOS withstands hostile environments (DoD/industrial).

### 7.1 mTLS everywhere

- Ingestion endpoints, actuator calls, node-to-coordinator.

### 7.2 Secret management

- Vault/AWS Secrets Manager as first-class (no env fallback in prod; already partially done).

### 7.3 Supply chain

- Signed containers, SBOM enforcement, dependency allowlist, vulnerability gating.

### 7.4 AuthN/AuthZ for humans + machines

- Short-lived tokens (OIDC/JWT), service identities, least-privilege RBAC per site/device.

**Dependencies:** None. Parallel.  
**Phases:** Phase 1: mTLS for actuator and ingestion. **Done (actuator):** `actuator_mtls_cert_path`, `actuator_mtls_key_path`, `actuator_mtls_ca_path` (env: WAVEOS_ACTUATOR_MTLS_*); SdnRestAdapter and OcppChargerAdapter use client cert for HTTPS when set. Phase 2: no env fallback in prod everywhere. **Done:** `strict_secrets` config and `WAVEOS_STRICT_SECRETS=1`; when set, vault/aws/gcp do not fall back to env JSON; `set_strict_secrets()` from config at startup. Phase 3: OIDC/JWT and scoped RBAC.

---

## 8. SRE/operations maturity

**Goal:** Run 24/7, upgrade safely, debug fast.

### 8.1 Health endpoints + readiness probes

- Liveness/readiness with real checks (telemetry ingest ok, policy ok, actuator ok).

### 8.2 Runbooks

- “What to do when scoring spikes,” “actuator down,” “telemetry stale.”

### 8.3 Observability completeness

- Golden signals; distributed tracing across ingest → score → policy → act.

### 8.4 Performance budgets

- Memory/CPU ceilings; load test suite + soak tests.

**Dependencies:** None. Parallel.  
**Phases:** Phase 1: readiness checks. **Done.** Phase 2: runbook automation. **Done:** `waveos runbook list`, `waveos runbook run <id>`; runbooks telemetry_stale, actuator_down, scoring_spike (steps informational). Phase 3: budgets and soak tests. **Done:** Performance budgets via existing `max_memory_mb`/`max_cpu_seconds` and `apply_resource_limits()`; `waveos soak-test --runs N --every SEC --in ... --baseline ... --out ...` (optional `--min-success`).

---

## 9. Compliance that passes audit

**Goal:** Meet control objectives, not just generate reports.

### 9.1 Control mapping

- SOC2/DoD/NERC mapped to code controls, operational controls, evidence artifacts.

### 9.2 Access reviews

- Periodic RBAC review exports.

### 9.3 Change management

- Policy and bundle changes reviewed/approved/traceable.

**Dependencies:** Persistence (6), security (7).  
**Phases:** Phase 1: control mapping doc and evidence links. **Done:** [CONTROL_MAPPING.md](CONTROL_MAPPING.md) (control ID → code/ops → evidence artifact); evidence quick reference. Phase 2: access review export. **Done:** `waveos access-review-export --out <path>` (roles + permissions, permission_clearance, token_assignments summary). Phase 3: change workflow. **Done:** `change_log.append_change_log()` on install/promote/rollback; `deployment_changes.jsonl` in bundle state dir; `waveos change-log [--path] [--limit]`.

---

## 10. Productization essentials

**Goal:** Buyers can buy, deploy, and use it.

### 10.1 Installer + upgrade path

- One-command install; migrations for config/state.

### 10.2 Reference integrations

- At least 2 “real” adapters (e.g. one switch + one charger).

### 10.3 Admin UX (minimal)

- Fleet status, last runs, active policies, deployments/rollbacks.

**Dependencies:** Real device control (1), fleet (3).  
**Phases:** Phase 1: installer script and migration script. **Done:** `waveos install [--prefix PREFIX] [--config]` (create out dirs + optional config.toml.example); `scripts/install.sh`; `waveos migrate [--db PATH]` (ensure persistence schema); `waveos last-runs [--db] [--limit] [--incidents]` (admin view from persistence). Phase 2: second real adapter; Phase 3: minimal admin UI or CLI views. **Done (CLI):** `waveos status` (active bundle, last runs summary, fleet nodes/healthy, policy path); `waveos verify-evidence-attestation <path>`.

---

## Implementation order (recommended)

1. **Real device control (area 1)** — actuation reliability, safety interlocks, device adapters (SDN REST + stubs). **This unblocks everything else that needs “real” execution.**
2. **Persistence (6)** and **Security (7)** — in parallel where possible.
3. **Closed-loop verification (2)** and **Fleet (3)** — build on 1 and 6.
4. **Policy (4), Data plane (5), SRE (8)** — parallel.
5. **Compliance (9)** and **Productization (10)** — last, once 1–3 and 6–7 are solid.

This roadmap is the master plan; individual area docs (e.g. ACTUATOR_INTEGRATION_KIT.md, HARDWARE_INTEGRATION_KIT.md) should be updated as each phase is implemented.
