"""OpenTelemetry tracing configuration."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from sfir_backend.config.settings import Settings


def configure_tracing(settings: Settings) -> None:
    if not settings.otlp_endpoint:
        return

    resource = Resource.create(
        attributes={
            "service.name": settings.otlp_service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otlp_endpoint,
        insecure=True,
        timeout=10,
    )

    processor = BatchSpanProcessor(
        exporter,
        max_export_batch_size=512,
        max_queue_size=2048,
        schedule_delay_millis=5000,
    )

    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(app)


def instrument_httpx() -> None:
    HTTPXClientInstrumentor().instrument()


def instrument_sqlalchemy(engine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
