# main.py er API'ets hovedmodul og står primært for koordinering/orkestrering af de forskellige komponenter. Den håndterer HTTP-requests, validerer input, kalder eksterne API'er og returnerer standardiserede svar. 

from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import StringConstraints

from . import cvr, industry, metrics
from .models import AmbiguousName, ErrorResponse, LookupResult

# Fejlmeddelelser - herunder defininering og kontrakt
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Company not found"},
    502: {"model": ErrorResponse, "description": "CVR source failed or returned invalid data"},
    504: {"model": ErrorResponse, "description": "CVR source timed out"},
}

# Funktionen, LifeSpan, håndterer applikationens livscyklus og konfigurerer metrikkerne ved opstart. Den sikrer, at alle nødvendige metrikker er initialiseret og klar til brug.
@asynccontextmanager
async def lifespan(app: FastAPI):
    metrics.configure()
    for path in [route.path for route in app.routes] + ["unmatched"]:
        if path in ("/health", "/metrics"):
            continue
        for outcome in ("success", "client_error", "error"):
            metrics.api_calls.add(0, {"path": path, "outcome": outcome})
    yield

# Skaber FastAPI applikationen, definerer dens metadata og tilknytter livscyklus-håndteringen.
app = FastAPI(
    title="LB interview case", 
    version="0.5.0",
    lifespan=lifespan
    )

# Funktion, der opretter den udadgående http klient, der bruges til at kalde eksterne API'er. Den sikrer, at klienten har en passende timeout og håndterer ressourcer korrekt.
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client

# Middleware, der har til formål at måle alle indgående HTTP-requests - undtagen dem til /metrics og /health. Den registrerer starttidspunktet, udfører requesten og måler varigheden samt outcome (success, client_error, error). Metrikkerne sendes til Prometheus for overvågning og analyse.
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

# Funktion til at håndtere fejl fra eksterne API'er
def upstream_error(error: Exception, source: str) -> HTTPException:
    if isinstance(error, httpx.TimeoutException):
        return HTTPException(504, detail=f"{source} timed out")
    if (source == "CVR API" and isinstance(error, httpx.HTTPStatusError)
            and error.response.status_code == 404):
        return HTTPException(404, detail=f"{source}: not found")
    return HTTPException(502, detail=f"{source} is unavailable or returned invalid data")

# /health api endpoint - returnerer en simpel status
@app.get("/health")
def health():
    return {"status": "ok"}  

# /metrics api endpoint - returnerer/eksponerer Prometheus metrikker
@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Endpoint til at identificere en virksomhed baseret på dets navn. Håndterer en request som: "GET /companies?name=Example&year=2024"
@app.get("/companies", response_model=LookupResult,
         responses={**ERROR_RESPONSES, 409: {"model": AmbiguousName}})
async def lookup_by_name(
    name: Annotated[
        str, Query(), StringConstraints(strip_whitespace=True, min_length=2, max_length=200)
    ],
    year: int = Query(ge=2008, le=2024),
    client: httpx.AsyncClient = Depends(http_client),
):
    try:
        candidates = await cvr.search(client, name)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise upstream_error(exc, "CVR API") from exc
    if not candidates:
        raise HTTPException(404, detail="No company matches this name")
    if len(candidates) > 1:
        return JSONResponse(status_code=409, content={
            "message": "Multiple companies match; select a CVR number",
            "candidates": candidates,
        })
    return await enrich_company(client, candidates[0]["cvr"], year)

# Endpoint til at identificere en allerede identificeret virksomhed baseret på dets CVR nummer. Håndterer en request som: "GET /companies/12345678?year=2024"
@app.get("/companies/{cvr_number}", response_model=LookupResult, responses=ERROR_RESPONSES)
async def lookup_by_cvr(
    cvr_number: str = Path(pattern=r"^[0-9]{8}$"),
    year: int = Query(ge=2008, le=2024),
    client: httpx.AsyncClient = Depends(http_client),
):
    return await enrich_company(client, cvr_number, year)

# Funktion til at indhente virksomhedsdata og berige med statistikker. Håndterer både CVR og StatBank integrationerne, og sikrer, at fejl håndteres korrekt og at advarsler returneres, hvis data ikke er tilgængelige.
async def enrich_company(client: httpx.AsyncClient, cvr_number: str, year: int) -> LookupResult:
    """Both routes use this flow; failed statistics never discard company data."""
    try:
        company = await cvr.get_company(client, cvr_number)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise upstream_error(exc, "CVR API") from exc
    # Tilgængeligheds tjeks med advarsler, hvis data ikke er tilgængelig.
    warnings = []
    if company["employees"] is None:
        warnings.append("employees_unavailable")
    if company["address"] is None:
        warnings.append("address_unavailable")
    industry_code = company["industry_code_db25"]

    # Tilføjer yderligere branchestatistikker, hvis branchekoden er tilgængelig. Håndterer fejl og advarsler, hvis data ikke kan hentes eller er ufuldstændige.
    industry_stats = None
    if industry_code is None:
        warnings.append("industry_missing")
    else:
        try:
            industry_stats, industry_warnings = await industry.fetch(client, industry_code, year)
            warnings.extend(industry_warnings)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            warnings.append("statistics_timeout" if isinstance(exc, httpx.TimeoutException)
                            else "statistics_unavailable")
            
    # Returnerer det samlede resultat - inklusiv virksomhedens data, branchestatistikker og eventuelle advarsler. Metrikkerne opdateres for at afspejle resultatets status (komplet eller delvis).
    result = LookupResult(year=year, status="partial" if warnings else "complete",
                          company=company, industry_statistics=industry_stats, warnings=warnings)
    metrics.lookup_results.add(1, {"status": result.status})
    return result
