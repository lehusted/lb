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
- **Målinger:** OpenTelemetry eksporterer direkte til Prometheus. Ingen tracing eller Collector.
- **Data:** Ingen database eller cache. Hvert opslag henter data fra de eksterne kilder.
- **Teststrategi:** Fem kernescenarier giver seks testkørsler med syntetiske HTTP-svar. De afprøver den rigtige parsing, branchemapning, sammenlægning og API-kontrakt. To live integrationstests kontrollerer CVR og DST hver for sig og vælges eksplicit, så den daglige testkørsel og CI er uafhængige af datakildernes tilgængelighed.
- **Branchekorrespondance:** `app/industry.py` ejer valget af DB07-kilder og sammenlægningen af deres tal. Modulet indlæser de officielle relationer fra `app/data/industry_correspondence.json` ved opstart. En gammel branche må kun indgå, hvis hele dens aktivitet overgår til den valgte DB25-kode. `app/statistics.py` henter og validerer de valgte kilder i ét HTTP-kald. JSON-filen er projektets eneste lokale branchedatafil; den indeholder også kildeadresse, dato og SHA-256. [Branchemapning](Branchekode-mapnings_problematik.md) forklarer den aktuelle funktionalitet.

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

`pytest.ini` udelader live tests som standard. GitHub Actions kører de seks tests uden netværksadgang og bygger begge Docker-images ved push og pull requests. Efter et bestået build ved push til `main` publiceres backend-imaget til GHCR med `latest` og commit-SHA som tags.

## Kendte problemer og begrænsninger

- **DB25 og DB07:** Den officielle korrespondance, opdateret 26. februar 2026, understøtter 406 verificerede 1:1-relationer og 15 komplette sammenlægninger. De øvrige 317 DB25-koder giver `partial` med `industry_mapping_unsupported` og uden branchestatistik. Dækningen er cirka 57 procent af kodekataloget, ikke af virksomhederne. Tallene er historisk DB07-statistik og eventuelle summer af kildebrancher, ikke en officiel tilbageberegning på DB25. APICVR oplyser ikke et særskilt klassifikationsversionsfelt; aktuelle branchekoder behandles som DB25. Kildeopdateringer foretages manuelt med ny afstemning af relationerne. Originale Excel-filer og midlertidige udtræk opbevares ikke i projektet; ny kontrol mod kilden kræver download fra DST, som kan have erstattet den oprindelige version.
- **Arbejdssteder vs. virksomheder:** Statistikbankens `ARBSTED` opgør arbejdssteder inden for en branche på tværs af virksomheder, ikke antallet af juridiske virksomheder. Løsningen understøtter derfor ikke entydigt antallet af virksomheder for nu (dette vil potentielt kunne udledes via andre datasæt, men vil tage tid).
- **Tidsperioder:** Årsvalget gælder kun statistikken. Virksomhedsdata er aktuelle; medarbejdertallets periode oplyses ikke (`employees_period: null`). Historiske virksomhedsdata understøttes ikke, da det ikke pålideligt kan findes inden for relevante tid (man vil nok godt kunne transformere sig frem via data fra diverse kilder, men det er ikke tiden værd for nu).
- **År og navnesøgning:** API'et accepterer kun 2008–2024. Søgningens match og resultater afhænger af APICVR. Dette primært fordi, at Statistikbanken ikke indeholder data for alle år. `ERHV1` indeholder kun til og med 2024.
- **Kildeafhængighed:** Eksterne kald har fem sekunders timeout pr. forbindelses-, læse-, skrive- og puljeoperation, ikke en samlet deadline. Ingen automatiske genforsøg.
- **Drift og test:** Lokal demo med én API-worker; metrics nulstilles ved genstart. Teststrategien dækker udvalgte kernescenarier og to live integrationer. Øvrige fejl- og valideringsvarianter samt hele branchekataloget er ikke automatisk dækket. Frontend, kandidatvalg ved flere navnematch og metrics kontrolleres manuelt før demo. Publicering dækkes ikke af testene.
