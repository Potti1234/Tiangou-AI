import csv
from dataclasses import dataclass
from pathlib import Path

from app.data_sources.emsd import TJ_PER_GWH


CENSUS_MONTHLY_ELECTRICITY_FILE = "census_statistics/monthly_electricity_gas_by_user_type_915_91201.csv"
MONTHS = {
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
}
USER_TYPE_COLUMNS = {
    "residential": 2,
    "commercial": 3,
    "industrial": 4,
    "street_lighting": 5,
    "all_groups": 6,
}


@dataclass(frozen=True)
class MonthlyElectricityConsumption:
    year: int
    month: str | None
    user_type: str
    tj: float
    gwh: float
    source_file: str
    provenance: str = "observed"


def load_monthly_electricity_by_user_type(raw_dir: Path) -> list[MonthlyElectricityConsumption]:
    path = raw_dir / CENSUS_MONTHLY_ELECTRICITY_FILE
    records: list[MonthlyElectricityConsumption] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if len(row) < 7:
                continue
            year = _parse_year(row[0])
            if year is None:
                continue
            month = _parse_month(row[1])
            if row[1].strip() and month is None:
                continue
            for user_type, index in USER_TYPE_COLUMNS.items():
                tj = _parse_number(row[index])
                if tj is None:
                    continue
                records.append(
                    MonthlyElectricityConsumption(
                        year=year,
                        month=month,
                        user_type=user_type,
                        tj=tj,
                        gwh=round(tj / TJ_PER_GWH, 6),
                        source_file=str(path),
                    )
                )
    return records


def _parse_year(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_month(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    return text if text in MONTHS else None


def _parse_number(value: str) -> float | None:
    text = value.replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
