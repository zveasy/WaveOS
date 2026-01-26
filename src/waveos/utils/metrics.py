from __future__ import annotations

import os
from typing import Optional

from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server

_registry: Optional[CollectorRegistry] = None
_started = False
_counters: Optional[dict[str, Counter]] = None
_histograms: Optional[dict[str, Histogram]] = None


def init_registry() -> CollectorRegistry:
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry


def start_metrics_server(port: int | None = None) -> None:
    global _started
    if _started:
        return
    port = port or (int(os.getenv("WAVEOS_METRICS_PORT")) if os.getenv("WAVEOS_METRICS_PORT") else None)
    if not port:
        return
    registry = init_registry()
    start_http_server(int(port), registry=registry)
    _started = True


def counters() -> dict[str, Counter]:
    global _counters
    if _counters is not None:
        return _counters
    registry = init_registry()
    _counters = {
        "telemetry_ingested": Counter(
            "waveos_telemetry_ingested_total",
            "Total telemetry samples ingested",
            registry=registry,
        ),
        "normalize_errors": Counter(
            "waveos_normalize_errors_total",
            "Total normalization errors",
            registry=registry,
        ),
    }
    return _counters


def histograms() -> dict[str, Histogram]:
    global _histograms
    if _histograms is not None:
        return _histograms
    registry = init_registry()
    _histograms = {
        "normalize_duration": Histogram(
            "waveos_normalize_duration_seconds",
            "Time spent normalizing telemetry",
            registry=registry,
        ),
        "scoring_duration": Histogram(
            "waveos_scoring_duration_seconds",
            "Time spent scoring telemetry",
            registry=registry,
        ),
    }
    return _histograms
