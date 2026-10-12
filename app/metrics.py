# Metrics.py er applikationens fælles monitoreringsmodul. Den definerer hvad der bliver målt og forbinder disse til Prometheus. Idéen er at skabe en konsistent måde at gemme og rapportere metrikker på.

from contextlib import asynccontextmanager
from time import perf_counter

import httpx

# Man kunne godt have simplificeret yderligere og kun brugt Prometheus, men det ville gøre det sværere at skifte til en anden metrik backend senere. 
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

# Denne blok skaber instrumenteringen for applikationen. Den definerer hvilke metrikker der skal måles, og hvordan de skal aggregeres.
_configured = False
meter = metrics.get_meter("lb-interview-case")
api_calls = meter.create_counter("api_requests")
api_duration = meter.create_histogram("api_request_duration", unit="s")
source_calls = meter.create_counter("downstream_requests")
source_duration = meter.create_histogram("downstream_request_duration", unit="s")
lookup_results = meter.create_counter("lookup_results")

# Konfiguration af metrikkerne - kaldes kun én gang ved opstart af applikationen. Den definerer hvilke metrikker der skal måles, og hvordan de skal aggregeres.
def configure() -> None:
    global _configured
    if _configured:
        return
    from opentelemetry.exporter.prometheus import PrometheusMetricReader

# Denne blok definerer tidsintervaller og hvordan disse skal aggregeres.
    buckets = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30]
    views = [
        View(instrument_name=name, aggregation=ExplicitBucketHistogramAggregation(buckets))
        for name in ("api_request_duration", "downstream_request_duration")
    ]
    # Denne blok forbinder metrikkerne til Prometheus og definerer hvilke metrikker der skal måles, og hvordan de skal aggregeres.
    metrics.set_meter_provider(MeterProvider(
        resource=Resource.create({"service.name": "lb-interview-case"}),
        metric_readers=[PrometheusMetricReader()],
        views=views,
    ))
    for source in ("cvr", "statbank"):
        for outcome in ("success", "error", "not_found"):
            source_calls.add(0, {"source": source, "outcome": outcome})
    for status in ("complete", "partial"):
        lookup_results.add(0, {"status": status})
    _configured = True

# Denne blok er den delte 'wrapper' brugt af CVR og StatBank integrationerne,
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
