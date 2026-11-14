"""Inicialização OpenTelemetry para microsserviços Flask do ToggleMaster.

A telemetria fica desligada no desenvolvimento local quando não há endpoint OTLP.
Em produção os três sinais são enviados ao OpenTelemetry Collector via HTTP/protobuf.
"""

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

_INITIALIZED = False


def initialize_telemetry(service_name, *, database=False, http_client=False, aws=False):
    """Instala exporters e instrumentação antes da criação dos clientes externos."""
    global _INITIALIZED
    if _INITIALIZED or os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        return
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return

    sampling_ratio = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))
    if not 0.0 <= sampling_ratio <= 1.0:
        raise ValueError("OTEL_TRACES_SAMPLER_ARG deve estar entre 0 e 1")

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", service_name),
            "service.namespace": "toggle-master",
        }
    )

    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(sampling_ratio)),
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(),
        export_interval_millis=30000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    # Preserva os logs no stdout e adiciona OTLP ao logger raiz.
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    # Evita reexportar logs internos dos exporters, prevenindo realimentação.
    handler.addFilter(lambda record: not record.name.startswith("opentelemetry"))
    logging.getLogger().addHandler(handler)

    # Instrumenta antes da primeira conexão HTTP/SQL ou cliente AWS.
    if database:
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

        Psycopg2Instrumentor().instrument()
    if http_client:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
    if aws:
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

        BotocoreInstrumentor().instrument()
    _INITIALIZED = True


def instrument_flask(app):
    """Instrumenta tráfego de negócios, excluindo probes Kubernetes."""
    if _INITIALIZED:
        FlaskInstrumentor().instrument_app(app, excluded_urls="/health")
