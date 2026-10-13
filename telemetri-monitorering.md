# Verificér NFR: telemetri og monitorering

OpenTelemetry registrerer kald og varigheder i [app/metrics.py](app/metrics.py#L14). Prometheus henter målingerne hvert femte sekund og beregner P95 og fejlprocent ved forespørgsel. En enkel monitoreringsside viser resultaterne automatisk. Der er ingen gemte recording rules eller alarmer.

## Fremgangsmåde

1. Start projektet med `docker compose up --build`.
2. Åbn **Monitorering** fra [forsiden](http://localhost:8080) eller gå til [monitoreringssiden](http://localhost:8080/monitorering.html). Siden opdaterer automatisk cirka hvert femte sekund. API-status skal vise **API-metrikker kan hentes**.
3. Brug applikationen normalt. For at se målinger i en demo kan du lave flere virksomhedsopslag med 5–10 sekunders mellemrum. Vælg også en virksomhed, hvor svaret indeholder branchestatistik, så Statistikbanken faktisk kaldes.
4. Se P95 i millisekunder og fejlrate i procent for API, CVR og Statistikbanken. Siden viser de seneste fem minutter og kræver ingen manuelle scripts eller forespørgsler. Før der er trafik og tilstrækkelige målinger, vises **Ingen målinger**.

Hvis en opdatering fejler, markeres visningen som forældet, tidspunktet for seneste vellykkede opdatering bevares, og siden forsøger automatisk igen. Hvis Prometheus kan svare, men ikke kan hente API'ets metrikker, vises det særskilt; eventuelle tal viser tidligere kald i perioden. API-status er en kontrol af metrikindsamlingen, ikke af datakildernes tilgængelighed.

## Faste beregninger

Siden udfører nedenstående fire metrikforespørgsler og `up{job="lb-interview-case"}` for API-status. Prometheus beregner P95 i sekunder; siden omregner til millisekunder. Ved behov kan forespørgslerne også inspiceres i [Prometheus](http://localhost:9090/query), og rå målinger findes på [API'ets /metrics](http://localhost:8000/metrics).

**API: estimeret P95 i sekunder for opslagsruterne samlet**

```promql
histogram_quantile(0.95,
  sum by (le) (rate(api_request_duration_seconds_bucket{job="lb-interview-case",path=~"/companies.*"}[5m]))
)
```

**API: fejlprocent for opslagsruterne samlet**

```promql
100 *
sum(rate(api_requests_total{job="lb-interview-case",path=~"/companies.*",outcome="error"}[5m]))
/
sum(rate(api_requests_total{job="lb-interview-case",path=~"/companies.*"}[5m]))
```

**Datakilder: estimeret P95 i sekunder pr. kilde (`cvr` og `statbank`)**

```promql
histogram_quantile(0.95,
  sum by (le, source) (rate(downstream_request_duration_seconds_bucket{job="lb-interview-case"}[5m]))
)
```

**Datakilder: fejlprocent pr. kilde**

```promql
100 * sum by (source) (rate(downstream_requests_total{job="lb-interview-case",outcome="error"}[5m]))
/
sum by (source) (rate(downstream_requests_total{job="lb-interview-case"}[5m]))
```

## Fortolkning

- P95 estimeres ud fra histogrammets tidsintervaller; det er ikke en præcis percentil af individuelle kald.
- API-fejlprocenten tæller HTTP 5xx og uventede exceptions. HTTP 4xx registreres særskilt som `client_error`.
- Kildefejl omfatter timeout, HTTP-fejl og ugyldige svardata. CVR 404 registreres særskilt som `not_found`.
- Statistikbanken kan fejle, mens API'et svarer HTTP 200 med `status: partial`. Fejlen ses i kildeprocenten.
- Uden trafik eller tilstrækkelige målinger i perioden kan resultatet være `NaN` eller tomt. Datakilderne overvåges kun ved opslag; der er ingen periodiske kildeprober.

NFR-metrikkerne kan dermed følges automatisk i monitoreringssiden. Automatisk proaktiv varsling er ikke implementeret.
