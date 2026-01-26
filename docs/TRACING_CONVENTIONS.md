# Tracing Conventions

## Scope
Wave OS spans capture the reasoning pipeline so decisions can be audited and debugged.

## Span Names
- `normalize_records`: normalize raw telemetry into canonical samples
- `score_links`: compute baseline vs run health scores
- `policy_recommendations`: produce advisory actions
- `report_render`: generate HTML and JSON outputs

## Attributes
- `waveos.entity_type`: link|port|path|workload
- `waveos.entity_id`: entity identifier
- `waveos.sample_count`: number of telemetry samples
- `waveos.status`: PASS|WARN|FAIL
- `waveos.driver_count`: number of contributing drivers
- `waveos.action_count`: number of policy actions

## Correlation IDs
- `waveos.run_id`: UUID or timestamp-based run identifier
- `waveos.baseline_id`: baseline dataset identifier

## Error Semantics
- Record exceptions on spans when normalization or scoring fails.
- Emit WARN on partial data, ERROR on missing baseline.
