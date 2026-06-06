import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DISTRICT_FILE = "hk_electric/consumption_by_district_and_customer_type.csv"
CUSTOMER_TYPE_FILE = "hk_electric/consumption_by_customer_type.csv"

SECTOR_LABELS = {
    "residential": "residential",
    "commercial": "commercial",
    "industrial": "industrial",
    "overall": "overall",
}
DISTRICT_LABELS = {
    "central & western": "central_western",
    "eastern": "eastern",
    "wan chai": "wan_chai",
    "southern": "southern",
    "islands (lamma island only)": "lamma",
}
PERIOD_LABELS = {
    "first half": "first_half",
    "second half": "second_half",
}


@dataclass(frozen=True)
class DistrictConsumption:
    year: int
    period: str
    district: str
    sector: str
    gwh: float
    source_file: str
    provenance: str = "observed"


@dataclass(frozen=True)
class CustomerTypeConsumption:
    year: int
    period: str
    sector: str
    gwh: float
    customer_count_thousand: float | None
    average_kwh: float | None
    source_file: str
    provenance: str = "observed"


def load_district_consumption(raw_dir: Path) -> list[DistrictConsumption]:
    path = raw_dir / DISTRICT_FILE
    records: list[DistrictConsumption] = []
    for row in _read_rows(path):
        year = _parse_year(_column(row, "Year"))
        period = _canonical_period(_column(row, "Period"))
        district = _canonical_district(_column(row, "Breakdown by Districts and Customer Type"))
        if year is None or period is None or district is None:
            continue
        for sector in ("residential", "commercial", "industrial"):
            gwh = _parse_number(_column(row, _sector_header_prefix(sector)))
            if gwh is None:
                continue
            records.append(
                DistrictConsumption(
                    year=year,
                    period=period,
                    district=district,
                    sector=sector,
                    gwh=gwh,
                    source_file=str(path),
                )
            )
    return records


def load_customer_type_consumption(raw_dir: Path) -> list[CustomerTypeConsumption]:
    path = raw_dir / CUSTOMER_TYPE_FILE
    records: list[CustomerTypeConsumption] = []
    for row in _read_rows(path):
        year = _parse_year(_column(row, "Year"))
        period = _canonical_period(_column(row, "Period"))
        sector = _canonical_sector(_column(row, "Breakdown By Customer Type"))
        gwh = _parse_number(_column(row, "Consumption"))
        if year is None or period is None or sector is None or gwh is None:
            continue
        records.append(
            CustomerTypeConsumption(
                year=year,
                period=period,
                sector=sector,
                gwh=gwh,
                customer_count_thousand=_parse_number(_column(row, "Number of Customers")),
                average_kwh=_parse_number(_column(row, "Average Consumption")),
                source_file=str(path),
            )
        )
    return records


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [row for row in csv.DictReader(handle) if any((value or "").strip() for value in row.values())]


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


def _parse_number(value: str) -> float | None:
    text = value.replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _english_label(value: str) -> str:
    return re.split(r"[\u3400-\u9fff]", value, maxsplit=1)[0].strip().lower()


def _canonical_period(value: str) -> str | None:
    label = _english_label(value)
    return next((canonical for english, canonical in PERIOD_LABELS.items() if label.startswith(english)), None)


def _canonical_sector(value: str) -> str | None:
    label = _english_label(value)
    return next((canonical for english, canonical in SECTOR_LABELS.items() if label.startswith(english)), None)


def _canonical_district(value: str) -> str | None:
    label = _english_label(value)
    return DISTRICT_LABELS.get(label)


def _sector_header_prefix(sector: str) -> str:
    for english, canonical in SECTOR_LABELS.items():
        if canonical == sector:
            return english.title()
    return sector
