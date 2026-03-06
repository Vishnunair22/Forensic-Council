
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    TracerProvider = None
    BatchSpanProcessor = None
    JaegerExporter = None
    FastAPIInstrumentor = None


def setup_observability(app, settings):
    """
    Initialize OpenTelemetry tracing setup dynamically if telemetry flag matches.
    Instrument the FastAPI app router seamlessly.
    """
    if not OTEL_AVAILABLE:
        # OpenTelemetry not available, skip observability setup
        return
    
    if settings.app_env == "production":
        jaeger_exporter = JaegerExporter(
            agent_host_name="jaeger",
            agent_port=6831,
        )
        provider = TracerProvider()
        processor = BatchSpanProcessor(jaeger_exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        # Attach the middleware hook automatically measuring requests
        FastAPIInstrumentor.instrument_app(app)
