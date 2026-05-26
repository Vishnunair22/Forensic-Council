"""
Observability Module
===================

OpenTelemetry distributed tracing setup.

Uses the vendor-neutral OTLP exporter (replaces the deprecated
``opentelemetry-exporter-jaeger`` package which was removed from the
OTel Python distribution in v1.21).  Any OTLP-compatible backend
(Jaeger ≥ 1.35, Grafana Tempo, Honeycomb, …) accepts OTLP natively.

Environment variables (set alongside APP_ENV=production):
  OTEL_EXPORTER_OTLP_ENDPOINT   – http/protobuf collector endpoint
                                   default: http://jaeger:4318
  OTEL_EXPORTER_OTLP_PROTOCOL  – protocol (http/protobuf or grpc)
                                   default: http/protobuf
  OTEL_SERVICE_NAME             – service label in traces
                                   default: forensic-council-api
"""

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment,misc]
    BatchSpanProcessor = None  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]

# Set to True only after setup_observability completes successfully.
# get_tracer returns a NoOp tracer until then so call-sites are safe even
# if they run before lifespan (e.g. module-level tracer = get_tracer()).
_otel_initialized: bool = False


def setup_observability(app, settings) -> None:
    """
    Initialize OpenTelemetry tracing and instrument the FastAPI application.

    No-ops gracefully when:
    - ``opentelemetry-sdk`` / ``opentelemetry-exporter-otlp-proto-grpc``
      are not installed (development mode).
    - Neither ``OTEL_EXPORTER_OTLP_ENDPOINT`` nor ``OTEL_ENABLED=true`` is set
      and the deployment is not production.

    O-H-5: tracing now initializes in any environment where the operator
    has explicitly enabled it (via the OTel endpoint env var or the
    ``OTEL_ENABLED`` flag). Production still initializes by default. Dev,
    staging, and integration test envs gain trace visibility once their
    compose/k8s sets the endpoint — exactly the environments where
    pre-prod regressions surface.
    """
    global _otel_initialized

    if not OTEL_AVAILABLE:
        return

    import os

    explicit_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    explicit_enabled = os.environ.get("OTEL_ENABLED", "").lower() in ("1", "true", "yes")
    if settings.app_env != "production" and not explicit_endpoint and not explicit_enabled:
        return

    endpoint = explicit_endpoint or "http://jaeger:4318"
    service_name = os.environ.get("OTEL_SERVICE_NAME", "forensic-council-api")

    resource = Resource.create({"service.name": service_name})
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Automatically measure every HTTP request
    FastAPIInstrumentor.instrument_app(app)

    _otel_initialized = True


def get_tracer(name: str = "forensic-council"):
    """
    Return an OpenTelemetry tracer instance.

    Returns a no-op tracer when OTel is not installed or setup_observability
    has not been called, so call-sites need no guards.
    """
    if OTEL_AVAILABLE and _otel_initialized:
        return trace.get_tracer(name)
    return _NoOpTracer()


class _NoOpSpan:
    """Minimal no-op span for non-production / missing-OTel environments."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key, value):
        pass

    def add_event(self, name, _attributes=None):
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
