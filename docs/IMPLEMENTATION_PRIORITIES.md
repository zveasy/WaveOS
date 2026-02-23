# WaveOS: Implementation Priorities (Production Gaps)

This document captures the **six major areas** that still need to be implemented for WaveOS to be a production-grade control-plane OS. Each has a clear **deliverable** so we can verify “done.”

Current state: we have **actuator scaffolding** (MockActuator, SdnThermalActuator writing JSONL, optional POST/cmd) and integration kits; production needs **real device control**, **safe action lifecycle**, **closed-loop verification**, **fleet model**, **scalable persistence**, and **operations hardening**.

---

## 1. Real device adapters (the biggest missing piece)

**Current state:** Actuator scaffolding only. No end-to-end “send command → receive ACK → confirm device state changed.”

**Requirement:** Production needs **at least 2 real adapters** with end-to-end control to prove “vendor-neutral” isn’t just a claim. Choose from:

- **EV charging (OCPP)** OR **BESS/inverter (Modbus/SunSpec)** OR **SDN/optical (gNMI/NETCONF/REST)**
- Plus a **second** adapter (different domain or vendor) to demonstrate vendor neutrality.

**Deliverable:**  
*“WaveOS can send a command, receive ACK, and confirm device state changed.”*

**Implied work:**

- Real protocol integration (OCPP, Modbus/SunSpec, or gNMI/NETCONF/REST) per adapter.
- Command → device → ACK flow; read-back of device state after command.
- Document which adapters are “validated” and with which devices/vendors.

---

## 2. Action transaction model (safety + reliability)

**Current state:** Actions are recommended and optionally written to JSONL or POSTed; no formal lifecycle, idempotency, or rollback.

**Requirement:** To avoid dangerous or inconsistent actuation:

- **Action idempotency** — Same action key/context can be applied once; duplicates are detected and ignored or reconciled.
- **ACK / timeout / retry** — Send → wait for ACK with timeout; retry with backoff; eventual failure handling.
- **Reconciliation** — Desired state vs actual state; corrective actions when drift is detected.
- **Rollback / compensation** for partial applies — If a batch of actions partially fails, defined rollback or compensation actions.
- **Cooldowns** to prevent oscillation — Minimum interval between same or conflicting actions on the same entity.

**Deliverable:**  
*Actions have lifecycle states such as: **PROPOSED → DISPATCHED → ACKED → VERIFIED** (and terminal states: FAILED, ROLLED_BACK, CANCELLED).*

**Implied work:**

- Action state machine and persistence of state per action ID.
- Timeouts, retries, and cooldown configuration.
- Reconciliation loop (desired vs actual) and rollback/compensation paths.

---

## 3. Closed-loop verification (prove the action worked)

**Current state:** We report “what we recommended” and “what we sent”; we do not systematically measure impact after actuation.

**Requirement:** WaveOS must measure impact after actuation:

- **Post-action verification windows** — After dispatching an action, observe telemetry for a defined window to confirm effect.
- **Action outcomes:** **effective** / **no-effect** / **harmful** / **unknown** — classify each action by observed outcome.
- **Escalation logic** if the system doesn’t stabilize — e.g. retry, escalate to different action, or alert human.

**Deliverable:**  
*Reports include “what we did” **and** “what happened after” (outcome classification and, where applicable, escalation).*

**Implied work:**

- Verification window (time + metrics) after each action.
- Outcome classification (effective / no-effect / harmful / unknown) from telemetry and thresholds.
- Escalation rules and integration with alerting/recovery.
- Report and evidence pack fields: action ID, outcome, verification summary.

---

## 4. Fleet: agent + coordinator (WaveOS as an OS, not a single run)

**Current state:** Single-run CLI and optional fleet deploy script (SSH push). No first-class “edge agent” or “coordinator” that distributes policy and bundles across sites.

**Requirement:** For “control-plane OS” across many nodes/sites:

- **Edge agent** per site/node — Lightweight process that runs policy, collects telemetry, executes actions, and reports back.
- **Coordinator** — Distributes policies and bundles to agents; collects status and reports.
- **Staged rollout** — Canary, health-gated promotion (e.g. only promote if canary nodes stay healthy).
- **Offline-safe behavior** — Local safe mode when coordinator is unreachable; no unsafe actuation without policy.

**Deliverable:**  
*Manage multiple nodes/sites and deploy policy updates safely (agent + coordinator + staged rollout + offline-safe behavior).*

**Implied work:**

- Agent process (or mode) that runs per node; heartbeat and telemetry to coordinator.
- Coordinator service: policy/bundle distribution, status aggregation, rollout orchestration.
- Canary and health-gated promotion (already have canary in update_agent; extend to “fleet canary”).
- Offline policy: e.g. “when disconnected, only allow these safe actions or no actuation.”

---

## 5. Persistence + audit that scales (beyond files)

**Current state:** File-based outputs (health_summary.json, events.jsonl, actions.json, run_meta.json, audit log files). No DB-backed runs/events/actions, no hash chain, no deterministic replay.

**Requirement:** Production needs:

- **DB-backed** runs, events, actions, incidents — Queryable, with retention policies.
- **Retention policies** — Configurable retention per data type; archival or purge.
- **Tamper-evident audit** — Hash chain (e.g. each record includes hash of previous) so integrity can be verified.
- **Deterministic replay** from evidence pack — Load an evidence pack and replay/verify decisions for forensics or compliance.

**Deliverable:**  
*“Audit-ready + searchable + replayable.”* Persistence layer (DB), retention, hash chain for audit log, and replay from evidence pack.

**Implied work:**

- Schema and backend for runs/events/actions/incidents (e.g. SQLite/Postgres or documented interface).
- Retention policy engine and cleanup/archival.
- Audit log format with hash chain; verification API or CLI.
- Replay path: load evidence pack → reconstruct state or re-run pipeline in “replay” mode.

---

## 6. Operations hardening (24/7 reliability)

**Current state:** Basic health-check, config validation, runbooks in docs. No real readiness checks for ingest freshness or actuator connectivity; no resource ceilings or formal soak/load story; upgrade/migration is ad hoc.

**Requirement:**

- **Real readiness checks** — Ingest freshness (telemetry not stale), actuator connectivity (can we reach the device or API?).
- **Resource ceilings** — Memory/CPU limits and behavior when exceeded (e.g. graceful degradation, no OOM kill).
- **Soak / load tests** — Documented or automated; prove stability under sustained load.
- **Runbooks** — Operator-facing runbooks for common failures, rollback, and escalation (linked from alerts).
- **Upgrade / migration story** — Safe upgrade path (e.g. config schema, DB schema); rollback of upgrades.

**Deliverable:**  
*Can run continuously and be operated by someone else.* Readiness reflects real dependencies; resource limits and soak tests exist; runbooks and upgrade/migration are documented and tested.

**Implied work:**

- Readiness: check telemetry source freshness and actuator reachability; fail readiness if critical path is broken.
- Resource limits (memory, CPU) and behavior under limit (configurable).
- Soak/load test suite or doc (e.g. run N runs over M hours; no leaks, no crashes).
- Runbooks for: pipeline failure, actuator failure, recovery, rollback, upgrade.
- Upgrade/migration: versioned config and state; migration scripts and rollback procedure.

---

## Summary table

| # | Priority | Deliverable (one line) |
|---|----------|------------------------|
| 1 | Real device adapters | WaveOS can send a command, receive ACK, and confirm device state changed (≥2 adapters). |
| 2 | Action transaction model | Actions have lifecycle: PROPOSED → DISPATCHED → ACKED → VERIFIED (plus idempotency, retry, rollback, cooldowns). |
| 3 | Closed-loop verification | Reports include “what we did” and “what happened after” (outcome: effective / no-effect / harmful / unknown; escalation). |
| 4 | Fleet agent + coordinator | Manage multiple nodes/sites; deploy policy updates safely; staged rollout; offline-safe behavior. |
| 5 | Persistence + audit at scale | Audit-ready, searchable, replayable; DB-backed runs/events/actions; retention; hash chain; replay from evidence pack. |
| 6 | Operations hardening | Run 24/7 and be operable by someone else; real readiness; resource ceilings; soak tests; runbooks; upgrade/migration. |

---

## How this fits with other docs

- **Technical/product gaps** in [READINESS_REMAINING.md](READINESS_REMAINING.md) (e.g. “One real actuator path”) are **refined and expanded** here into “2 real adapters with full command→ACK→verify” and the action/verification model.
- **Commercialization** in [COMMERCIALIZATION_ROADMAP.md](COMMERCIALIZATION_ROADMAP.md) and [PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md](PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md) remains; this doc is the **implementation roadmap** for the core control-plane behavior.
- **Integration kits** ([ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md), [HARDWARE_INTEGRATION_KIT.md](HARDWARE_INTEGRATION_KIT.md)) describe how to plug devices; **real adapters** (priority 1) are concrete implementations that satisfy the “command → ACK → state changed” deliverable.

Use this document to prioritize sprints and to gate “production-ready” claims: e.g. “Real device adapters + action transaction model + closed-loop verification” as minimum for “we can control real hardware safely.”
