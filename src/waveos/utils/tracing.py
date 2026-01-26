from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer_initialized = False


def init_tracer(service_name: str = "waveos", endpoint: Optional[str] = None) -> None:
    global _tracer_initialized
    if _tracer_initialized:
        return
    endpoint = endpoint or os.getenv("WAVEOS_OTEL_ENDPOINT")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer_initialized = True


@contextmanager
def span(name: str) -> Iterator[trace.Span]:
    tracer = trace.get_tracer("waveos")
    with tracer.start_as_current_span(name) as active_span:
        yield active_span
