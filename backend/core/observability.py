"""
Observability Module
====================

OpenTelemetry distributed tracing setup.

Uses the vendor-neutral OTLP exporter (replaces the deprecated
``opentelemetry-exporter-jaeger`` package which was removed from the
OTel Python distribution in v1.21).  Any OTLP-compatible backend
(Jaeger ≥ 1.35, Grafana Tempo, Honeycomb, …) accepts OTLP natively.

Environment variables (set alongside APP_ENV=production):
  OTEL_EXPORTER_OTLP_ENDPOINT   – gRPC collector endpoint
                                   default: http://otel-collector:4317
  OTEL_SERVICE_NAME             – service label in traces
                                   default: forensic-council-api
"""

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment,misc]
    BatchSpanProcessor = None  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]


def setup_observability(app, settings) -> None:
    """
    Initialise OpenTelemetry tracing and instrument the FastAPI application.

    No-ops gracefully when:
    - ``opentelemetry-sdk`` / ``opentelemetry-exporter-otlp-proto-grpc``
      are not installed (development mode).
    - ``APP_ENV`` is not ``production``.
    """
    if not OTEL_AVAILABLE:
        return

    if settings.app_env != "production":
        return

    import os

    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"
    )
    service_name = os.environ.get("OTEL_SERVICE_NAME", "forensic-council-api")

    resource = Resource.create({"service.name": service_name})
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Automatically measure every HTTP request
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = "forensic-council"):
    """
    Return an OpenTelemetry tracer instance.

    When OTel is not available or not in production, returns a no-op tracer
    so call-sites can use ``tracer.start_as_current_span()`` without
    guarding every invocation.
    """
    if OTEL_AVAILABLE:
        return trace.get_tracer(name)
    # No-op tracer — all spans are silently discarded
    return trace.get_tracer(name) if OTEL_AVAILABLE else _NoOpTracer()


class _NoOpSpan:
    """Minimal no-op span for non-production / missing-OTel environments."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def set_attribute(self, key, value):
        pass
    def add_event(self, name, attributes=None):
        pass
    def set_status(self, status):
        pass
    def end(self):
        pass


class _NoOpTracer:
    """Minimal no-op tracer that returns no-op spans."""
    def start_span(self, name, **kwargs):
        return _NoOpSpan()
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()
