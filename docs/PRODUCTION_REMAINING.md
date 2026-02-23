# What Is Still Not Done (Full Production WaveOS OS)

This document tracks remaining work to reach the “full production WaveOS OS” and fleet-grade operations. It complements [IMPLEMENTATION_PRIORITIES.md](IMPLEMENTATION_PRIORITIES.md).

---

## A) Coordinator v1 — Implemented ✅

The coordinator is no longer a stub. Implemented in `waveos.coordinator`:

- **Node registry:** `POST /nodes/join`, `DELETE /nodes/<id>`, `GET /nodes` (join/leave, metadata, capabilities)
- **Heartbeat ingestion:** `POST /heartbeat`; online/offline via `last_seen_at` and `GET /fleet/status`
- **Policy distribution:** `POST /policy`, `GET /policy/<version>`, `GET /policy` (versioned)
- **Run ingestion:** `POST /runs` (run_id, node_id, summary, policy_version)
- **Central fleet status API:** `GET /fleet/status?max_age_seconds=120`
- **AuthN for agents:** Optional `WAVEOS_COORDINATOR_AGENT_TOKEN` (Bearer); mTLS on coordinator via `--tls` / env

**Remaining for “fleet OS” at scale:** Action signing (coordinator signs, agent verifies), optional OIDC/JWT for short-lived machine identity.

---

## B) Desired-State Reconciliation — Implemented ✅

In `waveos.desired_state`:

- **Desired state model:** `DesiredStateRecord` per site/device; `set_desired`, `get_desired`, `list_desired`
- **Reconcile loop:** `reconcile_one`, `reconcile_loop(actual_lookup, entity_type, strategy)`
- **Drift strategy:** `APPLY`, `ALERT_ONLY`, `FALLBACK_SAFE`

**Remaining:** Persist desired state in DB; wire reconcile loop to scheduler or agent cycle; plug in real `actual_lookup` from runs/telemetry.

---

## C) Rollouts at Scale — Implemented ✅

In `waveos.coordinator.rollout`:

- **Staged rollout:** `RolloutSpec` with `canary_percent`, `canary_site_ids`; `select_canary_nodes()`
- **Promotion gates:** `promotion_gate_passed(canary_node_ids, healthy_node_ids, run_ok_count_by_node, spec)`
- **Rollback:** `rollback_reason()` when canary nodes unhealthy or exceed failure threshold

**Remaining:** Wire to coordinator API (e.g. `POST /rollout`, `POST /rollout/<id>/promote`, `POST /rollout/<id>/rollback`) and to persistence (deployments table).

---

## D) Persistence — Implemented ✅

DB coverage in `waveos.persistence.store`:

- **Runs:** `runs`, `run_events`, `run_actions`, `run_scores` (already present)
- **Scores:** In `run_scores`
- **Events:** In `run_events`
- **Incidents:** In `incidents` (with lifecycle columns: status, closed_at, escalated_at, escalation_reason, postmortem_path)
- **Deployments:** `deployments` table; `save_deployment`, `list_deployments`
- **Policy versions applied:** `policy_versions_applied`; `save_policy_version_applied`, `get_policy_versions_applied`
- **Action transactions:** Already present

**Remaining:** Ensure all run/incident paths write through persistence when enabled; optional archival/retention for deployments.

---

## E) Incident Lifecycle — Implemented ✅

In `waveos.incident_lifecycle`:

- **Open/close:** `incident_create`, `incident_close`; status open → escalated → closed
- **Timeline:** Part of incident record (events + actions + outcomes)
- **Escalation:** `incident_escalate(reason, notify_operator, require_approval, lock_enforcement)`
- **Postmortem pack:** `build_postmortem_pack(incident, output_dir, include_artifacts)` (zip)

**Remaining:** Wire escalation to alerting (notify operator); enforce “require approval” and “lock enforcement” in run path; persist incident status updates in DB.

---

## F) Security Posture — Documented

See [SECURITY_PRODUCTION.md](SECURITY_PRODUCTION.md):

- **mTLS:** Coordinator TLS and agent→coordinator HTTPS (and optional client certs) — configurable, not default
- **Short-lived identity:** OIDC/JWT or cert-based — planned, not implemented
- **Secret provider required in prod:** Enforced when not `WAVEOS_LICENSE_SKIP`; `strict_secrets` disables JSON fallback
- **Action signing:** Coordinator signs, agent verifies — not yet implemented

---

## G) Secrets Tests — Fixed ✅

- Vault/AWS/GCP secrets tests now run with `WAVEOS_LICENSE_SKIP=1` (parametrized) so JSON fallback is allowed in tests.
- Documented in test file: production does not use JSON fallback; integration tests with real credentials are separate.

---

## Summary

| Area | Status | Notes |
|------|--------|--------|
| A) Coordinator v1 | ✅ | Node registry, heartbeats, policy, runs, fleet status, Bearer auth |
| B) Desired-state reconciliation | ✅ | Model, reconcile loop, drift strategy |
| C) Rollouts at scale | ✅ | Canary selection, promotion gates, rollback reason |
| D) Persistence | ✅ | Runs, scores, events, incidents, deployments, policy_versions_applied |
| E) Incident lifecycle | ✅ | Open/close, escalate, postmortem pack |
| F) Security | Documented | mTLS/auth/secrets/action-signing in SECURITY_PRODUCTION.md |
| G) Secrets tests | ✅ | Passing; gated by LICENSE_SKIP for JSON fallback |

**Still to do for “full production”:** Action signing (coordinator→agent), OIDC/JWT or cert-based short-lived identity, wiring rollout API and incident escalation into run path and alerting.
