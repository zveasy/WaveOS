# How to test if WaveOS works

Three levels: **automated tests**, **CLI smoke test**, and **soak/chaos**. Plus **what to verify** so you know it actually did what it should.

---

## What WaveOS is supposed to do (and how to verify)

For a single run, WaveOS is supposed to:

| Step | What it does | How you know it worked |
|------|----------------|-------------------------|
| **sim** | Generates demo baseline + run telemetry under the output dir. | `out/demo_data/baseline/` and `out/demo_data/run/` exist; both contain JSON/JSONL. |
| **baseline** | Builds baseline stats (e.g. baseline.json) from the baseline data. | `baseline/baseline.json` exists; no error. |
| **run** | Loads run telemetry, compares to baseline, scores health, recommends actions, writes outputs. | `out/run/health_summary.json` has entities with `status` (PASS/WARN/FAIL) and `score`; `events.jsonl` has log lines; `actions.json` has recommended actions. |
| **report** | Renders the run into a human-readable report. | `out/run/report.html` exists and opens in a browser with the health table and run ID. |

So “it runs and does what it needs to do” means: the pipeline completes, and the outputs contain **real content** (scores, statuses, events, actions), not just empty files.

**Quick content checks after a run** (e.g. after `bash scripts/smoke_test.sh`):

```bash
# 1. Health summary has entities and statuses
python3 -c "
import json
from pathlib import Path
p = Path('out/smoke_run/health_summary.json')
d = json.loads(p.read_text())
assert d, 'health_summary should not be empty'
for e in (d if isinstance(d, list) else d.get('entities', d)):
    assert 'entity_id' in e and 'status' in e, f'entity should have entity_id and status: {e}'
print('OK: health_summary has entities with status')
"

# 2. Events were emitted
test -f out/smoke_run/events.jsonl && test -s out/smoke_run/events.jsonl && echo "OK: events.jsonl has content"

# 3. Report exists and is non-trivial
test -f out/smoke_run/report.html && test -s out/smoke_run/report.html && echo "OK: report.html exists and non-empty"
```

Or run the smoke script with verification (see below): `bash scripts/smoke_test.sh --verify`.

---

## 1. Automated test suite

From the repo root (with `.venv` active or `src` on `PYTHONPATH` via `conftest`):

```bash
# All tests
python -m pytest tests/ -q

# With coverage
python -m pytest tests/ -q --cov=src/waveos --cov-report=term-missing

# Key areas
python -m pytest tests/test_pipeline_integration.py tests/test_cli_e2e.py tests/test_production_profile_and_soak_chaos.py tests/test_v1_acceptance.py -v
```

**Note:** `test_cli_e2e` runs the `waveos` CLI (sim → baseline → run → report). It requires the package to be installed so the `waveos` command exists:

```bash
pip install -e .
python -m pytest tests/test_cli_e2e.py -v
```

---

## 2. CLI smoke test (manual)

Install and run a minimal pipeline end-to-end:

```bash
# Install so the `waveos` command is available
pip install -e .

# Generate demo data
waveos sim --out out/demo_data

# Build baseline from demo baseline dir
waveos baseline --in out/demo_data/baseline

# Run pipeline: run dir, baseline dir, output dir
waveos run --in out/demo_data/run --baseline out/demo_data/baseline --out out/run

# Generate report from run output
waveos report --in out/run

# Sanity checks
ls out/run/health_summary.json out/run/events.jsonl out/run/report.html
waveos validate-config
waveos health-check
```

If all commands succeed and the listed files exist, the core pipeline works.

**With production profile:**

```bash
waveos --config configs/production.toml validate-config
waveos --config configs/production.toml run --in out/demo_data/run --baseline out/demo_data/baseline --out out/run_prod
```

---

## 3. Soak and chaos (evidence / regression)

- **Soak:** Run the pipeline or agent many times and collect a report (run counts, duration, failures).
- **Chaos:** Run failure scenarios (e.g. kill coordinator, backpressure) and record outcomes.

```bash
# Soak: 10 pipeline runs, write report
python scripts/soak_runner.py pipeline --iterations 10 --in out/demo_data/run --baseline out/demo_data/baseline --out out/soak --report out/soak_report.json

# Chaos: list scenarios, then run one (e.g. kill_coordinator)
python scripts/chaos_runner.py --list
python scripts/chaos_runner.py --scenario kill_coordinator --report out/chaos_outcomes.json
```

See [SOAK_CHAOS_RESULTS.md](SOAK_CHAOS_RESULTS.md) for 4h/24h and chaos evidence templates.

---

## Quick “does it work?” checklist

| Step | Command | Pass condition |
|------|---------|-----------------|
| 1. Unit/integration tests | `python -m pytest tests/ -q` | All pass (or only expected skips). |
| 2. Config | `waveos validate-config` | Exit 0 (requires `pip install -e .`). |
| 3. Pipeline e2e | `bash scripts/smoke_test.sh` (or sim → baseline → run → report by hand) | No errors; `out/smoke_run/health_summary.json` and `report.html` exist. |
| 3b. Content verify | `bash scripts/smoke_test.sh --verify` (run after a smoke run) | Same as 3, plus checks: events.jsonl has lines, health_summary has entity/status/score, report.html non-empty. |
| 4. Production config | `waveos --config configs/production.toml validate-config` | Exit 0. |
| 5. Soak/chaos (optional) | `scripts/soak_runner.py` and `scripts/chaos_runner.py` | Reports written; no crashes. |
