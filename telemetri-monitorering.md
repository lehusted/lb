# Verificér NFR: telemetri og monitorering

OpenTelemetry registrerer kald og varigheder i [app/metrics.py](app/metrics.py#L14). Prometheus henter målingerne hvert femte sekund og beregner P95 og fejlprocent ved forespørgsel. Der er ingen gemte recording rules, dashboards eller alarmer.

## Fremgangsmåde

1. Start projektet med `docker compose up --build`.
2. Åbn [Prometheus Query](http://localhost:9090/query), vælg **Table**, skriv `up`, og klik **Execute**. Resultatet skal være `1`; [Targets](http://localhost:9090/targets) skal vise API'et som **UP**.
3. Lav flere virksomhedsopslag på [frontend](http://localhost:8080) med 5–10 sekunders mellemrum. Vent yderligere 5–10 sekunder, så Prometheus når at hente målingerne.
4. Kør de fire forespørgsler nedenfor enkeltvis med **Execute**. **Table** viser aktuelle resultater; **Graph** viser udviklingen over tid. Rå målinger findes på [API'ets /metrics](http://localhost:8000/metrics).

Forespørgslerne bruger den seneste time. Skift `[1h]` til `[5m]` for de seneste fem minutter.

## Forespørgsler

**API: estimeret P95 i sekunder pr. opslagsrute**

```promql
histogram_quantile(0.95,
  sum by (le, path) (rate(api_request_duration_seconds_bucket{path=~"/companies.*"}[1h]))
)
```

**API: fejlprocent pr. opslagsrute**

```promql
100 *
sum by (path) (rate(api_requests_total{path=~"/companies.*",outcome="error"}[1h]))
/
sum by (path) (rate(api_requests_total{path=~"/companies.*"}[1h]))
```

**Datakilder: estimeret P95 i sekunder pr. kilde (`cvr` og `statbank`)**

```promql
histogram_quantile(0.95,
  sum by (le, source) (rate(downstream_request_duration_seconds_bucket[1h]))
)
```

**Datakilder: fejlprocent pr. kilde**

```promql
100 * sum by (source) (rate(downstream_requests_total{outcome="error"}[1h]))
/
sum by (source) (rate(downstream_requests_total[1h]))
```

## Fortolkning

- P95 estimeres ud fra histogrammets tidsintervaller; det er ikke en præcis percentil af individuelle kald.
- API-fejlprocenten tæller HTTP 5xx og uventede exceptions. HTTP 4xx registreres særskilt som `client_error`.
- Kildefejl omfatter timeout, HTTP-fejl og ugyldige svardata. CVR 404 registreres særskilt som `not_found`.
- Statistikbanken kan fejle, mens API'et svarer HTTP 200 med `status: partial`. Fejlen ses i kildeprocenten.
- Uden trafik eller tilstrækkelige målinger i perioden kan resultatet være `NaN` eller tomt. Datakilderne overvåges kun ved opslag; der er ingen periodiske kildeprober.

NFR-metrikkerne kan dermed verificeres i Prometheus. Automatisk proaktiv varsling er ikke implementeret.
