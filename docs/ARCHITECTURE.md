# Wave OS Architecture

## Purpose

Wave OS is a **control-plane OS** for embedded and industrial systems: a DoD/industrial-grade distributed operating system that sits above hardware, firmware, and network infrastructure and makes everything behave as one controlled, upgradeable, secure platform. It is not a dashboard or monitoring tool—it is the layer that reasons, orchestrates, and (in later phases) controls.

V1 delivers the kernel of that vision: a vendor-neutral pipeline that ingests telemetry, normalizes across vendors, scores health, detects drift, reasons about actions via a policy engine, and produces reports—plus signed bundles, RBAC, audit, recovery, and observability. The full 15-capability production target and v1/v2/v3 milestones are in [PRD_DOD_REQUIREMENTS.md](PRD_DOD_REQUIREMENTS.md); implementation status is in [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md).

## Production vision: compatibility layer + single control plane

- **Universal compatibility layer:** Translation and interoperability across mixed VxWorks/Linux versions, legacy and modern drivers, and vendor protocols (ABB, Siemens, Eaton, etc.) so old and new systems coexist without full rewrites. Current code: vendor-neutral normalization, schema versioning, config/identity abstraction; v2/v3 add protocol adapters and runtime translation.
- **Single control plane:** Orchestration across edge, embedded, microgrid controllers, cloud, and air-gapped DoD networks. Current code: single-node local-first pipeline; v2/v3 add multi-node coordination and federated control.
- **Standard device API:** One interface for charger, inverter, BESS, microgrid islanding, telemetry, and relays regardless of vendor. Current code: normalized telemetry and actuator interface (advisory/mock); v2/v3 add real device adapters and plug-and-play.

The components below are the building blocks of this control-plane OS.

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
