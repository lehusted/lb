# To live smokechecks mod CVR og DST - køres eksplicit med pytest -m integration.

import asyncio
import math

import httpx
import pytest

from app import cvr, statistics
from app.models import Company

# Mærker alle testene i filen med 'integration', så de kan køres selektivt med pytest -m integration.
pytestmark = pytest.mark.integration

# Tester CVR integrationen ved at hente en virksomhed med et kendt CVR nummer og validere, at de returnerede data er korrekte og fuldstændige (format mæssigt). OBS: Ingen Mock kald.
def test_cvr():
    async def fetch():
        async with httpx.AsyncClient(timeout=5.0) as client:
            return await cvr.get_company(client, "16500836")

    company = Company.model_validate(asyncio.run(fetch()))
    assert company.cvr == "16500836"
    assert company.name.strip()
    assert company.data_period == "current"

# Tester DST integrationen ved at hente branchestatistikker for kendte DB07 koder og validere, at de returnerede data er korrekte og fuldstændige (format mæssigt). OBS: Ingen Mock kald.
def test_dst():
    async def fetch():
        async with httpx.AsyncClient(timeout=5.0) as client:
            return await statistics.fetch(client, ["620200", "620300"], 2024)

    branches = asyncio.run(fetch())
    assert set(branches) == {"620200", "620300"}
    for values in branches.values():
        assert set(values) == {"workplaces", "jobs", "full_time_employment", "payroll_million_dkk"}
        assert any(value is not None for value in values.values())
        assert all(
            value is None or isinstance(value, (int, float)) and math.isfinite(value)
            for value in values.values()
        )
