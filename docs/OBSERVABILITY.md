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
