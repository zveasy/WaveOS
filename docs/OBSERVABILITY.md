# Observability

## Metrics (Prometheus)
- Enable with `WAVEOS_METRICS_PORT=9109`.
- Example scrape config:
  ```yaml
  scrape_configs:
    - job_name: waveos
      static_configs:
        - targets: ["localhost:9109"]
  ```

## Tracing (OpenTelemetry)
- Set `WAVEOS_OTEL_ENDPOINT` to your OTLP HTTP endpoint.
- Example: `http://localhost:4318/v1/traces`
- Spans: `normalize_records`, `score_links`

## Dashboards
- Grafana dashboard template: `docs/observability/grafana-dashboard.json`

## Proxy Quick Test
- Run `bin/proxy_demo.sh` to start metrics + proxy, send a request, and print proxy metrics.

## Perf (CI Artifacts)
- CI uploads `perf-artifacts` containing:
  - `out/load/load_test.json`
  - `out/profile.pstats`
  - `out/profile_run/**` (report, run_meta, metrics.csv)
- Download in GitHub Actions: open the `perf` job → Artifacts → `perf-artifacts`.

## Dashboard Validation (Real Runs)
1. Generate demo data:
   - `waveos sim --out out/observability`
2. Build a baseline and run with metrics enabled:
   - `WAVEOS_METRICS_PORT=9109 waveos baseline --in out/observability/baseline`
   - `WAVEOS_METRICS_PORT=9109 waveos run --in out/observability/run --baseline out/observability/baseline --out out/observability/report`
3. While a run is executing, verify metrics are exposed:
   - `curl http://localhost:9109/metrics | rg "waveos_(telemetry_ingested|normalize_errors|normalize_duration|scoring_duration)"`
4. Import the Grafana dashboard JSON and confirm panels populate for:
   - Telemetry ingested
   - Normalize errors
   - Normalize duration p95
   - Scoring duration p95
   - Proxy connections (if proxy enabled)
   - Proxy bytes (if proxy enabled)
