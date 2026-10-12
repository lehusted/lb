# cvr.py er applikationens eksterne integration med CVR API'et. 

from .metrics import measured_request

#Eksterne API endpoint
BASE = "https://apicvr.dk/api/v1"

# Denne funktion henter virksomheds data for et specifikt CVR nummer. Den validerer responsen og konverterer den til et standardiseret format.
async def get_company(client, cvr: str) -> dict:
    async with measured_request(client, "GET", f"{BASE}/{cvr}", "cvr") as response:
        company = company_fields(response.json())
        if company["cvr"] != cvr:
            raise ValueError("CVR response does not match the requested company")
        return company

# Denne funktion søger efter virksomheder baseret på et navn. Den validerer responsen og returnerer en liste af kandidater, som matcher navnet.
async def search(client, name: str) -> list[dict]:
    async with measured_request(
        client, "GET", f"{BASE}/search", "cvr", params={"name": name}
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

# Denne funktion validerer og konverterer rå data fra CVR API'et til et standardiseret format, som bruges i resten af applikationen. Den sikrer, at alle nødvendige felter er til stede og korrekt formateret.
def company_fields(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Unexpected CVR company response")
    code = raw.get("industrycode")
    code = str(code).zfill(6) if code is not None else None
    vat, name, employees = str(raw["vat"]), raw["name"], raw.get("employees")
    # Validerer virksomheden stamdata/felter
    if (not (vat.isascii() and vat.isdigit() and len(vat) == 8)
            or not isinstance(name, str) or not name.strip()
            or (code is not None and not (code.isascii() and code.isdigit() and len(code) == 6))
            or (employees is not None and (type(employees) is not int or employees < 0))):
        raise ValueError("Invalid CVR company fields")
    # Sikrer at adressefelterne er korrekt formateret og valideret, og sammensætter dem til en enkelt adresse streng.
    address = (raw.get("address"), raw.get("zipcode"), raw.get("city"))
    if any(value is not None and type(value) not in (str, int) for value in address):
        raise ValueError("Invalid CVR address")
    address = [str(value).strip() for value in address if value is not None]
    # Konstruerer og returnerer det standardiserede dictionary (dict) med virksomhedens data, som bruges i resten af applikationen.
    return {
        "cvr": vat,
        "name": name,
        "address": ", ".join(value for value in address if value) or None,
        "industry_code_db25": code,
        "employees": employees,
        "data_period": "current",
    }
