# Quick Start for Evaluators

Get from zero to a first WaveOS report in a few minutes (evaluation / trial use).

## Prerequisites

- Python 3.11+
- License: set `WAVEOS_LICENSE_KEY` (trial key from your contact) or `WAVEOS_LICENSE_SKIP=1` for local dev only.

## 1. Install

```bash
pip install waveos
# or from repo:
# pip install -e .
```

## 2. Set license (if required)

```bash
export WAVEOS_LICENSE_KEY="WAVEOS-EVAL-20261231"   # replace with your trial key
# For local dev only: export WAVEOS_LICENSE_SKIP=1
```

## 3. Generate demo data and run pipeline

```bash
# Generate simulated telemetry (creates demo_data/baseline and demo_data/run)
waveos sim --out ./demo_data

# Build baseline stats from the baseline folder
waveos baseline --in ./demo_data/baseline

# Run scoring + policy
waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out

# Open the report
waveos report --in ./out --open
```

You should see an HTML report with health scores, events, and recommended actions.

## 4. Health check (optional)

```bash
waveos health-check
waveos validate-config
```

Exit 0 means ready for use.

## 5. Next steps

- **Config:** Copy `docs/config/microgrid.toml` or `docs/config/ev_charger.toml` and set `WAVEOS_CONFIG` to point to it.
- **Production:** See [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) and [DEPLOYMENT.md](DEPLOYMENT.md).
- **Licensing:** Contact licensing@omniandluci.com for trial or commercial keys.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| License error | Set `WAVEOS_LICENSE_KEY` or `WAVEOS_LICENSE_PATH`; for dev use `WAVEOS_LICENSE_SKIP=1`. |
| Missing baseline | Run `waveos baseline` before `waveos run`. |
| No report | Ensure `waveos run` completed (exit 0); then `waveos report --in <out_dir>`. |
| Exit codes | 0 = success, 1 = usage/input, 2 = config, 3 = license. See [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md#exit-codes-automation). |
