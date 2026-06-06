import csv
from dataclasses import dataclass
from pathlib import Path


EMSD_TABLE12_FILE = "emsd/energy_end_use_table12.csv"
END_USE_COLUMNS = {
    "air_conditioning": "Air Conditioning Percentage",
    "lighting": "Lighting Percentage",
    "refrigeration": "Refrigeration Percentage",
    "industrial_process_equipment": "Industrial Process/ Equipment Percentage",
    "cooking": "Cooking Percentage",
    "hot_water": "Hot Water Percentage",
    "office_equipment": "Office Equipment Percentage",
    "vertical_transport": "Vertical Transport Percentage",
    "others": "Others Percentage",
}


@dataclass(frozen=True)
class EndUseShares:
    year: int
    shares: dict[str, float]
    source_file: str
    provenance: str = "observed"


def load_end_use_shares(raw_dir: Path) -> list[EndUseShares]:
    path = raw_dir / EMSD_TABLE12_FILE
    records: list[EndUseShares] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            year = _parse_year(row.get("Year", ""))
            if year is None:
                continue
            shares = {
                canonical: _parse_percent(_column(row, prefix))
                for canonical, prefix in END_USE_COLUMNS.items()
            }
            records.append(
                EndUseShares(
                    year=year,
                    shares={key: value for key, value in shares.items() if value is not None},
                    source_file=str(path),
                )
            )
    return records


def _column(row: dict[str, str], english_prefix: str) -> str:
    prefix = english_prefix.lower()
    for key, value in row.items():
        if key.strip().lower().startswith(prefix):
            return (value or "").strip()
    return ""


def _parse_year(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _parse_percent(value: str) -> float | None:
    text = value.replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text) / 100.0
    except ValueError:
        return None
