from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

import pyroscope
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.resource.detector.containerid import ContainerResourceDetector
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import DropAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.attributes.deployment_attributes import DEPLOYMENT_ENVIRONMENT_NAME
from opentelemetry.semconv.attributes.service_attributes import SERVICE_INSTANCE_ID, SERVICE_NAME
from pyroscope.otel import PyroscopeSpanProcessor

from observability._logs import logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opentelemetry.semconv.attributes.deployment_attributes import DeploymentEnvironmentNameValues

_EXPORT_EVERY_MILLISECONDS: Final = 15_000
_EXPORT_TIMEOUT_SECONDS: Final = 10.0
_PROFILE_SAMPLES_PER_SECOND: Final = 100
_PROFILE_UPLOAD_EVERY_SECONDS: Final = 10

# Requests served and the process serving them; whatever else is instrumented records into nothing.
_SHIPPED_METRICS: Final = ("http.server.*", "process.*", "cpython.*")

# The process's own resources and the interpreter's collector; the host's are not the process's.
_PROCESS_METRICS: Final[Mapping[str, list[str] | None]] = MappingProxyType(
    {
        "process.cpu.time": ["user", "system"],
        "process.cpu.utilization": ["user", "system"],
        "process.memory.usage": None,
        "process.memory.virtual": None,
        "process.thread.count": None,
        "process.open_file_descriptor.count": None,
        "process.context_switches": ["involuntary", "voluntary"],
        "cpython.gc.collections": None,
        "cpython.gc.collected_objects": None,
        "cpython.gc.uncollectable_objects": None,
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceIdentity:
    """Who sends the telemetry: the same on traces, metrics and profiles of a process."""

    name: str
    environment: DeploymentEnvironmentNameValues


def configure_tracing(service: ServiceIdentity, *, otlp_endpoint: str) -> TracerProvider:
    """Make the process's tracer provider, shipping spans in batches over OTLP.

    Args:
        service: Who sends the traces.
        otlp_endpoint: The OTLP receiver address.

    Returns:
        The provider.
    """
    provider = TracerProvider(resource=_resource(service))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, timeout=_EXPORT_TIMEOUT_SECONDS))
    )
    trace.set_tracer_provider(provider)
    logger.info("exporting traces over OTLP", extra={"otlp_endpoint": otlp_endpoint})
    return provider


def configure_metrics(service: ServiceIdentity, *, otlp_endpoint: str) -> None:
    """Make the process's meter provider and measure the process; only served requests and the process ship.

    Args:
        service: Who sends the metrics.
        otlp_endpoint: The OTLP receiver address.
    """
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, timeout=_EXPORT_TIMEOUT_SECONDS),
        export_interval_millis=_EXPORT_EVERY_MILLISECONDS,
    )
    # A drop for everything, and a stream for each name kept: a matching view adds a stream, not replaces one.
    views = [View(instrument_name="*", aggregation=DropAggregation())]
    views.extend(View(instrument_name=name) for name in _SHIPPED_METRICS)
    provider = MeterProvider(resource=_resource(service), metric_readers=[reader], views=views)
    metrics.set_meter_provider(provider)
    SystemMetricsInstrumentor(config=dict(_PROCESS_METRICS)).instrument(meter_provider=provider)
    logger.info("exporting metrics over OTLP", extra={"otlp_endpoint": otlp_endpoint})


def configure_profiling(service: ServiceIdentity, tracer_provider: TracerProvider, *, pyroscope_url: str) -> None:
    """Start CPU profiling, its samples labelled with the root spans of `tracer_provider`.

    Only root spans started after this call label samples, and only on their own thread.

    Args:
        service: Who sends the profiles.
        tracer_provider: The provider whose root spans label the samples.
        pyroscope_url: The profile receiver address.
    """
    pyroscope.configure(
        application_name=service.name,
        server_address=pyroscope_url,
        sample_rate=_PROFILE_SAMPLES_PER_SECOND,
        upload_interval=_PROFILE_UPLOAD_EVERY_SECONDS,
        # The profile ingest protocol drops label names with dots.
        tags={DEPLOYMENT_ENVIRONMENT_NAME.replace(".", "_"): service.environment.value},
        # Looking for a busy CPU: waiting on a remote service would otherwise fill the whole picture.
        oncpu=True,
        gil_only=True,
    )
    tracer_provider.add_span_processor(PyroscopeSpanProcessor())
    logger.info("sending CPU profiles to Pyroscope", extra={"pyroscope_url": pyroscope_url})


def _resource(service: ServiceIdentity) -> Resource:
    # One per process: the series of two processes must not merge.
    instance_id = f"{socket.gethostname()}-{os.getpid()}"
    identity = {
        SERVICE_NAME: service.name,
        SERVICE_INSTANCE_ID: instance_id,
        DEPLOYMENT_ENVIRONMENT_NAME: service.environment.value,
    }
    return Resource.create(identity).merge(ContainerResourceDetector().detect())
