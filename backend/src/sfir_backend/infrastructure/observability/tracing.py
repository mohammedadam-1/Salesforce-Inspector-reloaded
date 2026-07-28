from __future__ import annotations

from typing import Any
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from sfir_backend.config.settings import Settings
from sfir_backend.domain.observability.models import TraceSpan


def _create_otlp_exporter(endpoint: str) -> Any:
    """Lazy import of OTLP exporter to avoid gRPC import hangs."""
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    return OTLPSpanExporter(endpoint=endpoint)


def configure_tracing(settings: Settings) -> trace.Tracer:
    """Configure OpenTelemetry tracing."""
    if not settings.tracing_enabled:
        return trace.get_tracer(__name__)

    resource = Resource.create({
        "service.name": settings.otlp_service_name,
        "environment": settings.environment,
    })

    provider = TracerProvider(resource=resource)

    if settings.otlp_endpoint:
        exporter = _create_otlp_exporter(settings.otlp_endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)
    return trace.get_tracer(__name__)


class TracingManager:
    def __init__(self, tracer: trace.Tracer | None = None) -> None:
        self._tracer = tracer or trace.get_tracer(__name__)

    @property
    def tracer(self) -> trace.Tracer:
        return self._tracer

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        parent_span: trace.Span | None = None,
    ) -> trace.Span:
        if parent_span:
            ctx = trace.set_span_in_context(parent_span)
            return self._tracer.start_span(name, context=ctx, attributes=attributes)
        return self._tracer.start_span(name, attributes=attributes)

    def current_span(self) -> trace.Span | None:
        span = trace.get_current_span()
        if span and span.is_recording():
            return span
        return None

    def add_event(
        self, span: trace.Span, name: str, attributes: dict[str, Any] | None = None,
    ) -> None:
        span.add_event(name, attributes or {})

    def set_attribute(self, span: trace.Span, key: str, value: Any) -> None:
        span.set_attribute(key, value)

    def record_exception(self, span: trace.Span, exception: Exception) -> None:
        span.record_exception(exception)

    def to_trace_span(self, span: trace.Span) -> TraceSpan:
        ctx = span.get_span_context()
        return TraceSpan(
            span_id=format(ctx.span_id, "x"),
            trace_id=format(ctx.trace_id, "x"),
            name=span.get_attribute("name") or span.get_span_context().span_id,
        )

    def generate_trace_id(self) -> str:
        return str(uuid4())

    def generate_span_id(self) -> str:
        return str(uuid4())
