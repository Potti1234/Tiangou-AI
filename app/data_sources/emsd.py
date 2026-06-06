import csv
from dataclasses import dataclass
from pathlib import Path


EMSD_TABLE12_FILE = "emsd/energy_end_use_table12.csv"
EMSD_TABLE08_FILE = "emsd/electricity_consumption_by_sector_table08.csv"
TJ_PER_GWH = 3.6
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
ELECTRICITY_SECTOR_COLUMNS = {
    "residential": "Residential",
    "commercial": "Commercial",
    "industrial": "Industrial",
    "transport": "Transport",
}


@dataclass(frozen=True)
class EndUseShares:
    year: int
    shares: dict[str, float]
    source_file: str
    provenance: str = "observed"


@dataclass(frozen=True)
class ElectricitySectorConsumption:
    year: int
    sector: str
    tj: float
    gwh: float
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


def load_electricity_consumption_by_sector(raw_dir: Path) -> list[ElectricitySectorConsumption]:
    path = raw_dir / EMSD_TABLE08_FILE
    records: list[ElectricitySectorConsumption] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            year = _parse_year(row.get("Year", ""))
            if year is None:
                continue
            for sector, prefix in ELECTRICITY_SECTOR_COLUMNS.items():
                tj = _parse_number(_column(row, f"{prefix} (Unit : Terajoule)"))
                if tj is None:
                    continue
                records.append(
                    ElectricitySectorConsumption(
                        year=year,
                        sector=sector,
                        tj=tj,
                        gwh=round(tj / TJ_PER_GWH, 6),
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


def _parse_number(value: str) -> float | None:
    text = value.replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
