import json
from pathlib import Path
import subprocess
import sys
import textwrap

import httpx
import pytest
from prometheus_client.parser import text_string_to_metric_families


CSV = (
    "BRANCHE07;TAL;TID;INDHOLD\n"
    "620100;ARBSTED;2024;1234\n"
    "620100;ANSATTE;2024;5678\n"
    "620100;FULDBESK;2024;4500\n"
    "620100;L\u00d8NSUM;2024;123,5\n"
)


def test_enrichment(browser, sample_company, mock_mapping):
    def handle(request):
        if request.url.host == "apicvr.dk":
            return httpx.Response(200, json=sample_company)
        body = json.loads(request.content)
        assert body["table"] == "ERHV1"
        assert body["variables"][0]["values"] == ["620100"]
        return httpx.Response(200, text=CSV)

    with browser(handle) as client:
        response = client.get("/companies/12345678?year=2024")
    assert response.status_code == 200
    result = response.json()
    assert result["company"]["employees"] is None
    assert result["mapping"] == "verified_csv"
    assert result["industry_statistics"]["workplaces"] == 1234
    assert result["industry_statistics"]["payroll_million_dkk"] == 123.5


def test_search_returns_compact_list(browser):
    def handle(request):
        assert "search/company/Novo" in str(request.url)
        return httpx.Response(200, json=[
            {"vat": 12345678, "name": "Novo Example", "status": "NORMAL", "email": "ignore@example.com"},
            {"vat": 87654321, "name": "Novo Old", "status": "Oph\u00f8rt"},
        ])

    with browser(handle) as client:
        response = client.get("/companies?name=Novo")
    assert response.status_code == 200
    assert response.json() == [
        {"cvr": "12345678", "name": "Novo Example", "status": "NORMAL"},
        {"cvr": "87654321", "name": "Novo Old", "status": "Oph\u00f8rt"},
    ]


def test_missing_company_returns_404(browser):
    with browser(lambda request: httpx.Response(404)) as client:
        response = client.get("/companies/12345678?year=2024")
    assert response.status_code == 404


def test_cvr_timeout_returns_504(browser):
    def timeout(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with browser(timeout) as client:
        response = client.get("/companies/12345678?year=2024")
    assert response.status_code == 504


def test_statbank_error_returns_502(browser, sample_company, mock_mapping):
    def handle(request):
        return (httpx.Response(200, json=sample_company) if request.url.host == "apicvr.dk"
                else httpx.Response(503))

    with browser(handle) as client:
        response = client.get("/companies/12345678?year=2024")
    assert response.status_code == 502


def test_unmapped_code_is_rejected(browser, sample_company):
    with browser(lambda request: httpx.Response(200, json=sample_company)) as client:
        response = client.get("/companies/12345678?year=2024")
    assert response.status_code == 422
    assert "No verified" in response.json()["detail"]


@pytest.mark.parametrize("year", [2007, 2025])
def test_unsupported_year_is_rejected(browser, year):
    def should_not_call(request):
        raise AssertionError("Year validation must happen before external requests")

    with browser(should_not_call) as client:
        response = client.get(f"/companies/12345678?year={year}")
    assert response.status_code == 422


def test_manual_override_cannot_bypass_mapping(browser, sample_company):
    with browser(lambda request: httpx.Response(200, json=sample_company)) as client:
        response = client.get("/companies/12345678?year=2024&db07=620100")
    assert response.status_code == 422


def test_metrics_exporter_in_ci(browser):
    with browser(lambda request: httpx.Response(200, json=[])) as client:
        assert client.get("/companies?name=Novo").status_code == 200
        response = client.get("/metrics")
    assert response.status_code == 200
    assert 'api_requests_total{outcome="success",path="/companies"}' in response.text
    assert 'api_request_duration_seconds_bucket{le="0.1",path="/companies"}' in response.text
    assert 'api_request_duration_seconds_bucket{le="30",path="/companies"}' in response.text
    assert 'downstream_request_duration_seconds_bucket{le="5",source="cvr"}' in response.text
    assert 'downstream_request_duration_seconds_bucket{le="+Inf",source="cvr"}' in response.text


def test_enrichment_uses_real_allowlist(browser, sample_company):
    sample_company["industrycode"] = 212000
    csv_text = (Path(__file__).parent / "fixtures" / "erhv1_212000_2024.csv").read_text(encoding="utf-8-sig")

    def handle(request):
        if request.url.host == "apicvr.dk":
            return httpx.Response(200, json=sample_company)
        payload = json.loads(request.content)
        assert payload["variables"][0]["values"] == ["212000"]
        assert payload["valuePresentation"] == "Code"
        assert payload["lang"] == "da"
        return httpx.Response(200, text=csv_text)

    with browser(handle) as client:
        response = client.get("/companies/12345678?year=2024")
    assert response.status_code == 200
    assert response.json()["mapping"] == "verified_csv"
    assert response.json()["industry_statistics"] == {
        "year": 2024, "industry_code_db07": "212000", "workplaces": 135,
        "jobs": 43347, "full_time_employment": 39717, "payroll_million_dkk": 35508,
    }


@pytest.mark.parametrize("field, value", [
    ("industrycode", "invalid"), ("industrycode", True),
    ("employees", "unknown"), ("employees", -1), ("name", None),
    ("address", []), ("vat", 87654321),
])
def test_invalid_company_fields_return_502(browser, sample_company, field, value):
    sample_company[field] = value
    with browser(lambda request: httpx.Response(200, json=sample_company)) as client:
        assert client.get("/companies/12345678?year=2024").status_code == 502


def test_missing_industry_returns_422(browser, sample_company):
    sample_company["industrycode"] = None
    with browser(lambda request: httpx.Response(200, json=sample_company)) as client:
        assert client.get("/companies/12345678?year=2024").status_code == 422


@pytest.mark.parametrize("path, payload", [
    ("/companies/12345678?year=2024", []),
    ("/companies/12345678?year=2024", {}),
    ("/companies?name=Novo", {}), ("/companies?name=Novo", [None]),
    ("/companies?name=Novo", [{"vat": 12345678, "name": None}]),
])
def test_invalid_cvr_payload_returns_502(browser, path, payload):
    with browser(lambda request: httpx.Response(200, json=payload)) as client:
        assert client.get(path).status_code == 502


def count(text, name, **labels):
    return sum(sample.value for family in text_string_to_metric_families(text)
               for sample in family.samples
               if sample.name == name and all(sample.labels.get(k) == v for k, v in labels.items()))


@pytest.mark.parametrize("source, failure, status, outcome", [
    ("cvr", "payload", 502, "error"), ("statbank", "payload", 502, "error"),
    ("statbank", "http", 502, "error"), ("statbank", "timeout", 504, "error"),
    ("statbank", "not_found", 502, "error"), ("cvr", "not_found", 404, "not_found"),
    ("cvr", "timeout", 504, "error"),
])
def test_downstream_failure_metrics(browser, sample_company, mock_mapping, source, failure, status, outcome):
    def handle(request):
        current = "cvr" if request.url.host == "apicvr.dk" else "statbank"
        if current != source:
            return httpx.Response(200, json=sample_company)
        if failure == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if failure == "http":
            return httpx.Response(503)
        if failure == "not_found":
            return httpx.Response(404)
        return httpx.Response(200, text="invalid payload")

    with browser(handle) as client:
        before = client.get("/metrics").text
        assert client.get("/companies/12345678?year=2024").status_code == status
        after = client.get("/metrics").text
    assert count(after, "downstream_requests_total", source=source, outcome=outcome) - count(before, "downstream_requests_total", source=source, outcome=outcome) == 1
    assert count(after, "downstream_requests_total", source=source, outcome="success") == count(before, "downstream_requests_total", source=source, outcome="success")
    assert count(after, "downstream_request_duration_seconds_count", source=source) - count(before, "downstream_request_duration_seconds_count", source=source) == 1
    api_outcome = "error" if status >= 500 else "client_error"
    assert count(after, "api_requests_total", outcome=api_outcome) - count(before, "api_requests_total", outcome=api_outcome) == 1


def test_first_payload_failure_has_zero_counter_baseline():
    # The process-wide MeterProvider needs a fresh process for startup assertions.
    code = textwrap.dedent('''
        import httpx
        from fastapi.testclient import TestClient
        from app.main import app, http_client
        async def fake_client():
            def handle(request):
                if request.url.host == "apicvr.dk":
                    return httpx.Response(200, json={"vat":12345678,"name":"Example","industrycode":212000})
                return httpx.Response(200, text="invalid CSV")
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                yield client
        app.dependency_overrides[http_client] = fake_client
        with TestClient(app) as client:
            before = client.get("/metrics").text
            assert 'downstream_requests_total{outcome="error",source="statbank"} 0.0' in before
            assert 'api_requests_total{outcome="error",path="/companies/{cvr_number}"} 0.0' in before
            assert client.get("/companies/12345678?year=2024").status_code == 502
            after = client.get("/metrics").text
            assert 'downstream_requests_total{outcome="error",source="statbank"} 1.0' in after
            assert 'api_requests_total{outcome="error",path="/companies/{cvr_number}"} 1.0' in after
    ''')
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
