from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_observability(app, settings):
    """
    Initialize OpenTelemetry tracing setup dynamically if telemetry flag matches.
    Instrument the FastAPI app router seamlessly.
    """
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
