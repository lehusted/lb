"""Mock outbound calls: tests never depend on the two public APIs."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, http_client


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def browser():
    def make(handler):
        async def fake_client():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                yield client
        app.dependency_overrides[http_client] = fake_client
        return TestClient(app)
    return make


@pytest.fixture
def sample_company():
    return {
        "vat": 12345678, "name": "Example A/S", "address": "Example Street 1",
        "zipcode": 1000, "city": "Copenhagen", "employees": None,
        "industrycode": 621000,
    }


@pytest.fixture
def mock_mapping(monkeypatch, tmp_path):
    from app import industry
    file = tmp_path / "mapping.csv"
    file.write_text("db25,db07,verified\n621000,620100,true\n", encoding="utf-8")
    monkeypatch.setattr(industry, "MAPPING_FILE", file)
    # The endpoint normally imports to_db07 from industry; it reads MAPPING_FILE at runtime.
    return file
