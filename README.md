# LB interviewcase

En MVP med frontend og REST API til virksomhedsopslag via CVR-nummer eller navn. Svaret kombinerer aktuelle virksomhedsoplysninger fra APICVR med branchestatistik fra Danmarks Statistiks ERHV1 for et valgt år.

## Funktion og arbejdsgang

1. Validér CVR-nummer (8 cifre), navn (2–200 tegn) og statistikår (2008–2024).
2. Søg navnet i APICVR, hvis CVR-nummeret ikke er angivet. Flere match kræver, at brugeren vælger en virksomhed.
3. Hent virksomhedens aktuelle navn, adresse, primære branchekode og senest indberettede medarbejdertal.
4. Send branchekoden og det valgte år til ERHV1, og returnér virksomhedsdata og branchestatistik samlet.

Branchestatistikken omfatter arbejdssteder og job ultimo november, fuldtidsbeskæftigede samt årlig lønsum i mio. kr. Tallene gælder hele branchen. Arbejdssteder tæller ikke juridiske virksomheder, og job tæller ikke unikke personer.

Svaret har `status: complete` eller `partial`. Manglende oplysninger bevares som `null`, og `warnings` forklarer årsagen. Nul bevares som nul. Hvis statistikken fejler, returneres de hentede virksomhedsoplysninger stadig med HTTP 200.

## Teknologi og designvalg

- **API:** Python 3.12, FastAPI, Pydantic og httpx. Begge opslagsruter bruger samme funktion.
- **Frontend:** HTML, CSS og JavaScript, serveret af Nginx, som videresender API-kald til FastAPI. Ingen frontend-framework eller buildproces.
- **Drift:** Docker Compose starter API, frontend og Prometheus. API og frontend kører uden root; porte bindes til localhost.
- **Målinger:** OpenTelemetry eksporterer direkte til Prometheus. Ingen tracing eller Collector.
- **Data:** Ingen database eller cache. Hvert opslag henter data fra de eksterne kilder.

## Start projektet

Kræver Docker med Linux-containere og internetadgang til imagebygning og datakilder.

```bash
docker compose up --build
```

| Adresse | Funktion |
| --- | --- |
| http://localhost:8080 | Webside |
| http://localhost:8000/docs | API-dokumentation og svarmodeller |
| http://localhost:8000/health | Kontrol af, at applikationen svarer |
| http://localhost:8000/metrics | Prometheus-metrics |
| http://localhost:9090 | Prometheus og PromQL-forespørgsler |

Stop med Ctrl+C og derefter `docker compose down`.

## API og fejlhåndtering

Begge ruter kræver `year`. Eksempler med `curl.exe` i PowerShell:

```powershell
curl.exe "http://localhost:8000/companies/16500836?year=2024"
curl.exe "http://localhost:8000/companies?name=LB%20Forsikring&year=2024"
```

HTTP 404 betyder intet match; 409 returnerer navnekandidater; 422 betyder ugyldigt input. Fejl hos CVR-kilden giver 502 eller 504 ved timeout.

| Advarsel | Betydning |
| --- | --- |
| `employees_unavailable` | Medarbejdertal mangler |
| `address_unavailable` | Adresse mangler |
| `industry_missing` | Branchekode mangler |
| `statistics_timeout` | Statistikbanken svarer ikke i tide |
| `statistics_unavailable` | Statistikopslag fejler eller giver ugyldige data |
| `statistics_values_unavailable` | Enkelte statistikværdier mangler eller er undertrykt |

## Målinger og udviklingsflow

Prometheus henter metrics hvert femte sekund. API og datakilder måles med kaldtællere og varighedshistogrammer til fejlrater og estimeret P95. Delvise svar tælles særskilt; statistikfejl registreres som kildefejl, selv når API'et svarer 200. `/health` kontrollerer kun applikationen.

Eksisterende regressionstest bruger syntetiske data og simulerede HTTP-svar. Kør dem i et Python 3.12-miljø:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions er konfigureret til at køre test og bygge begge Docker-images ved push og pull requests. Efter et bestået build ved push til `main` publiceres backend-imaget til GHCR med `latest` og commit-SHA som tags.

## Kendte problemer og begrænsninger

- **DB25 og DB07:** CVR-branchekoden sendes direkte til ERHV1 uden verificeret konvertering. Samme kode kan dække forskellige brancher. `complete` bekræfter datatilgængelighed, ikke sammenlignelighed. Der er pt. udfordringer med Danmarks Statistik's branche kode mapning (https://www.dst.dk/da/Statistik/dokumentation/dansk-branchekode-er-gaeldende), hvorfor logikken til at parre disse korrekt, er utilgængelig.
- **Arbejdssteder vs. virksomheder:** Statistikbankens `ARBSTED` opgør arbejdssteder inden for en branche på tværs af virksomheder, ikke antallet af juridiske virksomheder. Løsningen understøtter derfor ikke entydigt antallet af virksomheder for nu (dette vil potentielt kunne udledes via andre datasæt, men vil tage tid).
- **Tidsperioder:** Årsvalget gælder kun statistikken. Virksomhedsdata er aktuelle; medarbejdertallets periode oplyses ikke (`employees_period: null`). Historiske virksomhedsdata understøttes ikke, da det ikke pålideligt kan findes inden for relevante tid (man vil nok godt kunne transformere sig frem via data fra diverse kilder, men det er ikke tiden værd for nu).
- **År og navnesøgning:** API'et accepterer kun 2008–2024. Søgningens match og resultater afhænger af APICVR. Dette primært fordi, at Statistikbanken ikke indeholder data for alle år. `ERHV1` indeholder kun til og med 2024.
- **Kildeafhængighed:** Eksterne kald har fem sekunders timeout pr. forbindelses-, læse-, skrive- og puljeoperation, ikke en samlet deadline. Ingen automatiske genforsøg.
- **Drift og test:** Lokal demo med én API-worker; metrics nulstilles ved genstart. Testene dækker udvalgte scenarier og verificerer hverken live-kilder, branchekonvertering eller publicering.
