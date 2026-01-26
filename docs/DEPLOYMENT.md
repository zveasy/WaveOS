# Deployment Guide

## Local
1) Install dependencies: `pip install -e .`
2) Generate demo data: `waveos sim --out ./demo_data`
3) Build baseline: `waveos baseline --in ./demo_data/baseline`
4) Run analysis: `waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out`
5) Render report: `waveos report --in ./out --open`

## Container (Local)
Use `docker-compose.yml` for a local container runtime. Mounts the repo and runs a placeholder command.

## Configuration
- `WAVEOS_LOG_FORMAT=json|text` (default: json)
- `WAVEOS_LOG_LEVEL=INFO|DEBUG|...`
- `WAVEOS_METRICS_PORT=9109` to enable Prometheus metrics endpoint
