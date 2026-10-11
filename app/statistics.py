"""ERHV1 HTTP request and CSV-to-JSON transformation."""

import csv
from decimal import Decimal
import io
import math
import re

from .metrics import measured_request

URL = "https://api.statbank.dk/v1/data"
FIELDS = {
    "ARBSTED": "workplaces",
    "ANSATTE": "jobs",
    "FULDBESK": "full_time_employment",
    "L\u00d8NSUM": "payroll_million_dkk",
}


def metric_name(text: str) -> str | None:
    label = text.strip().upper()
    if label in FIELDS:
        return FIELDS[label]
    return {
        "arbejdssteder ultimo november": "workplaces",
        "job ultimo november": "jobs",
        "fuldtidsbesk\u00e6ftigede": "full_time_employment",
        "\u00e5rlig l\u00f8nsum (mio. kr)": "payroll_million_dkk",
        "\u00e5rlig l\u00f8nsum (mio. kr.)": "payroll_million_dkk",
    }.get(label.casefold())


def number(value: str) -> int | float | None:
    text = value.strip().replace("\u00a0", " ")
    if text in ("", "..", ":", "-", "..."):
        return None
    # Danish CSV uses decimal commas; dots/spaces are thousands separators.
    if not re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]{1,3}(?: [0-9]{3})+)(?:,[0-9]+)?", text):
        raise ValueError("Invalid Danish number")
    text = text.replace(".", "").replace(" ", "")
    if "," not in text:
        return int(text)
    decimal = Decimal(text.replace(",", "."))
    if decimal == decimal.to_integral_value():
        return int(decimal)
    result = float(decimal)
    if not math.isfinite(result):
        raise ValueError("Non-finite ERHV1 value")
    return result


def parse_csv(text: str, db07: str, year: int) -> dict:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";", strict=True)
    try:
        if len(reader.fieldnames or []) != 4 or set(reader.fieldnames) != {"BRANCHE07", "TAL", "TID", "INDHOLD"}:
            raise ValueError("Unexpected ERHV1 CSV headers")
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError("Malformed ERHV1 CSV") from exc
    result = {name: None for name in FIELDS.values()}
    found = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Incomplete ERHV1 CSV row")
        if row["BRANCHE07"].split(" ", 1)[0] != db07 or row["TID"] != str(year):
            raise ValueError("ERHV1 response does not match the requested industry/year")
        key = metric_name(row["TAL"])
        if key is None:
            raise ValueError("Unknown ERHV1 metric")
        if key in found:
            raise ValueError("Duplicate ERHV1 metric")
        found.add(key)
        result[key] = number(row["INDHOLD"])
    if found != set(FIELDS.values()):
        raise ValueError("ERHV1 is missing requested metrics")
    return result


async def fetch(client, db07: str, year: int) -> dict:
    payload = {
        "table": "ERHV1", "format": "CSV", "lang": "da", "valuePresentation": "Code",
        "variables": [
            {"code": "BRANCHE07", "values": [db07]},
            {"code": "TAL", "values": list(FIELDS)},
            {"code": "TID", "values": [str(year)]},
        ],
    }
    async with measured_request(client, "POST", URL, "statbank", json=payload) as response:
        return {"year": year, "industry_code_db07": db07, **parse_csv(response.text, db07, year)}
