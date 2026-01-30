# API Reference

## CLI

### `waveos sim`
Generate simulated telemetry.
```
waveos sim --out ./demo_data
```

### `waveos baseline`
Build baseline statistics from telemetry.
```
waveos baseline --in ./demo_data/baseline
```

### `waveos run`
Score a run vs baseline and generate reports.
```
waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
```

### `waveos report`
Render HTML report from outputs.
```
waveos report --in ./out --open
```

### `waveos schedule`
Run the pipeline on a fixed interval.
```
waveos schedule --in ./demo_data/run --baseline ./demo_data/baseline --out ./out --every 300 --count 3
```

### `waveos bundle`
Build, install, or rollback a bundle.
```
waveos bundle build --dir ./bundle --policy-version policy-1 --bundle-id bundle-1 --sign
waveos bundle install --dir ./bundle
waveos bundle rollback
```

### `waveos supervise`
Supervise a child process with auto-restart.
```
waveos supervise --max-restarts 3 --backoff 1.0 -- /usr/local/bin/service
```

### `waveos load-test`
Run a normalization load test and emit a JSON report.
```
waveos load-test --out ./out/load --links 200 --samples 200
```

### `waveos profile`
Profile a run with cProfile and save stats.
```
waveos profile --in ./demo_data/run --baseline ./demo_data/baseline --out ./out --profile ./out/profile.pstats
```

### `waveos cleanup`
Purge old outputs/logs.
```
waveos cleanup --path ./out --days 7
```

### `waveos proxy-serve`
Run the proxy server only (keeps it alive).
```
WAVEOS_PROXY_ENABLED=true WAVEOS_PROXY_MODE=http_forward waveos proxy-serve
```

### `waveos metrics-serve`
Run the metrics server only (keeps it alive).
```
WAVEOS_METRICS_PORT=9109 waveos metrics-serve
```

### `waveos serve`
Run metrics + proxy servers together.
```
WAVEOS_METRICS_PORT=9109 WAVEOS_PROXY_ENABLED=true WAVEOS_PROXY_MODE=http_forward waveos serve
```

### `waveos validate-telemetry`
Validate telemetry records against a profile (microgrid or EV charger).
```
waveos validate-telemetry --in ./out/demo/run/telemetry.jsonl --profile microgrid --out ./out/validation.json
```

### CLI Auth
```
waveos --role operator --token <token> run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
```

## Outputs
- `health_summary.json`
- `events.jsonl`
- `actions.json`
- `run_meta.json`
- `metrics.csv`
- `recovery_actions.jsonl` (if recovery enabled)
- `enforced_actions.jsonl` (if enforcement enabled)
- `evidence_pack_<run_id>.zip` (if enabled)
- `explainability.json`
- `report.html`

## Models (Pydantic)

### Telemetry
- `TelemetrySample`: normalized telemetry record
- `Link`, `Port`, `Path`, `Workload`

### Scoring
- `HealthScore`: PASS/WARN/FAIL with drivers
- `BaselineStats`, `RunStats`

### Policy and Events
- `ActionRecommendation`: advisory action
- `Event`: timeline event with level and details
