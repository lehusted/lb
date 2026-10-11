"""Regressionstest af tidsperioder, statistikkens betydning og årstal."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, http_client


# Alle oplysninger er opdigtede; branchekoden dokumenterer ikke DB25/DB07-mapping.
CSV_HEADER = "BRANCHE07;TAL;TID;INDHOLD\n"
CSV_ROWS = (
    "212000;ARBSTED;{year};0\n"
    "212000;ANSATTE;{year};12\n"
    "212000;FULDBESK;{year};2,5\n"
    "212000;LØNSUM;{year};1.234,5\n"
)


@pytest.fixture(params=["cvr", "name"])
def api(request, monkeypatch):
    """Kør hvert tilfælde via begge ruter med HTTP-svar uden netværksadgang."""
    source = {"csv": CSV_HEADER + CSV_ROWS, "requests": []}

    def respond(outgoing):
        source["requests"].append(outgoing)
        if outgoing.method == "GET" and str(outgoing.url) == "https://apicvr.dk/api/v1/search?name=Testfirma":
            return httpx.Response(200, json=[{"vat": 12345678, "name": "Testfirma"}])
        if outgoing.method == "GET" and str(outgoing.url) == "https://apicvr.dk/api/v1/12345678":
            return httpx.Response(200, json={
                "vat": 12345678, "name": "Testfirma", "address": "Fiktiv testadresse",
                "industrycode": 212000, "employees": 7,
            })
        if outgoing.method == "POST" and str(outgoing.url) == "https://api.statbank.dk/v1/data":
            payload = json.loads(outgoing.content)
            year = next(v["values"][0] for v in payload["variables"] if v["code"] == "TID")
            return httpx.Response(200, text=source["csv"].format(year=year))
        raise AssertionError(f"Uventet eksternt kald: {outgoing.method} {outgoing.url}")

    async def mock_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            yield client

    # monkeypatch gendanner afhængigheden efter hver test, også ved fejl.
    monkeypatch.setitem(app.dependency_overrides, http_client, mock_client)
    route = "/companies/12345678" if request.param == "cvr" else "/companies"
    params = {} if request.param == "cvr" else {"name": "Testfirma"}
    with TestClient(app) as client:
        yield client, route, params, source


@pytest.mark.parametrize("year", [2008, 2024])
def test_successful_response(api, year):
    # Begge grænseår accepteres; firmaoplysninger må ikke blive mærket som historiske.
    client, route, params, source = api
    response = client.get(route, params={**params, "year": year})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["warnings"] == []
    assert data["year"] == year
    assert data["company"]["data_period"] == "current"
    assert data["company"]["employees_period"] is None
    assert data["company"]["employees"] == 7

    # Forskellige tal afslører ombytning af mål; nul og decimaler skal bevares.
    stats = data["industry_statistics"]
    assert stats["year"] == year
    assert stats["workplaces"] == 0
    assert stats["jobs"] == 12
    assert stats["full_time_employment"] == 2.5
    assert stats["payroll_million_dkk"] == 1234.5  # Lønsum forbliver i mio. kr.

    # Kontrollér det faktiske HTTP-payload, så et fast standardår ikke kan skjule sig.
    statbank_calls = [call for call in source["requests"] if call.url.host == "api.statbank.dk"]
    assert len(statbank_calls) == 1
    payload = json.loads(statbank_calls[0].content)
    assert payload["table"] == "ERHV1"
    selections = {v["code"]: v["values"] for v in payload["variables"]}
    assert selections["TID"] == [str(year)]
    assert set(selections["TAL"]) == {"ARBSTED", "ANSATTE", "FULDBESK", "LØNSUM"}


@pytest.mark.parametrize("year", [
    pytest.param("2007", id="foer-perioden"),  # Før det første understøttede år.
    pytest.param("2025", id="efter-perioden"),  # Efter det sidste understøttede år.
    pytest.param("abc", id="tekst"),  # Tekst kan ikke anvendes som årstal.
    pytest.param("2024.5", id="decimaltal"),  # Årstallet skal være et helt tal.
    pytest.param("", id="tomt"),  # En tom parameter er ikke et årstal.
    pytest.param(None, id="mangler"),  # Årstallet er obligatorisk og har ingen standardværdi.
])
def test_invalid_year(api, year):
    # Ugyldige år skal afvises tydeligt, før nogen ekstern datakilde kontaktes.
    client, route, params, source = api
    if year is not None:
        params = {**params, "year": year}
    response = client.get(route, params=params)
    assert response.status_code == 422
    assert any(error["loc"] == ["query", "year"] for error in response.json()["detail"])
    assert source["requests"] == []


@pytest.mark.parametrize("missing", ["empty", "suppressed"])
def test_missing_observations(api, missing):
    # Manglende statistik må hverken blive til nul eller fjerne firmaoplysningerne.
    client, route, params, source = api
    if missing == "empty":
        source["csv"] = CSV_HEADER  # Gyldige kolonnenavne, men ingen observationer.
    else:
        # Kun jobtallet er undertrykt; de øvrige mål skal stadig kunne bruges.
        source["csv"] = CSV_HEADER + CSV_ROWS.replace(";12\n", ";..\n")
    response = client.get(route, params={**params, "year": 2024})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["year"] == 2024
    assert data["company"]["cvr"] == "12345678"
    assert data["company"]["name"] == "Testfirma"
    assert data["company"]["employees"] == 7
    if missing == "empty":
        assert data["industry_statistics"] is None
        assert data["warnings"] == ["statistics_unavailable"]
    else:
        stats = data["industry_statistics"]
        assert stats["year"] == 2024
        assert stats["jobs"] is None
        assert stats["workplaces"] == 0
        assert stats["full_time_employment"] == 2.5
        assert stats["payroll_million_dkk"] == 1234.5
        assert data["warnings"] == ["statistics_values_unavailable"]
