# Soak and Failure-Mode Readiness

Production readiness requires validating behavior under sustained load and failure. This doc describes what to validate and how (soak tests, chaos/failure injection).

---

## Scenarios to Validate

| Scenario | What to prove | How |
|----------|----------------|-----|
| **Coordinator restarts while agents continue** | Agents either retry and reconnect, or operate offline-safe (no unsafe actuation). | Restart coordinator mid-run; agents should not apply actions from stale batches; heartbeat retry should succeed after restart. |
| **Network partitions** | Agent does not apply actions when it cannot reach coordinator (if policy is “require coordinator”). Offline-safe mode: apply only safe actions or none. | Simulate partition (firewall, disconnect); verify agent behavior and recovery. |
| **Duplicate joins / ID collisions** | Node registry accepts one join per node_id; duplicate join overwrites or is idempotent; no corruption. | POST /nodes/join twice with same node_id; GET /nodes and fleet status consistent. |
| **Backpressure when runs flood coordinator** | Coordinator does not OOM; rejects or queues with limit; DB/disk bounded. | POST /runs at high rate; monitor memory and response codes. |
| **DB corruption / migration** | Persistence layer handles missing/corrupt DB or schema version; migration path documented. | Remove DB or corrupt a table; run with persistence_enabled; verify error handling or migration. |
| **Time skew between nodes** | Action signing rejects timestamps too far in past/future; heartbeat “last seen” is consistent. | Set agent clock skew; verify signed batch verify fails or heartbeat age is correct. |
| **Rate limits + cooldown under load** | Actuation cooldown and rate limits enforced; no thundering herd. | Trigger many actions; verify cooldown and max_actions_per_minute respected. |

---

## Soak Tests (hours/days)

- **Coordinator:** Run `waveos coordinator serve` with DB; agents send heartbeats and runs every N seconds for 24h+; check memory stable, no crashes, DB size bounded.
- **Agent:** Run `waveos agent --interval 60 --run` for 24h+; verify no leak, watchdog and heartbeat consistent.
- **Pipeline:** Run `waveos run` in a loop (e.g. schedule) for many iterations; verify outputs bounded, no OOM.

Suggested commands:

```bash
# Soak coordinator (run in background, then run agents against it)
waveos coordinator serve --db out/soak/coordinator.db &
# Soak agent (heartbeat + optional run each 60s)
WAVEOS_AGENT_INTERVAL_SEC=60 WAVEOS_COORDINATOR_URL=https://localhost:9100 waveos agent --run
# Soak pipeline (repeated run)
for i in $(seq 1 1000); do waveos run --in demo_data/run --baseline demo_data/baseline --out out/soak/run_$i; done
```

---

## Chaos / Failure Injection

- **Kill coordinator** during agent heartbeat: agent should log failure and retry; no crash.
- **Corrupt SQLite file:** e.g. `echo x >> out/coordinator/coordinator.db`; next request may fail; coordinator should not crash (handle DB errors).
- **Replay old signed batch:** Send same nonce/timestamp again; agent verify should reject (replay).
- **Send invalid signature:** Agent verify should reject.

---

## Scripts

- **scripts/soak_coordinator.sh** (optional): Start coordinator, run N heartbeat clients in loop for M minutes, report success/fail count.
- **scripts/chaos_kill_coordinator.sh** (optional): Start coordinator and one agent; after K seconds kill coordinator; verify agent logs and retries.

---

## Checklist Before Production

- [ ] Soak coordinator + agents for at least 1 hour (or 24h for critical).
- [ ] One chaos run: coordinator kill + agent retry.
- [ ] One run with enforcement_locked_path set: verify no actions applied.
- [ ] One run with signed action batch: verify agent verifies and evidence pack contains verified_by_agent.
- [ ] DB migration tested (add schema version, run persistence).
