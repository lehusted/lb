# LB interviewcase

En MVP med frontend og REST API til virksomhedsopslag via CVR-nummer eller navn. Svaret kombinerer aktuelle virksomhedsoplysninger fra APICVR med branchestatistik fra Danmarks Statistiks ERHV1 for et valgt år.

## Funktion og arbejdsgang

1. Validér CVR-nummer (8 cifre), navn (2–200 tegn) og statistikår (2008–2024).
2. Søg navnet i APICVR, hvis CVR-nummeret ikke er angivet. Flere match kræver, at brugeren vælger en virksomhed.
3. Hent virksomhedens aktuelle navn, adresse, primære branchekode og senest indberettede medarbejdertal.
4. Find dokumenterede DB07-kilder til den aktuelle DB25-kode. Hent dem fra ERHV1 for det valgte år, sammenlæg komplette kildebrancher, og returnér virksomhedsdata og branchestatistik samlet.

Branchestatistikken omfatter arbejdssteder og job ultimo november, fuldtidsbeskæftigede samt årlig lønsum i mio. kr. Tallene gælder hele branchen. Arbejdssteder tæller ikke juridiske virksomheder, og job tæller ikke unikke personer.

Svaret har `status: complete` eller `partial`. Manglende oplysninger bevares som `null`, og `warnings` forklarer årsagen. Nul bevares som nul. Hvis statistikken fejler, returneres de hentede virksomhedsoplysninger stadig med HTTP 200.

## Teknologi og designvalg

- **API:** Python 3.12, FastAPI, Pydantic og httpx. Begge opslagsruter bruger samme funktion.
- **Frontend:** HTML, CSS og JavaScript, serveret af Nginx, som videresender API-kald til FastAPI. Ingen frontend-framework eller buildproces.
- **Drift:** Docker Compose starter API, frontend og Prometheus. API og frontend kører uden root; porte bindes til localhost.
- **Målinger:** OpenTelemetry eksporterer direkte til Prometheus. En enkel HTML/JavaScript-side viser estimeret P95 og fejlprocent for API, CVR og Statistikbanken. Prometheus udfører beregningerne for de seneste fem minutter; Nginx videresender sidens læseforespørgsler. Visningen genbruger de eksisterende containere og kræver ingen ekstra afhængigheder. Ingen tracing eller Collector.
- **Data:** Ingen database eller cache. Hvert opslag henter data fra de eksterne kilder.
- **Teststrategi:** Fem kernescenarier giver seks testkørsler med syntetiske HTTP-svar. De afprøver den rigtige parsing, branchemapning, sammenlægning og API-kontrakt. To live integrationstests kontrollerer CVR og DST hver for sig i et separat CI-job og vælges eksplicit ved lokal kørsel. Build og unit tests er forudsætninger for publicering; integrationstestene er ikke.
- **Branchekorrespondance:** `app/industry.py` ejer valget af DB07-kilder og sammenlægningen af deres tal. Modulet indlæser de officielle relationer fra `app/data/industry_correspondence.json` ved opstart. En gammel branche må kun indgå, hvis hele dens aktivitet overgår til den valgte DB25-kode. `app/statistics.py` henter og validerer de valgte kilder i ét HTTP-kald. JSON-filen er projektets eneste lokale branchedatafil; den indeholder også kildeadresse, dato og SHA-256. [Branchemapning](Branchekode-mapnings_problematik.md) forklarer den aktuelle funktionalitet.

## Start projektet

Kræver Docker med Linux-containere og internetadgang til imagebygning og datakilder.

```bash
docker compose up --build
```

| Adresse | Funktion |
| --- | --- |
| http://localhost:8080 | Webside |
| http://localhost:8080/monitorering.html | Automatisk monitorering af API og datakilder |
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

API-version 0.5.0 bruger `industry_statistics.industry_codes_db07` som en liste med én eller flere kildekoder. Det tidligere enkeltkodefelt `industry_code_db07` er erstattet. Flere koder betyder, at tallene er summeret fra de viste DB07-brancher. Hvis én nødvendig kildeværdi mangler, er summen for det pågældende mål `null`; nul bevares som nul. Svarkontrakten kan ses og prøves i `/docs`.

| Advarsel | Betydning |
| --- | --- |
| `employees_unavailable` | Medarbejdertal mangler |
| `address_unavailable` | Adresse mangler |
| `industry_missing` | Branchekode mangler |
| `industry_mapping_unknown` | Branchekoden findes ikke i det anvendte DB25-katalog; StatBank kontaktes ikke |
| `industry_mapping_unsupported` | Gamle brancher overgår kun delvist til den aktuelle branche; StatBank kontaktes ikke |
| `statistics_timeout` | Statistikbanken svarer ikke i tide |
| `statistics_unavailable` | Statistikopslag fejler eller giver ugyldige data |
| `statistics_values_unavailable` | Enkelte statistikværdier mangler eller er undertrykt |

## Målinger og udviklingsflow

Prometheus henter metrics hvert femte sekund. API og datakilder måles med kaldtællere og varighedshistogrammer til fejlrater og estimeret P95. Delvise svar tælles særskilt; statistikfejl registreres som kildefejl, selv når API'et svarer 200. En udeladt forespørgsel på grund af branchekorrespondancen registreres som et delvist resultat, ikke som en fejlet kilde-request. `/health` kontrollerer kun applikationen.

Åbn **Monitorering** fra forsiden eller gå til http://localhost:8080/monitorering.html. Siden henter automatisk faste Prometheus-forespørgsler cirka hvert femte sekund og viser API'ets opslagsruter samlet samt CVR og Statistikbanken hver for sig. P95 vises i millisekunder og fejlrate i procent for de seneste fem minutter. Tomme eller ikke-finite resultater vises som **Ingen målinger**. Fejl ved opdatering markerer visningen som forældet og bevarer tidspunktet for seneste vellykkede opdatering. Du skal ikke skrive forespørgsler eller køre scripts. [Telemetri og monitorering](telemetri-monitorering.md) beskriver beregninger og fortolkning.

Kør kernelogikkens tests i et Python 3.12-miljø:

```bash
python -m pip install -r requirements.txt pytest==8.4.1
python -m pytest -q
```

`tests/test_cases.py` dækker følgende scenarier med seks testkørsler uden netværksadgang:

| Scenarie | Kontrol |
| --- | --- |
| Succesfuldt navneopslag | Ét match, aktuelle virksomhedsdata, valgt statistikår, dokumenterede DB07-kilder og korrekte summer med nul og danske decimaler |
| Manglende værdier | Medarbejdertal og en sum med en undertrykt kildeværdi bevares som `null`; øvrige tal bevares |
| Delvis branchekorrespondance | Virksomhedsdata bevares; statistik udelades med en forklaring og uden DST-kald |
| Timeout hos CVR og DST | To testkørsler: CVR giver 504; DST giver 200 med delvist svar og bevarede virksomhedsdata |
| Ugyldigt årstal | 422 før eksterne kald |

Kør de to live integrationstests før demo og ved ændringer i integrationerne:

```bash
python -m pytest -q -m integration
```

`tests/test_integrations.py` henter en kendt juridisk virksomhed fra CVR og DB07-brancherne `620200` og `620300` for 2024 fra DST. Testene kontrollerer gyldige normaliserede svar og brugbare statistikværdier frem for faste aktuelle virksomhedsoplysninger eller statistikværdier. CVR-svar gemmes ikke som fixtures. Kilde- og netværksfejl får disse tests til at fejle.

`pytest.ini` udelader live tests som standard ved lokal kørsel. GitHub Actions starter tre uafhængige jobs ved push og pull requests: **Byg** bygger begge Docker-images, **Unit tests** kører de seks testkørsler i `tests/test_cases.py` uden eksterne API-kald, og **Integrationstests** kører de to live tests i `tests/test_integrations.py`. Det fjerde job, **Publicer image**, publicerer backend-imaget til GHCR med `latest` og commit-SHA som tags ved push til `main`, når Byg og Unit tests er bestået. Integrationstestene kan fejle og gøre det samlede workflow rødt, uden at de øvrige jobs eller publicering blokeres.

## Kendte problemer og begrænsninger

- **DB25 og DB07:** Understøtter 406 verificerede 1:1-relationer og 15 komplette sammenlægninger. De øvrige 317 DB25-koder giver `partial` med `industry_mapping_unsupported` og uden branchestatistik. APICVR oplyser ikke et særskilt klassifikationsversionsfelt - aktuelle branchekoder behandles som DB25. Kildeopdateringer foretages manuelt med ny afstemning af relationerne.
- **Arbejdssteder vs. virksomheder:** Statistikbankens `ARBSTED` opgør arbejdssteder inden for en branche på tværs af virksomheder, ikke antallet af juridiske virksomheder. Løsningen understøtter derfor ikke entydigt antallet af virksomheder for nu (dette vil potentielt kunne udledes via andre datasæt, men vil tage tid).
- **Tidsperioder:** Årsvalget gælder kun statistikken. Virksomhedsdata er aktuelle; medarbejdertallets periode oplyses ikke (`employees_period: null`). Historiske virksomhedsdata understøttes ikke, da det ikke pålideligt kan findes inden for relevante tid (man vil nok godt kunne transformere sig frem via data fra diverse kilder, men det er ikke tiden værd for nu).
- **År og navnesøgning:** API'et accepterer kun 2008–2024. Søgningens match og resultater afhænger af APICVR. Dette primært fordi, at Statistikbanken ikke indeholder data for alle år. `ERHV1` indeholder kun til og med 2024.
- **Kildeafhængighed:** Eksterne kald har fem sekunders timeout pr. forbindelses-, læse-, skrive- og puljeoperation, ikke en samlet deadline. Ingen automatiske genforsøg.
- **Monitorering:** Visningen viser et estimeret P95 fra histogrammer, ikke individuelle svartider. Datakilder måles kun ved opslag; der er ingen periodiske kildeprober eller automatiske alarmer. API-status viser, om Prometheus kan hente metrikker, og siger ikke, at datakilderne er tilgængelige. Uden trafik eller tilstrækkelige målinger i perioden vises **Ingen målinger**. Forældede tal markeres tydeligt ved opdateringsfejl.
- **Drift og test:** Lokal demo med én API-worker; metrics nulstilles ved genstart. Teststrategien dækker udvalgte kernescenarier og to live integrationer. Integrationstestene afhænger af datakildernes tilgængelighed og netværket; et publiceret image kan derfor have fejlede live tests i CI. Øvrige fejl- og valideringsvarianter samt hele branchekataloget er ikke automatisk dækket. Frontend, kandidatvalg ved flere navnematch og metrics kontrolleres manuelt før demo. Publicering dækkes ikke af testene.
