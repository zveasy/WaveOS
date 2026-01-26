# Wave OS Architecture

## Purpose
Wave OS is a vendor-neutral Optical OS / Network Brain that transforms optical links and photonic fabrics from passive transport into adaptive, self-healing, energy-aware systems. V1 delivers a local demo pipeline that ingests telemetry, scores health, detects drift, reasons about actions, and produces reports.

## Goals (V1)
- Local end-to-end demo with simulated baseline vs run telemetry.
- Health + drift detection with PASS/WARN/FAIL classifications.
- Policy engine that produces advisory actions.
- Closed-loop simulation with fault injection.
- Human- and machine-readable reporting.

## Non-Goals (V1)
- Real device control (actuator is mocked).
- Real-time streaming; file-based ingestion only.
- Vendor-specific telemetry adapters beyond normalized inputs.

## High-Level Flow
collectors → normalize → score → policy → actuator → report

## Key Components
- collectors: File-based ingestion (CSV/JSON). gNMI/OpenConfig stubs for future.
- normalize: Map raw input to a canonical schema with validation.
- models: Strongly-typed Pydantic models for Link, Port, Path, Workload, TelemetrySample, HealthScore, Event.
- scoring: Baseline vs run comparison, drift detection, classification, top drivers.
- policy: Reasoning engine that outputs advisory actions based on health, drift, and constraints.
- actuators: NoopActuator and MockActuator for logging intended actions.
- reporting: JSON summaries, JSONL event timeline, HTML report (Jinja2).
- sim: Telemetry generation, fault injection, and closed-loop demo harness.
- utils: Logging, time windows, helpers.

## Data Contracts
Core entities are modeled with Pydantic and validated at boundaries. The normalized telemetry model is the single source of truth for the pipeline.

## Telemetry Inputs
- Errors, drops, retries
- FEC corrected / uncorrected counts
- BER proxies
- DOM/DDM optics metrics (tx/rx power, temperature) when available

## Outputs
- health_summary.json
- events.jsonl
- report.html

## Observability
Logging includes timestamps and component names. Rich CLI output provides a concise run summary.

## Demo CLI
- waveos sim --out ./demo_data
- waveos baseline --in ./demo_data/baseline
- waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
- waveos report --in ./out --open

## Repo Layout
- /src/waveos: Core modules
- /bin: CLI entrypoints/scripts
- /docs: Architecture and guides
- /tests: Unit tests
- docker-compose.yml: Local demo runtime
- Makefile: Convenience targets
- README.md: Quickstart
