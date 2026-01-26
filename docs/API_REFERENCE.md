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

## Outputs
- `health_summary.json`
- `events.jsonl`
- `actions.json`
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
