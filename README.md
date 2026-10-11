# LB interview case

A small REST service that looks up a Danish company and adds industry statistics.
The company information is current. The selected year applies to the statistics.

## Run

Install Docker Desktop with Linux containers, then run:

~~~bash
docker compose up --build
~~~

| URL | Purpose |
| --- | --- |
| http://localhost:8080 | Danish lookup page |
| http://localhost:8000/docs | Interactive API documentation and response schemas |
| http://localhost:8000/health | Application liveness |
| http://localhost:8000/metrics | Prometheus metrics |
| http://localhost:9090 | Prometheus query interface |

Ports bind to localhost. Internet access is required for builds and public APIs.
Stop with Ctrl+C, then run docker compose down.

For local Python development, use Python 3.12 or later:

~~~bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
~~~

## How a lookup works

1. Validate the CVR or search the company name.
2. A unique name match supplies its CVR. Multiple matches require a selection.
3. Fetch the current company name, address, industry code and employee count.
4. Send that industry code and the selected year to ERHV1, as specified in the case.
5. Return company data and statistics together. Explain anything unavailable.

Both lookup routes call the same enrich_company function in app/main.py.
There is no database or saved company history.

| File | What it does |
| --- | --- |
| app/main.py | Routes, shared lookup flow, controlled errors and API timing |
| app/cvr.py | Calls APICVR and selects/validates company fields |
| app/statistics.py | Requests ERHV1 and validates/parses its Danish CSV |
| app/models.py | Defines the JSON response shapes displayed in /docs |
| app/metrics.py | Measures downstream calls and exports OpenTelemetry metrics |
| frontend/app.js | Sends lookups and displays results or name candidates |
| compose.yaml | Starts the API, static frontend and Prometheus |

## API examples

On PowerShell, use curl.exe. Both routes require an integer year from 2008 to 2024.

~~~bash
curl.exe "http://localhost:8000/companies/16500836?year=2024"
curl.exe "http://localhost:8000/companies?name=LB%20forsikring&year=2024"
curl.exe "http://localhost:8000/companies/24256790?year=2024"
~~~

A unique name returns the same response shape as a CVR lookup:

- year: the requested statistics year, retained even if statistics are unavailable.
- status: complete when all requested values are available, otherwise partial.
- company: CVR, name, address, industry_code_db25, employees, data_period and employees_period.
- industry_statistics: year, industry_code_db07 and the four measures below, or null.
- warnings: reason codes for unavailable information.

The name search is APICVR's prefix search, limited to 100 candidates. HTTP 409
returns message and candidates (CVR, name, source status). Choose a CVR and
request its details; the service never picks the first of several matches.
Company lifecycle status is shown in candidates, including ceased companies.
Names are trimmed before validating their length (2–200 characters). All input
validation errors use FastAPI's documented HTTP 422 response with a detail array.

| Situation | HTTP status / result |
| --- | --- |
| Complete or partial company lookup | 200 |
| No matching company / CVR not found | 404 |
| Multiple name matches | 409 with candidates |
| Invalid CVR, name or year | 422 |
| APICVR failure or malformed response | 502 |
| APICVR timeout | 504 |
| Industry code missing, rejected by StatBank or statistics request failed | 200, partial; company retained and statistics null |

| Warning code | Meaning |
| --- | --- |
| employees_unavailable | APICVR did not supply the employee count |
| address_unavailable | APICVR did not supply an address |
| industry_missing | The company has no primary industry code |
| statistics_timeout | StatBank timed out; retrying may help |
| statistics_unavailable | StatBank rejected the code/year, failed or returned invalid data |
| statistics_values_unavailable | Some ERHV1 values are missing or suppressed |

A missing value remains null; zero remains zero. The frontend displays
"Ikke tilgængelig". Missing statistics never discard company information.

## Data meaning and classification

The case's wording was clarified with the user on 11 October 2026:

- Use current company data plus industry statistics for the selected year.
- Use the case's ERHV1 request and label its actual measures accurately.
- Return a partial result when enrichment is unavailable.

APICVR returns current name, address and primary industry. Its employee count
is the latest reported monthly count, but its reporting period is not exposed.
Therefore data_period is current and employees_period is null. Neither means
that the employee count belongs to the selected statistics year.

| JSON field | ERHV1 code | Meaning |
| --- | --- | --- |
| workplaces | ARBSTED | Workplaces at the end of November, not legal companies |
| jobs | ANSATTE | Jobs at the end of November, not unique people |
| full_time_employment | FULDBESK | Employment converted to full-time equivalents |
| payroll_million_dkk | LØNSUM | Annual payroll in millions of DKK |

These describe the whole industry, not the selected company.
Source: [Statistics Denmark's definitions](https://www.dst.dk/da/Statistik/dokumentation/statistikdokumentation/arbejdssteder-og-job/indhold)
and [APICVR's transformation](https://github.com/NoahBohme/apicvr.dk/blob/master/apis/searchcvr.py).

The MVP follows the requested case flow: APICVR's industrycode is sent directly
as BRANCHE07 in the ERHV1 POST body. There is no manually maintained conversion
file or industry allowlist. The previous one-row mapping blocked almost every
industry before the StatBank request and has been removed.

CVR uses DB25; ERHV1 uses DB07. Direct code selection is a simplification, and
equal digits do not establish equal industry scope. A complete response means
all requested values were returned; it does not certify classification equivalence.
The API documentation and frontend make this limitation explicit. Verify the
classification correspondence before using these results for analytical comparisons.
If StatBank rejects the code/year or returns no usable data, the company is
retained with null statistics and a clear warning.

Source: [DB25 guidance](https://www.dst.dk/da/Statistik/dokumentation/dansk-branchekode-er-gaeldende)
and [ERHV1 documentation](https://www.dst.dk/en/Statistik/dokumentation/documentationofstatistics/workplaces-and-jobs/accessibility-and-clarity).

The ERHV1 parser checks headers, industry, year, all four measures, duplicate
rows and Danish numeric syntax. Invalid data counts as a downstream failure.

## Metrics

OpenTelemetry exports directly to Prometheus. Prometheus scrapes every five seconds.
There is one API worker, so counters describe one process and reset on restart.

After lookups and at least two scrapes, run these queries:

~~~promql
# Service P95 in seconds
histogram_quantile(0.95, sum by (le) (rate(api_request_duration_seconds_bucket[5m])))

# Service HTTP 5xx fraction
sum(rate(api_requests_total{outcome="error"}[5m]))
/ sum(rate(api_requests_total[5m]))

# P95 for each source: cvr and statbank
histogram_quantile(0.95, sum by (source, le) (rate(downstream_request_duration_seconds_bucket[5m])))

# Failure fraction for each source
sum by (source) (rate(downstream_requests_total{outcome="error"}[5m]))
/ sum by (source) (rate(downstream_requests_total[5m]))

# Partial-result fraction among returned company results
sum(rate(lookup_results_total{status="partial"}[5m]))
/ sum(rate(lookup_results_total[5m]))
~~~

Multiply fractions by 100 for percentages. No-traffic rates are undefined.
P95 is a histogram estimate, not an exact percentile of stored requests.
StatBank failures count as downstream errors even when the API returns partial HTTP 200.
Partial results also include missing source fields and rejected industry codes.
A company-not-found response is counted separately from downstream outages.
Labels never contain names, CVRs or exception text.

The health endpoint checks application liveness only. Downstream metrics measure
actual requests and payload validation; they do not actively probe idle sources.

## Architecture and Design Decisions

~~~text
Browser -> Nginx -> FastAPI -> APICVR -> StatBank
                      |
                      +-> /metrics <- Prometheus
~~~

- Python, FastAPI and httpx keep the request flow direct.
- Two routes share one lookup function; there are no service or repository layers.
- Pydantic response models make the contract visible in the existing FastAPI docs.
- Name searches use APICVR's query endpoint so names containing `/` are supported.
  Pydantic trims names and validates their length using the standard HTTP 422 format.
- Address components are trimmed and blanks omitted; an entirely missing address
  remains null and produces an address_unavailable warning.
- The CVR industry code goes directly into the case's ERHV1 request. This removes
  the one-row conversion restriction; differing classification scopes remain an explicit limitation.
- A simple partial response keeps valid company data when statistics are unavailable.
- No database, cache, tracing, Collector, Grafana or Kubernetes is needed.
- Each downstream request has finite five-second connect/read/write/pool timeouts.
  This is not a five-second total deadline. There are no automatic retries.
- The static frontend needs no framework, package dependencies or build step.
- Containers run without root. The frontend uses textContent and a local-only CSP.
  Inputs are validated by the API, and error messages do not expose raw responses.
- Three parameterized test functions share one HTTP mock setup in tests/test_cases.py.
  They exercise both routes without external API calls; pytest is a development dependency.

## Verification, CI and remaining delivery work

The original failure was in enrichment: a one-row conversion list blocked
almost all industries, initially causing HTTP 422 and later null statistics. Name lookup
also returned candidates without a combined company/statistics response. Both
routes now share the lookup flow, and unavailable enrichment returns partial data.

| Case requirement | Current coverage |
| --- | --- |
| Look up by CVR or name | Both supported; ambiguous names require a selection |
| Company name, address, industry and employees | Returned together; unavailable fields remain null |
| Company data for a given year | Agreed interpretation: current company data plus selected-year statistics |
| Four industry measures in the same response | CVR code and selected year sent directly to ERHV1; values returned together or null with a reason |
| REST or GraphQL API | REST with interactive documentation and response schemas |
| Service and downstream P95/error rates | OpenTelemetry metrics scraped by Prometheus; partial results also measured |
| Robust downstream handling | Controlled errors, finite timeouts, payload validation and partial statistics failures |
| Automated tests | Focused regression coverage for temporal semantics, statistical measures, years and missing observations on both routes |
| Docker delivery | API and frontend build and run through Compose with Prometheus |
| CI build, test and image publication | Tests run before builds; publication configured but remote execution unverified |
| Public repository and README | Existing repository is public; README covers running, examples and trade-offs |
| Architecture discussion | The lookup walkthrough and design decisions explain the MVP |

Local verification passed for Docker builds and health, both LB lookup routes,
a complete Novo Nordisk result, ambiguous-name selection, invalid inputs,
integration failure handling, browser rendering and the Prometheus queries.
The direct-code flow returned all four 2024 measures for 651200, 212000 and
701010. StatBank's rejection of 461890 produced a partial result with company
data retained. Synthetic integration checks confirmed that both routes send
the supplied code/year and preserve null, zero and decimal values.
These are smoke checks, not performance benchmarks or a replacement unit suite.

The old suite has been replaced with focused regression tests in tests/test_cases.py.
All test data is synthetic, and external HTTP calls use httpx.MockTransport.
Three parameterized functions cover current company versus historical statistics,
the four measures and their units, zero/decimal preservation, both boundary years,
invalid or missing years, exact-year forwarding, and empty/suppressed observations.
Comments explaining each case are in Danish. These tests do not verify live sources
or DB25-to-DB07 correspondence.

Run from the repository root in the Python environment described above:

~~~bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
~~~

GitHub Actions runs the tests before building both Docker images. Pushes to main publish the
backend to GHCR with latest and commit-SHA tags. Only the publishing job has
package-write permission. Passing tests do not establish live integration or
classification equivalence.

The existing repository is public: https://github.com/lehusted/lb.
Local changes are not automatically published. Actual CI/GHCR publication must
be verified separately when delivering the finished case.

Finish delivery in two steps:

1. If further test coverage is requested, cover ambiguous names, unavailable company
   employees, malformed CSV and both sources' failure paths using synthetic data.
2. Publish the finished changes and verify the actual CI run and published image.

Verified DB25-to-DB07 conversion is a separate improvement if exact industry
comparability becomes required; it is outside the current direct-code flow.

For the interview, demonstrate a CVR lookup, a unique name, ambiguous candidates
and a partial result. Explain the five lookup steps above, the data interpretations,
and how unit tests and deployment verification complete the case requirements.

## Known Challenges & Limitations

| Challenge | Handling / remaining limit |
| --- | --- |
| Historical company information | Current data is explicit; historical reconstruction is outside the agreed MVP |
| Case terminology | ERHV1 supplies workplaces and jobs; these are labeled accurately |
| Different industry classifications | CVR code queried directly in ERHV1; DB25/DB07 scope equivalence is not verified |
| Employee reporting period | Not exposed by APICVR; employees_period remains null |
| Missing/suppressed data | Preserve null and explain partial results; blank address components are omitted |
| Public API failures | Finite timeouts; company retained on statistics failure; metrics expose degradation |
| Statistics years | ERHV1 metadata checked on 11 October 2026: 2008–2024 |
| Name searches | Query endpoint supports `/`; prefix matching; maximum 100 candidates; no arbitrary first-match selection |
| Tests | Focused offline regression suite; classification, ambiguity and broader source-failure coverage remain outside this suite |
| Deployment | Localhost demonstration; one worker; actual publication remains to be verified |
