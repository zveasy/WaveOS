# SLOs and SLIs

## SLIs
- Pipeline success rate: % of runs producing reports without error.
- Processing latency: time from ingestion to report output.
- Scoring accuracy proxy: % of runs with expected PASS/WARN/FAIL classification in test fixtures.

## SLOs
- Success rate: 99% of runs produce outputs without failure.
- Latency: 95% of demo runs complete under 60 seconds.
- Accuracy proxy: 95% of regression tests match expected outputs.

## Measurement
- Emit metrics via Prometheus.
- Track latency histograms for normalization and scoring.
