# Fra virksomhedssøgning til resultat

Happy path: `Testfirma` giver ét match, og alle tal kan hentes for 2024. Eksempeldata er fiktive; CVR-svarene viser de felter, appen bruger. Virksomhedsdata er aktuelle; årstallet gælder branchestatistikken. GET-kald har ingen request-body.

## 1. Browser → Nginx → FastAPI

**Request:** Brugeren indtaster `Testfirma` og `2024`. Frontend trimmer navnet, validerer formularen og sender:

```http
GET http://localhost:8080/api/companies?name=Testfirma&year=2024
```

Nginx fjerner `/api/`-præfikset og videresender de samme query-parametre:

```http
GET http://app:8000/companies?name=Testfirma&year=2024
```

**Behandling:** FastAPI trimmer og validerer navnet (2–200 tegn) og konverterer/validerer årstallet (heltal, 2008–2024). Frontend viser “Henter virksomhedsoplysninger og branchestatistik…” og deaktiverer formularen under opslaget.

**Response:** Det samlede HTTP 200-svar i trin 5 returneres gennem Nginx med samme JSON-body.

## 2. FastAPI → APICVR: navnesøgning

**Request:** Kun navnet sendes til APICVR:

```http
GET https://apicvr.dk/api/v1/search?name=Testfirma
```

**Response — HTTP 200, JSON:**

```json
[{"vat": 12345678, "name": "Testfirma", "status": "AKTIV"}]
```

**Behandling:** Appen validerer kandidatfelterne og omdanner `vat` til `cvr: "12345678"`. Det ene match bruges til virksomhedsopslaget; kandidatlisten returneres ikke særskilt til browseren.

## 3. FastAPI → APICVR: virksomhedsoplysninger

**Request:** CVR-nummeret fra søgningen bruges i URL'en:

```http
GET https://apicvr.dk/api/v1/12345678
```

**Response — HTTP 200, JSON:**

```json
{
  "vat": 12345678, "name": "Testfirma",
  "address": "Fiktivvej 1", "zipcode": "0000", "city": "Testby",
  "industrycode": 212000, "employees": 7
}
```

**Behandling:** CVR-nummeret kontrolleres mod det forespurgte nummer. Felter valideres, adressedele trimmes og samles med kommaer. Branchekoden bliver den sekscifrede streng `"212000"`; virksomhedsdata mærkes `data_period: "current"`. Felterne indgår i `company` i trin 5.

## 4. FastAPI → Statistikbanken: branchestatistik

**Request:** Branchekoden fra CVR bruges uændret som `BRANCHE07`; det valgte år sendes som `TID`.

```http
POST https://api.statbank.dk/v1/data
Content-Type: application/json
```

```json
{
  "table": "ERHV1", "format": "CSV", "lang": "da", "valuePresentation": "Code",
  "variables": [
    {"code": "BRANCHE07", "values": ["212000"]},
    {"code": "TAL", "values": ["ARBSTED", "ANSATTE", "FULDBESK", "LØNSUM"]},
    {"code": "TID", "values": ["2024"]}
  ]
}
```

**Response — HTTP 200, semikolonsepareret CSV:**

```csv
BRANCHE07;TAL;TID;INDHOLD
212000;ARBSTED;2024;50
212000;ANSATTE;2024;1200
212000;FULDBESK;2024;1.000,5
212000;LØNSUM;2024;1.234,5
```

**Behandling:** Appen kontrollerer kolonner, branchekode, år og én række for hvert af de fire mål. Danske tal omdannes til JSON-tal (`1.234,5` → `1234.5`). `ARBSTED`, `ANSATTE`, `FULDBESK` og `LØNSUM` bliver henholdsvis `workplaces`, `jobs`, `full_time_employment` og `payroll_million_dkk` i trin 5.

## 5. FastAPI → Nginx → browser: samlet resultat

**Request:** `GET /api/companies?name=Testfirma&year=2024` fra trin 1; dette er svaret på samme kald.

**Behandling:** Appen samler virksomhedsdata og statistik i `LookupResult`, som valideres og serialiseres til JSON. Resultatet får `status: "complete"` og `warnings: []`. `employees_period` får standardværdien `null`, da APICVR ikke oplyser perioden.

**Response — HTTP 200, JSON:**

```json
{
  "year": 2024, "status": "complete",
  "company": {
    "cvr": "12345678", "name": "Testfirma",
    "address": "Fiktivvej 1, 0000, Testby",
    "industry_code_db25": "212000", "employees": 7,
    "employees_period": null, "data_period": "current"
  },
  "industry_statistics": {
    "year": 2024, "industry_code_db07": "212000",
    "workplaces": 50, "jobs": 1200,
    "full_time_employment": 1000.5, "payroll_million_dkk": 1234.5
  },
  "warnings": []
}
```

## 6. Browser: udstilling på websiden

**Input:** JSON-svaret fra trin 5 læses med `response.json()` og gives til `showResult()`.

**Behandling:** Frontend skriver felterne med `textContent`, formaterer tal med `da-DK`, viser resultatet og aktiverer formularen igen. Navnet får fokus, og status bliver “Virksomhedsoplysninger og branchestatistik er hentet.”

**Output:** Virksomhedsnavn, CVR, adresse, DB25-branchekode og 7 senest indberettede ansatte vises sammen med:

| Branchestatistik · 2024 | Vist værdi |
| --- | --- |
| Branche (DB07) | 212000 |
| Arbejdssteder ultimo november | 50 |
| Job ultimo november | 1.200 |
| Fuldtidsbeskæftigede | 1.000,5 |
| Årlig lønsum (mio. kr.) | 1.234,5 |
