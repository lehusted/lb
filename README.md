# LB interview case

## Run

Install Docker Desktop with Linux containers, then run:

```bash
docker compose up --build
```

Internet access is needed for images, Python packages and the public data sources.
One Compose file starts the frontend, FastAPI backend and Prometheus.

| URL | Purpose |
| --- | --- |
| http://localhost:8080 | LB interview case frontend (Danish) |
| http://localhost:8000/docs | API documentation |
| http://localhost:8000/health | Backend liveness |
| http://localhost:8000/metrics | Prometheus exposition |
| http://localhost:9090 | Prometheus UI |

All host ports bind to localhost. Stop with `Ctrl+C`, then `docker compose down`.

Enter a company name or an eight-digit CVR, select a statistics year (2008-2024),
and click Søg. Name searches return candidates to select; a CVR fetches details
directly. **Novo Nordisk, CVR 24256790, year 2024** is the verified demo.
Other industries return an explicit error until their mappings are verified.
Loading, empty results and request errors are displayed on the page.

The API can also be used directly. On PowerShell, use `curl.exe`:

```bash
curl "http://localhost:8000/companies?name=Novo%20Nordisk"
curl "http://localhost:8000/companies/24256790?year=2024"
```

For Python development and the existing tests, use Python 3.12 or later:

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

There is one Python dependency file, used by local development, Docker and CI.
The frontend has no package dependencies or build step; Compose builds its image
by copying static files into Nginx.

## API and data meaning

| Request | Result |
| --- | --- |
| `GET /companies?name=...` | Candidates with CVR, name and status; name requires at least two characters |
| `GET /companies/{cvr_number}?year=2024` | Current company information plus industry statistics for the selected year |
| `GET /health` | Liveness only; does not contact data sources |
| `GET /metrics` | OpenTelemetry metrics in Prometheus format |

The frontend forwards `/api/...` to these backend routes. Name search requires
choosing a company; ceased companies remain visible with their source status.

- `company`: CVR, name, address, primary `industry_code_db25`, `employees`, and
  `data_period: "current"`.
- `industry_statistics`: year, `industry_code_db07`, `workplaces`, `jobs`,
  `full_time_employment`, and `payroll_million_dkk`.
- `mapping: "verified_csv"` identifies the verified classification allowlist.

Company information is **current**, not reconstructed for the historical year.
ERHV1 values describe the **whole industry**: workplaces are not legal companies;
jobs are positions at the end of November, not unique people or company headcount.
Annual payroll is in millions of DKK. Missing values remain JSON `null` and appear
as **Ikke tilgængelig** in the frontend; zero remains zero.

### Verified classification mapping

`data/db25_to_db07.csv` allows only the verified pharmaceutical preparations
mapping **212000 -> 212000**. Equal code digits alone do not prove equivalence.
No manual classification override is available.

Source: Statistics Denmark's [DB07/DB25 documentation](https://www.dst.dk/da/Statistik/dokumentation/dansk-branchekode-er-gaeldende)
and [detailed correspondence workbook](https://www.dst.dk/ext/9884313386991/0/erhvervreg/DB07_DB25_noegle_brancher-%28xlsx%29--xlsx),
updated 26 February 2026. Verification on 11 October 2026 checked `DB25-DB07`
row 196, `DB07-DB25` row 191, and the unchanged-industry worksheet row 100.
Both relationship counts are 1, with no inclusion/exclusion changes.
Workbook SHA-256: `6e618cefb38106cc03606c504b8a8b9f4873a2c40454a8b6f25ca685f6eea04e`.
Add mappings only after verifying correspondence in both directions.

ERHV1 is requested as Danish UTF-8 CSV with code-valued columns
`BRANCHE07;TAL;TID;INDHOLD`. The parser validates industry, year, all four measures,
duplicates, row widths and Danish numeric syntax. Unexpected payloads fail safely.

| Scenario | HTTP status |
| --- | --- |
| Invalid input, absent industry or unsupported mapping | 422 |
| Company not found | 404 |
| Data source HTTP failure or invalid payload | 502 |
| Data source timeout | 504 |

Both integrations have finite 5-second HTTP timeouts per connect/read/write/pool
operation, not a five-second total deadline. Errors expose controlled messages.

## Architecture and Design Decisions

```text
Browser -> Nginx frontend -> /api/ -> FastAPI -> APICVR + ERHV1
                                        |
                                        +-> /metrics <- Prometheus
```

| Component | Responsibility / decision |
| --- | --- |
| `frontend/index.html`, `styles.css`, `app.js` | One Danish page, native controls and browser fetch; no frontend framework |
| `frontend/nginx.conf`, `Dockerfile` | Separate non-root static server; same-origin API proxy avoids CORS configuration |
| `app/main.py` | Validation, orchestration, HTTP errors and API metrics |
| `app/cvr.py`, `statistics.py`, `industry.py` | Data source requests, validated transformation and verified mapping |
| `app/metrics.py` / OpenTelemetry | Counters and latency histograms exported directly to Prometheus |
| Docker Compose | Three services in one runnable setup |
| `requirements.txt` | One pinned dependency set, including pytest for existing checks |

One Uvicorn worker preserves the single-process metrics model. The backend runs
as UID/GID 10001; Nginx also runs without root. Browser-rendered source values use
`textContent`, not HTML interpolation. A content security policy allows only local
resources, and responses disable browser caching. Frontend access logging is off
to avoid recording lookup queries. Inputs have labels, keyboard access, visible
focus, and announced loading/error states. The API remains the validation boundary.

No database, cache, message broker, frontend build tooling, tracing, Collector,
Grafana or Kubernetes is needed for this lookup flow.

## Metrics

Prometheus scrapes `http://app:8000/metrics` every five seconds.
`up{job="lb-interview-case"}` should be `1`. Send requests and allow at least two
scrapes before querying rates:

```promql
# API P95, last five minutes
histogram_quantile(0.95, sum by (le) (rate(api_request_duration_seconds_bucket[5m])))

# API 5xx fraction
(sum(rate(api_requests_total{outcome="error"}[5m]))
 or (0 * sum(rate(api_requests_total[5m]))))
/ sum(rate(api_requests_total[5m]))

# P95 for each data source
histogram_quantile(0.95, sum by (source, le) (rate(downstream_request_duration_seconds_bucket[5m])))

# Error fraction for each data source
(sum by (source) (rate(downstream_requests_total{outcome="error"}[5m]))
 or on (source) (0 * sum by (source) (rate(downstream_requests_total[5m]))))
/ sum by (source) (rate(downstream_requests_total[5m]))
```

Error fractions times 100 give percentages. P95 is a histogram estimate; buckets
range from 0.01 to 30 seconds plus infinity. Zero-request intervals have undefined
rates. Labels contain route templates and sources, not CVRs or names. Health and
metrics endpoints are excluded. Data source timing includes payload validation;
invalid HTTP-200 payloads count as errors, while a CVR 404 is `not_found`.

## Verification and CI

`pytest -q` runs 70 existing deterministic tests, including real OpenTelemetry
export, validation, null handling, Danish numbers and controlled data source errors.
Company fixtures are synthetic; the ERHV1 fixture contains only public aggregate
statistics. No personal CVR responses are stored in the repository.

Verified on 11 October 2026: all 70 tests passed on Windows and inside the normal
Linux image. Both online Docker builds and the three-service Compose startup
succeeded. Live CVR lookup, name search and candidate selection worked through the
frontend; Nginx configuration, proxy headers and Prometheus scraping passed.
The mobile page had no horizontal overflow at 390 pixels, and the automated
accessibility audit scored 100. These checks do not guarantee public API availability.

GitHub Actions installs `requirements.txt`, runs the tests and builds both images
with Compose. Successful pushes to `main` publish the backend image to GHCR with
`latest` and commit-SHA tags. Only that job has package write permission. The
frontend image is built locally by Compose. GitHub Actions/GHCR execution and
public repository publication have not been verified or performed here.

## Known Challenges & Limitations

| Challenge | Handling / remaining limit |
| --- | --- |
| Historical company information | Clearly labeled current data; historical reconstruction requires another source |
| Company counts versus workplaces; people versus jobs | Preserve ERHV1 terminology; literal legal-company counts are not provided |
| DB25/DB07 conversion | Only industry 212000 is verified; broader enrichment requires authoritative mappings |
| Missing values | Display Ikke tilgængelig; never guess employee counts or replace null with zero |
| Public data sources | Timeouts and outages can interrupt lookups; show controlled errors and expose metrics |
| Statistics years | Only 2008-2024; recheck source availability before expanding |
| Local demonstration | Localhost ports and non-root services; public hosting requires a separate security review |
| Metrics lifecycle | One backend worker; application counters restart with the process |
| Delivery | Internet is needed for normal builds; GitHub/GHCR execution remains unverified |
