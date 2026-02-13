# Operator Guide

## Running the Pipeline
1. Generate demo data:
   - `waveos sim --out ./demo_data`
2. Build baseline:
   - `waveos baseline --in ./demo_data/baseline`
3. Run scoring:
   - `waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out`

## Outputs
- `health_summary.json`, `events.jsonl`, `actions.json`, `run_meta.json`, `metrics.csv`, `report.html`
- Evidence pack: `evidence_pack_<run_id>.zip` (if enabled)

## Exit codes (automation)
| Code | Meaning |
|------|--------|
| 0 | Success |
| 1 | Usage or input error (e.g. missing baseline) |
| 2 | Configuration error |
| 3 | License or authorization error |

See [Production Checklist](PRODUCTION_CHECKLIST.md) for go-live steps.

## Troubleshooting
- Check `out/audit.jsonl` for access decisions.
- Check `out/spool.log` for log spool output.
- Enable debug logging: `WAVEOS_LOG_LEVEL=DEBUG`.
- Verify license and config: `waveos health-check`.
