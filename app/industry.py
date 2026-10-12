# industry.py huser logikken til at forbinde en virksomheds DB25 branchekode med de historiske DB07 branchekoder. Hertil, identificeres det om disse to koder, kan kombineres til at hente branchestatistikker fra StatBank API'et. Hvis ikke, returneres en forklaring på hvorfor det ikke er muligt.

from decimal import Decimal
import json
import math
from pathlib import Path
import re

from . import statistics

# Indlæser mapningsmatricen mellem DB25 og DB07 fra JSON filen under "data". Hver værdi er enten en liste af DB07 koder, eller None hvis der ikke er en entydig mapping.
def _load_codes() -> dict[str, list[str] | None]:
    data = json.loads((Path(__file__).parent / "data/industry_correspondence.json").read_text(encoding="utf-8"))
    relations = data["relations"]
    if not isinstance(relations, dict) or not relations:
        raise ValueError("Missing industry correspondence")
    # Dette loop verificerer alle DB25 koder og ets relaterede DB07 koder (fra linje 25 vil den omvendte relation ske - dette for at fange, hvis en gammel industri er blevet opdelt i flere nye).
    successors = {}
    for db25, codes in relations.items():
        if (not re.fullmatch(r"[0-9]{6}", db25)
                or not isinstance(codes, list) or not codes
                or any(not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code) for code in codes)
                or len(set(codes)) != len(codes)):
            raise ValueError("Invalid industry correspondence")
        for db07 in codes:
            successors.setdefault(db07, set()).add(db25)
    return {
        db25: sorted(codes) if all(len(successors[code]) == 1 for code in codes) else None
        for db25, codes in relations.items()
    }

# Indlæser den globale mapningsmatrice ved opstart af applikationen (kun én gang). Dette sikrer, at alle DB25 koder er korrekt mappet til deres respektive DB07 koder, og at eventuelle uoverensstemmelser fanges tidligt.
_CODES = _load_codes()

# Tilføjer værdier og bibeholder manglende data - '_sum' accepterer integers, floats og None, og returnerer summen af de tilgængelige værdier. 
def _sum(values: list[int | float | None]) -> int | float | None:
    if any(value is None for value in values):
        return None
    if all(isinstance(value, int) for value in values):
        return sum(values)
    total = sum((Decimal(str(value)) for value in values), Decimal(0))
    if total == total.to_integral_value():
        return int(total)
    result = float(total)
    if not math.isfinite(result):
        raise ValueError("Non-finite industry total")
    return result

# Entry point for filen - 'fetch' henter branchestatistikker for en given DB25 kode og et år. Den returnerer to ting: en dictionary med branchestatistikker eller None hvis data ikke er tilgængelig, efterfulgt af en liste med advarsler, der forklarer eventuelle problemer med dataene.
async def fetch(client, db25: str, year: int) -> tuple[dict | None, list[str]]:
    if db25 not in _CODES:
        return None, ["industry_mapping_unknown"]
    codes = _CODES[db25]
    if codes is None:
        return None, ["industry_mapping_unsupported"]
    branches = await statistics.fetch(client, codes, year)
    totals = {
        field: _sum([branches[code][field] for code in codes])
        for field in statistics.FIELDS.values()
    }
    warnings = ["statistics_values_unavailable"] if any(value is None for value in totals.values()) else []
    return {"year": year, "industry_codes_db07": codes, **totals}, warnings
