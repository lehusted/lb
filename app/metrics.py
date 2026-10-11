"""OpenTelemetry metrics and request timing; no tracing or Collector."""

from contextlib import asynccontextmanager
from time import perf_counter

import httpx

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

_configured = False
meter = metrics.get_meter("lb-interview-case")
api_calls = meter.create_counter("api_requests")
api_duration = meter.create_histogram("api_request_duration", unit="s")
source_calls = meter.create_counter("downstream_requests")
source_duration = meter.create_histogram("downstream_request_duration", unit="s")


def configure() -> None:
    """Called once on application startup (one Uvicorn worker only)."""
    global _configured
    if _configured:
        return
    from opentelemetry.exporter.prometheus import PrometheusMetricReader

    buckets = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30]
    views = [
        View(instrument_name=name, aggregation=ExplicitBucketHistogramAggregation(buckets))
        for name in ("api_request_duration", "downstream_request_duration")
    ]
    metrics.set_meter_provider(MeterProvider(
        resource=Resource.create({"service.name": "lb-interview-case"}),
        metric_readers=[PrometheusMetricReader()],
        views=views,
    ))
    # A zero baseline lets Prometheus rate() include the first failure.
    for source in ("cvr", "statbank"):
        for outcome in ("success", "error", "not_found"):
            source_calls.add(0, {"source": source, "outcome": outcome})
    _configured = True


@asynccontextmanager
async def measured_request(client, method: str, url: str, source: str, **kwargs):
    """Measure HTTP and payload validation as one integration call."""
    started = perf_counter()
    outcome = "error"
    try:
        response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        yield response
        outcome = "success"
    except httpx.HTTPStatusError as exc:
        if source == "cvr" and exc.response.status_code == 404:
            outcome = "not_found"
        raise
    finally:
        labels = {"source": source, "outcome": outcome}
        source_calls.add(1, labels)
        source_duration.record(perf_counter() - started, {"source": source})
