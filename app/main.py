"""REST API: search, enrich, health and Prometheus metrics."""

from contextlib import asynccontextmanager
from time import perf_counter

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import cvr, metrics, statistics
from .industry import to_db07


@asynccontextmanager
async def lifespan(app: FastAPI):
    metrics.configure()
    for path in [route.path for route in app.routes] + ["unmatched"]:
        if path in ("/health", "/metrics"):
            continue
        for outcome in ("success", "client_error", "error"):
            metrics.api_calls.add(0, {"path": path, "outcome": outcome})
    yield


app = FastAPI(title="LB interview case", version="0.2.0", lifespan=lifespan)


async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@app.middleware("http")
async def measure_api(request, call_next):
    if request.url.path in ("/metrics", "/health"):
        return await call_next(request)
    started, outcome = perf_counter(), "error"
    try:
        response = await call_next(request)
        outcome = "error" if response.status_code >= 500 else (
            "client_error" if response.status_code >= 400 else "success"
        )
        return response
    finally:
        route = request.scope.get("route")
        labels = {"path": route.path if route else "unmatched", "outcome": outcome}
        metrics.api_calls.add(1, labels)
        metrics.api_duration.record(perf_counter() - started, {"path": labels["path"]})


def upstream_error(error: Exception, source: str) -> HTTPException:
    if isinstance(error, httpx.TimeoutException):
        return HTTPException(504, detail=f"{source} timed out")
    if (source == "CVR API" and isinstance(error, httpx.HTTPStatusError)
            and error.response.status_code == 404):
        return HTTPException(404, detail=f"{source}: not found")
    return HTTPException(502, detail=f"{source} is unavailable or returned invalid data")


@app.get("/health")
def health():
    return {"status": "ok"}  # Liveness only; does not call external services.


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/companies")
async def search(name: str = Query(min_length=2), client: httpx.AsyncClient = Depends(http_client)):
    try:
        return await cvr.search(client, name)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise upstream_error(exc, "CVR API") from exc


@app.get("/companies/{cvr_number}")
async def enrich(
    cvr_number: str,
    year: int = Query(ge=2008, le=2024),
    client: httpx.AsyncClient = Depends(http_client),
):
    if not (cvr_number.isascii() and cvr_number.isdigit() and len(cvr_number) == 8):
        raise HTTPException(422, detail="CVR number must be 8 digits")
    try:
        company = await cvr.get_company(client, cvr_number)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise upstream_error(exc, "CVR API") from exc
    industry_code = company["industry_code_db25"]
    if industry_code is None:
        raise HTTPException(422, detail="Company has no industry code")
    mapped = to_db07(industry_code)
    if mapped is None:
        raise HTTPException(422, detail="No verified DB25 -> DB07 mapping for this company")
    try:
        industry_stats = await statistics.fetch(client, mapped, year)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise upstream_error(exc, "Statistics Denmark") from exc
    return {
        "company": company,
        "industry_statistics": industry_stats,
        "mapping": "verified_csv",
    }
