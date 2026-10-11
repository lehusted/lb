"""Curated DB25 -> DB07 mappings; never guess classification conversions."""

import csv
from pathlib import Path

MAPPING_FILE = Path(__file__).resolve().parents[1] / "data" / "db25_to_db07.csv"


def to_db07(db25: str) -> str | None:
    """Return a manually verified 1:1 mapping, or None."""
    with MAPPING_FILE.open(encoding="utf-8", newline="") as source:
        matches = [
            row["db07"]
            for row in csv.DictReader(source)
            if row["db25"] == db25 and row["verified"].lower() == "true"
        ]
    return matches[0] if len(matches) == 1 else None
