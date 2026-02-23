# WaveOS: Next Steps

Ordered by impact. Use this to pick the next sprint or to answer “what’s left?”

---

## Already in place (reference)

- **Pipeline:** sim → baseline → run → report; health scoring, policy, actions, evidence pack, HTML report.
- **Coordinator v1:** Node registry, heartbeats, policy, run ingestion, fleet status, rollout API (start/promote/rollback).
- **Action signing:** Coordinator signs batches; agent verifies; nonce/timestamp replay protection; evidence pack.
- **Identity/audit:** Optional mTLS (`WAVEOS_COORDINATOR_REQUIRE_MTLS=1`), audit log for auth decisions.
- **Enforcement lock:** Escalation can set lock/approval paths; run path skips actuation when locked.
- **Production profile:** `configs/production.toml` and `configs/coordinator.production.env`; soak/chaos scripts and results template.
- **Persistence, incident lifecycle, desired-state reconciliation, rollout logic** (canary, gates, rollback) are implemented; some wiring to run path or operator flows may still be partial.

---

## 1. Immediate (validation and wiring)

| Step | What to do | Why |
|------|------------|-----|
| **Run soak + chaos and record results** | Run 4h (or 24h) soak and chaos scenarios; fill [SOAK_CHAOS_RESULTS.md](SOAK_CHAOS_RESULTS.md) with run counts, outcomes, sign-off. | Turns “we built it” into “we operated it” and de-risks production. |
| **Smoke test with verify** | Use `bash scripts/smoke_test.sh --verify` (and open `report.html`) to confirm outputs have real content. | Confirms the pipeline does what it should, not just that it exits 0. |
| **Wire escalation → lock in operator flow** | When `incident_escalate(..., lock_enforcement=True)` is used, ensure `enforcement_locked_path` (and optional approval path) are set (by code or runbook). Run path already respects them. | So “escalate incident → lock enforcement and require approvals” is end-to-end. |
| **Promotion gates before promote** | Before calling `POST /rollout/<id>/promote`, check `promotion_gate_passed()` using fleet status and run outcomes (from coordinator store or heartbeat payloads). Optionally add a “check gates” endpoint or document the flow. | So “promote only if 95% healthy and N good runs” is enforceable. |

---

## 2. Short-term (production hardening)

| Step | What to do | Why |
|------|------------|-----|
| **mTLS and secrets in production** | In production, set `WAVEOS_COORDINATOR_REQUIRE_MTLS=1` and use a real secrets provider (Vault/AWS/GCP); no env/JSON fallback. | Matches [SECURITY_PRODUCTION.md](SECURITY_PRODUCTION.md) and production profile. |
| **RBAC (if buyer needs it)** | Add optional per-site/per-node (or capability) checks in coordinator `_auth_ok` using config/env (e.g. allowed_node_ids, allowed_site_ids). Audit already logs auth decisions. | Enterprise often wants “this identity can only touch these nodes/sites.” |
| **Real readiness checks** | Extend readiness beyond “config loaded”: e.g. telemetry source reachable, actuator/coordinator reachable when required. | So K8s/orchestrator doesn’t send traffic when critical path is broken. |
| **Runbooks and upgrade/migration** | Document runbooks for pipeline failure, actuator failure, rollback, escalation; document upgrade/migration (config and DB schema) and test once. | Needed for 24/7 operations and handoff. |

---

## 3. Medium-term (from Implementation Priorities)

From [IMPLEMENTATION_PRIORITIES.md](IMPLEMENTATION_PRIORITIES.md); order by your roadmap:

| # | Priority | Deliverable (one line) |
|---|----------|------------------------|
| 1 | **Real device adapters** | ≥2 adapters: send command → ACK → confirm device state changed (e.g. SDN REST, Modbus inverter; document validated devices/vendors). |
| 2 | **Action transaction model** | Lifecycle PROPOSED → DISPATCHED → ACKED → VERIFIED in code and persistence; idempotency, retry, cooldowns, rollback. (Partially in place; complete and wire everywhere.) |
| 3 | **Closed-loop verification** | Reports and evidence include “what happened after” (outcome: effective/no-effect/harmful/unknown); escalation when system doesn’t stabilize. (Partially in place; complete outcome classification and escalation wiring.) |
| 4 | **Fleet agent + coordinator** | Multi-node/site management, policy rollout, offline-safe behavior. (Coordinator and rollout API exist; agent and offline policy can be deepened.) |
| 5 | **Persistence + audit at scale** | DB-backed runs/events/actions, retention, audit hash chain, replay from evidence pack. (Persistence exists; add retention, hash chain, replay.) |
| 6 | **Operations hardening** | Readiness reflects real deps; resource ceilings; soak tests and runbooks. (Soak/chaos tooling exists; complete as above.) |

---

## 4. Commercial (from Product Status)

From [PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md](PRODUCT_STATUS_AND_COMMERCIAL_READINESS.md):

- **Hardware-validated telemetry:** Validate schema with at least one real device/partner; document “Validated with &lt;vendor&gt;.”
- **One proven actuator path:** Prove one path where WaveOS actions change physical behavior (real or testbed); document or certify.
- **Watchdog/recovery on device:** Wire recovery + watchdog to a real device supervisor; validate reset-reason.
- **Compliance and field drill:** Formalize compliance mapping; run one incident/rollback drill and document.

---

## Quick “what do I do next?” guide

- **“I want to prove it runs in production.”**  
  → Run soak + chaos, fill SOAK_CHAOS_RESULTS.md; use production profile and mTLS/secrets.

- **“I want operators to use rollout and escalation.”**  
  → Wire escalation → lock/approval; add gate check before promote (or doc the flow).

- **“I want to control real hardware.”**  
  → Prioritize real device adapters (≥2) and one proven actuator path.

- **“I want to sell to enterprise/DoD.”**  
  → Harden identity (mTLS, RBAC if needed), complete compliance mapping and one field drill.

Use [IMPLEMENTATION_PRIORITIES.md](IMPLEMENTATION_PRIORITIES.md) for full deliverable text and [PRODUCTION_REMAINING.md](PRODUCTION_REMAINING.md) for detailed remaining wiring.
