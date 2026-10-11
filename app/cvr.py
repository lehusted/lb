"""Integration with the CVR public API."""

from urllib.parse import quote

from .metrics import measured_request

BASE = "https://apicvr.dk/api/v1"


async def get_company(client, cvr: str) -> dict:
    async with measured_request(client, "GET", f"{BASE}/{cvr}", "cvr") as response:
        company = company_fields(response.json())
        if company["cvr"] != cvr:
            raise ValueError("CVR response does not match the requested company")
        return company


async def search(client, name: str) -> list[dict]:
    async with measured_request(
        client, "GET", f"{BASE}/search/company/{quote(name, safe='')}", "cvr"
    ) as response:
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected CVR search response")
        result = []
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("Unexpected CVR search row")
            vat, name, status = str(row["vat"]), row["name"], row.get("status")
            if (not (vat.isascii() and vat.isdigit() and len(vat) == 8)
                    or not isinstance(name, str) or not name.strip()
                    or (status is not None and not isinstance(status, str))):
                raise ValueError("Invalid CVR search fields")
            result.append({"cvr": vat, "name": name, "status": status})
        return result


def company_fields(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Unexpected CVR company response")
    code = raw.get("industrycode")
    code = str(code).zfill(6) if code is not None else None
    vat, name, employees = str(raw["vat"]), raw["name"], raw.get("employees")
    if (not (vat.isascii() and vat.isdigit() and len(vat) == 8)
            or not isinstance(name, str) or not name.strip()
            or (code is not None and not (code.isascii() and code.isdigit() and len(code) == 6))
            or (employees is not None and (type(employees) is not int or employees < 0))):
        raise ValueError("Invalid CVR company fields")
    address = (raw.get("address"), raw.get("zipcode"), raw.get("city"))
    if any(value is not None and type(value) not in (str, int) for value in address):
        raise ValueError("Invalid CVR address")
    return {
        "cvr": vat,
        "name": name,
        "address": ", ".join(str(v) for v in address if v is not None),
        "industry_code_db25": code,
        "employees": employees,
        "data_period": "current",
    }
