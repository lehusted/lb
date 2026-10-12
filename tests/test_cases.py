# test_cases.py huser seks testkørsler af kernelogikken med syntetiske HTTP-svar.

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, http_client


# Fiktive tal; kildekoderne følger projektets dokumenterede 622000-korrespondance.
CSV = (
    "BRANCHE07;TAL;TID;INDHOLD\n"
    "620200;ARBSTED;{year};0\n"
    "620200;ANSATTE;{year};12\n"
    "620200;FULDBESK;{year};2,5\n"
    "620200;LØNSUM;{year};1.234,5\n"
    "620300;ARBSTED;{year};0\n"
    "620300;ANSATTE;{year};8\n"
    "620300;FULDBESK;{year};1,2\n"
    "620300;LØNSUM;{year};10,5\n"
)

# Fælles testopsætning. 
@pytest.fixture
def api(monkeypatch):
    source = {
        "company": {
            "vat": 12345678, "name": "Testfirma", "address": "Fiktiv testadresse",
            "industrycode": 622000, "employees": 7,
        },
        "csv": CSV, "timeout": None, "requests": [],
    }
    # Simurerer eksterne HTTP-kald til CVR og StatBank API'erne. Afhængigt af URL'en returneres et fiktivt svar, eller der simuleres en timeout.
    def respond(outgoing):
        source["requests"].append(outgoing)
        if outgoing.url.host == source["timeout"]:
            raise httpx.ReadTimeout("Fiktiv timeout", request=outgoing)
        if outgoing.method == "GET" and str(outgoing.url) == "https://apicvr.dk/api/v1/search?name=Testfirma":
            return httpx.Response(200, json=[{"vat": 12345678, "name": "Testfirma"}])
        if outgoing.method == "GET" and str(outgoing.url) == "https://apicvr.dk/api/v1/12345678":
            return httpx.Response(200, json=source["company"])
        if outgoing.method == "POST" and str(outgoing.url) == "https://api.statbank.dk/v1/data":
            payload = json.loads(outgoing.content)
            year = next(v["values"][0] for v in payload["variables"] if v["code"] == "TID")
            return httpx.Response(200, text=source["csv"].format(year=year))
        raise AssertionError(f"Uventet eksternt kald: {outgoing.method} {outgoing.url}")
    # Mock klient, der kobler HTTP klienten til ovenstående funktion (respond), og returnerer fiktive svar.
    async def mock_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            yield client
    # Mock klienten sættes ind i FastAPI via dependency injection. 
    monkeypatch.setitem(app.dependency_overrides, http_client, mock_client)
    with TestClient(app) as client:
        yield client, source

# Tester hovedscenariet, hvor alle eksterne kald lykkes, og der returneres fuldstændige data for virksomheden og branchestatistikkerne.
def test_successful_response(api):
    client, source = api
    response = client.get("/companies", params={"name": "Testfirma", "year": 2008})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["warnings"] == []
    assert data["year"] == 2008
    assert data["company"]["cvr"] == "12345678"
    assert data["company"]["name"] == "Testfirma"
    assert data["company"]["industry_code_db25"] == "622000"
    assert data["company"]["data_period"] == "current"
    assert data["company"]["employees_period"] is None
    assert data["company"]["employees"] == 7

    assert data["industry_statistics"] == {
        "year": 2008, "industry_codes_db07": ["620200", "620300"],
        "workplaces": 0, "jobs": 20, "full_time_employment": 3.7,
        "payroll_million_dkk": 1245,
    }
    assert [str(call.url) for call in source["requests"]] == [
        "https://apicvr.dk/api/v1/search?name=Testfirma",
        "https://apicvr.dk/api/v1/12345678",
        "https://api.statbank.dk/v1/data",
    ]
    payload = json.loads(source["requests"][-1].content)
    assert payload["table"] == "ERHV1"
    selections = {v["code"]: v["values"] for v in payload["variables"]}
    assert selections == {
        "BRANCHE07": ["620200", "620300"],
        "TAL": ["ARBSTED", "ANSATTE", "FULDBESK", "LØNSUM"],
        "TID": ["2008"],
    }

# Tester scenariet med manglende værdier - medarbejdertal og statistikværdier er ikke tilgængelige, og der returneres advarsler i responsen.
def test_missing_values(api):
    client, source = api
    source["company"]["employees"] = None
    source["csv"] = CSV.replace(";12\n", ";..\n")
    response = client.get("/companies/12345678", params={"year": 2024})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["year"] == 2024
    assert data["company"]["cvr"] == "12345678"
    assert data["company"]["name"] == "Testfirma"
    assert data["company"]["employees"] is None
    assert data["industry_statistics"] == {
        "year": 2024, "industry_codes_db07": ["620200", "620300"],
        "workplaces": 0, "jobs": None, "full_time_employment": 3.7,
        "payroll_million_dkk": 1245,
    }
    assert data["warnings"] == ["employees_unavailable", "statistics_values_unavailable"]

# Tester scenariet, hvor CVR API'et returnerer en branchekode, som ikke kan mappes til DB07 koder.
def test_unsupported_mapping(api):
    client, source = api
    source["company"]["industrycode"] = 11300  # DB25 011300 har kun delvis korrespondance.
    response = client.get("/companies/12345678", params={"year": 2024})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["company"]["cvr"] == "12345678"
    assert data["company"]["industry_code_db25"] == "011300"
    assert data["industry_statistics"] is None
    assert data["warnings"] == ["industry_mapping_unsupported"]
    assert [call.url.host for call in source["requests"]] == ["apicvr.dk"]

# Tester scenarier, hvor eksterne kald til CVR eller StatBank API'erne fejler med en timeout (appens reaktion på timeout-fejl). 
@pytest.mark.parametrize("host", ["apicvr.dk", "api.statbank.dk"], ids=["cvr", "dst"])
def test_source_timeout(api, host):
    client, source = api
    source["timeout"] = host
    response = client.get("/companies/12345678", params={"year": 2024})
    if host == "apicvr.dk":
        assert response.status_code == 504
        assert response.json()["detail"] == "CVR API timed out"
        assert [call.url.host for call in source["requests"]] == ["apicvr.dk"]
    else:
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert data["year"] == 2024
        assert data["company"]["cvr"] == "12345678"
        assert data["company"]["employees"] == 7
        assert data["industry_statistics"] is None
        assert data["warnings"] == ["statistics_timeout"]
        assert [call.url.host for call in source["requests"]] == ["apicvr.dk", "api.statbank.dk"]

# Tester scenariet, hvor brugeren anmoder om et år, der ligger uden for det tilladte interval (2008-2024).
def test_invalid_year(api):
    client, source = api
    response = client.get("/companies/12345678", params={"year": 2025})
    assert response.status_code == 422
    assert any(error["loc"] == ["query", "year"] for error in response.json()["detail"])
    assert source["requests"] == []
