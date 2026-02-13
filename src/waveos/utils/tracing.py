from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

_tracer_initialized = False
_otel_available = False
_trace = None

try:
    from opentelemetry import trace as _trace_module
    _trace = _trace_module
    _otel_available = True
except ModuleNotFoundError:
    pass


class _NoopSpan:
    """No-op span when OpenTelemetry is not installed (e.g. minimal Docker image)."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass


def init_tracer(service_name: str = "waveos", endpoint: Optional[str] = None) -> None:
    global _tracer_initialized
    if _tracer_initialized:
        return
    if not _otel_available:
        _tracer_initialized = True
        return
    endpoint = endpoint or os.getenv("WAVEOS_OTEL_ENDPOINT")
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OTLP tracing is enabled (WAVEOS_OTEL_ENDPOINT is set) but the OTLP exporter is not installed. "
                "Install the tracing extra: pip install -e '.[otel]'"
            ) from exc
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    _trace.set_tracer_provider(provider)
    _tracer_initialized = True


@contextmanager
def span(name: str) -> Iterator[Any]:
    if not _otel_available:
        yield _NoopSpan()
        return
    tracer = _trace.get_tracer("waveos")
    with tracer.start_as_current_span(name) as active_span:
        yield active_span
