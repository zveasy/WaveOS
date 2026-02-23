# Soak and chaos results (evidence artifact)

This document is the **results artifact** for "we operated it": paste or link 4h/24h soak reports and chaos test outcomes here. The tooling writes JSON/MD reports; this page turns them into evidence for production readiness.

---

## 1. Soak report (4h / 24h)

Run the soak runner with `--report` and paste the summary (or link the artifact).

**Commands:**
```bash
# 4h pipeline soak (e.g. 1440 iterations at ~10s each, or lower iterations for shorter run)
python scripts/soak_runner.py pipeline --iterations 500 --in demo_data/run --baseline demo_data/baseline --out out/soak --report out/soak_report_4h.json

# 24h agent soak (run in tmux/screen)
python scripts/soak_runner.py agent --duration 86400 --interval 60 --report out/soak_agent_report_24h.json
```

**Template – fill after run:**

| Metric | 4h soak | 24h soak |
|--------|--------|----------|
| Run count (pipeline) or duration (agent) | | |
| Success count | | |
| Failure count | | |
| Duration (wall clock) | | |
| Recovery behavior (restarts, reconnects) | | |
| Artifact path | `out/soak_report_4h.json` | `out/soak_agent_report_24h.json` |

**Conclusion:** [ ] Soak completed with zero (or acceptable) failures; no OOM; recovery behavior as expected.

---

## 2. Chaos test outcomes

Run chaos scenarios and record outcomes. Reports are appended to `out/chaos_outcomes.json`.

**Commands:**
```bash
# Kill coordinator while agent runs (standalone; starts coordinator and agent)
python scripts/chaos_runner.py --scenario kill_coordinator --report out/chaos_outcomes.json

# Backpressure (coordinator must be running)
WAVEOS_COORDINATOR_URL=http://127.0.0.1:9100 python scripts/chaos_runner.py --scenario backpressure --report out/chaos_outcomes.json

# Duplicate join (coordinator must be running)
WAVEOS_COORDINATOR_URL=http://127.0.0.1:9100 python scripts/chaos_runner.py --scenario duplicate_join --report out/chaos_outcomes.json
```

**Template – fill after runs:**

| Scenario | Outcome | Details |
|----------|---------|---------|
| kill_coordinator | passed / failed / error | Agent retried or exited cleanly; no crash |
| backpressure | passed / degraded / error | success/fail counts; coordinator stable |
| duplicate_join | passed / error | Single or idempotent node record |

**Conclusion:** [ ] Chaos runs completed; coordinator restart and backpressure behavior acceptable.

---

## 3. Sign-off

- **Date:** _______________
- **Operator:** _______________
- **Soak artifact paths:** _______________
- **Chaos artifact path:** `out/chaos_outcomes.json` (or _______________)
- **Notes:** _______________

This evidence supports moving from "we built it" to "we operated it" for production readiness.
