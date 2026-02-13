# Run WaveOS on Your Computer

Get WaveOS running locally and see the report in a few minutes.

## 1. Install

```bash
cd /path/to/WaveOS
pip install -e .
# Or install from PyPI (when published): pip install waveos
```

Requires **Python 3.11+**.

## 2. License (so the CLI runs)

For local use, either skip the license check or use a test key:

```bash
export WAVEOS_LICENSE_SKIP=1
# Or: export WAVEOS_LICENSE_KEY="WAVEOS-EVAL-20991231"
```

## 3. Run the pipeline (see it work)

These four commands generate demo telemetry, build a baseline, run scoring and policy, and open the HTML report.

```bash
# 1) Generate demo data (creates demo_data/baseline and demo_data/run)
waveos sim --out ./demo_data

# 2) Build baseline stats from the baseline folder
waveos baseline --in ./demo_data/baseline

# 3) Run scoring + policy (compare run data to baseline, write outputs to ./out)
waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out

# 4) Open the report in your browser
waveos report --in ./out --open
```

You should see:

- **Terminal:** Summary of health scores and events.
- **Browser:** An HTML report with link health, events timeline, and recommended actions (the “control plane” making decisions).

## 4. Sanity checks (optional)

```bash
waveos health-check
waveos validate-config
waveos -V
```

Exit 0 and a version string mean the install is good.

## 5. What you’re seeing

- **sim** — Simulates optical/network telemetry (errors, drops, power, etc.) with some “drift” so the run looks different from the baseline.
- **baseline** — Computes normal stats from the baseline data.
- **run** — Compares run telemetry to the baseline, scores health (PASS/WARN/FAIL), runs the policy engine, and produces recommended actions and events.
- **report** — Renders the HTML report and optional evidence pack.

WaveOS is a **control-plane OS** for networks and energy (optical links, microgrids, EV chargers). It doesn’t drive GPUs today; see below.

---

## GPU and “make GPUs go faster”

**WaveOS in this repo does not currently control or accelerate GPUs.** It is built for:

- Optical and network telemetry
- Microgrid / EV charger / energy scheduling
- Policy and health scoring for those domains

So **on your computer it will run and show the report**, but it will **not** make your GPU go faster.

There is a **future “WaveOS Compute Edition”** idea in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) (GPU benchmark track: scheduling, utilization, throughput). That is **not implemented** in this codebase. To get **GPU speedups** you would need either:

- That future compute edition (when/if built), or
- Your own integration: e.g. treat GPUs as “devices,” send telemetry (utilization, temp) into WaveOS, and write an actuator that applies policy (e.g. power cap, fan curve) via vendor APIs or drivers.

**Summary:** You can deploy and see WaveOS work on your machine with the steps above; making GPUs go faster would require a separate, not-yet-shipped compute track or custom GPU integration.
