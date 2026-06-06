from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.data_sources.emsd import EndUseShares, load_end_use_shares
from app.data_sources.hk_electric import (
    CustomerTypeConsumption,
    DistrictConsumption,
    load_customer_type_consumption,
    load_district_consumption,
)


SECTORS = ("residential", "commercial", "industrial")
SNAPSHOTS = ("overnight_04h", "shoulder_10h", "peak_16h", "cooling_peak_18h")
COMPLETE_PERIODS = {"first_half", "second_half"}
HOURS_PER_YEAR = 8760.0


@dataclass(frozen=True)
class CalibrationAssumptions:
    sector_load_factors: dict[str, float] = field(
        default_factory=lambda: {
            "residential": 0.45,
            "commercial": 0.55,
            "industrial": 0.70,
        }
    )
    sector_snapshot_multipliers: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "residential": {
                "overnight_04h": 0.70,
                "shoulder_10h": 0.62,
                "peak_16h": 0.88,
                "cooling_peak_18h": 0.92,
            },
            "commercial": {
                "overnight_04h": 0.25,
                "shoulder_10h": 0.82,
                "peak_16h": 1.00,
                "cooling_peak_18h": 1.10,
            },
            "industrial": {
                "overnight_04h": 0.78,
                "shoulder_10h": 0.88,
                "peak_16h": 0.92,
                "cooling_peak_18h": 0.90,
            },
        }
    )
    cooling_air_conditioning_sensitivity: float = 0.35


@dataclass(frozen=True)
class CalibrationBundle:
    source_year: int
    source_periods: list[str]
    is_partial_year: bool
    district_sector_gwh: dict[str, dict[str, float]]
    sector_gwh: dict[str, float]
    sector_shares: dict[str, float]
    end_use_year: int | None
    end_use_shares: dict[str, float]
    average_mw_by_sector: dict[str, float]
    peak_mw_by_sector: dict[str, float]
    snapshot_mw_by_sector: dict[str, dict[str, float]]
    snapshot_total_mw: dict[str, float]
    assumptions: CalibrationAssumptions
    metadata: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_year": self.source_year,
            "source_periods": self.source_periods,
            "is_partial_year": self.is_partial_year,
            "district_sector_gwh": self.district_sector_gwh,
            "sector_gwh": self.sector_gwh,
            "sector_shares": self.sector_shares,
            "end_use_year": self.end_use_year,
            "end_use_shares": self.end_use_shares,
            "average_mw_by_sector": self.average_mw_by_sector,
            "peak_mw_by_sector": self.peak_mw_by_sector,
            "snapshot_mw_by_sector": self.snapshot_mw_by_sector,
            "snapshot_total_mw": self.snapshot_total_mw,
            "assumptions": {
                "sector_load_factors": self.assumptions.sector_load_factors,
                "sector_snapshot_multipliers": self.assumptions.sector_snapshot_multipliers,
                "cooling_air_conditioning_sensitivity": self.assumptions.cooling_air_conditioning_sensitivity,
            },
            "metadata": self.metadata,
            "warnings": self.warnings,
        }


def load_calibration_bundle(
    raw_dir: Path,
    year: int | None = None,
    assumptions: CalibrationAssumptions | None = None,
) -> CalibrationBundle:
    assumptions = assumptions or CalibrationAssumptions()
    district_records = load_district_consumption(raw_dir)
    customer_records = load_customer_type_consumption(raw_dir)
    end_use_records = load_end_use_shares(raw_dir)
    if not customer_records:
        raise ValueError("No HK Electric customer-type consumption records were found.")

    source_year = year if year is not None else _latest_complete_or_available_year(customer_records)
    periods = sorted({record.period for record in customer_records if record.year == source_year})
    selected_customer = [record for record in customer_records if record.year == source_year and record.period in periods]
    selected_district = [record for record in district_records if record.year == source_year and record.period in periods]
    is_partial_year = set(periods) != COMPLETE_PERIODS
    if not selected_customer:
        raise ValueError(f"No HK Electric customer-type consumption records found for year {source_year}.")

    sector_gwh = _sector_totals(selected_customer)
    district_sector_gwh = _district_sector_totals(selected_district)
    total_gwh = sum(sector_gwh.values())
    sector_shares = {sector: round(value / total_gwh, 6) if total_gwh else 0.0 for sector, value in sector_gwh.items()}
    end_use = _latest_end_use(end_use_records, source_year)
    average_mw_by_sector = {
        sector: round(gwh * 1000.0 / HOURS_PER_YEAR, 3)
        for sector, gwh in sector_gwh.items()
    }
    peak_mw_by_sector = {
        sector: round(average_mw_by_sector[sector] / assumptions.sector_load_factors[sector], 3)
        for sector in SECTORS
        if sector in average_mw_by_sector
    }
    snapshot_mw_by_sector = _snapshot_mw_by_sector(peak_mw_by_sector, assumptions, end_use)
    snapshot_total_mw = {
        snapshot: round(sum(sector_values.get(snapshot, 0.0) for sector_values in snapshot_mw_by_sector.values()), 3)
        for snapshot in SNAPSHOTS
    }

    warnings = []
    if is_partial_year:
        warnings.append(f"HK Electric source year {source_year} is partial; available periods: {', '.join(periods)}.")
    warnings.append("CLP territory demand is currently synthetic/inferred until CLP or C&SD data is added.")

    return CalibrationBundle(
        source_year=source_year,
        source_periods=periods,
        is_partial_year=is_partial_year,
        district_sector_gwh=district_sector_gwh,
        sector_gwh={sector: round(value, 3) for sector, value in sector_gwh.items()},
        sector_shares=sector_shares,
        end_use_year=end_use.year if end_use else None,
        end_use_shares=end_use.shares if end_use else {},
        average_mw_by_sector=average_mw_by_sector,
        peak_mw_by_sector=peak_mw_by_sector,
        snapshot_mw_by_sector=snapshot_mw_by_sector,
        snapshot_total_mw=snapshot_total_mw,
        assumptions=assumptions,
        metadata={
            "territory": "hk-electric",
            "provenance": "observed_hk_electric_public_consumption",
            "district_source_file": str(raw_dir / "hk_electric/consumption_by_district_and_customer_type.csv"),
            "customer_type_source_file": str(raw_dir / "hk_electric/consumption_by_customer_type.csv"),
            "end_use_source_file": str(raw_dir / "emsd/energy_end_use_table12.csv"),
        },
        warnings=warnings,
    )


def _latest_complete_or_available_year(records: list[CustomerTypeConsumption]) -> int:
    by_year = {
        record.year: {candidate.period for candidate in records if candidate.year == record.year}
        for record in records
    }
    complete = [year for year, periods in by_year.items() if periods >= COMPLETE_PERIODS]
    return max(complete or by_year)


def _sector_totals(records: list[CustomerTypeConsumption]) -> dict[str, float]:
    totals = {sector: 0.0 for sector in SECTORS}
    for record in records:
        if record.sector in totals:
            totals[record.sector] += record.gwh
    return totals


def _district_sector_totals(records: list[DistrictConsumption]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for record in records:
        totals.setdefault(record.district, {sector: 0.0 for sector in SECTORS})
        totals[record.district][record.sector] += record.gwh
    return {
        district: {sector: round(value, 3) for sector, value in sectors.items()}
        for district, sectors in sorted(totals.items())
    }


def _latest_end_use(records: list[EndUseShares], source_year: int) -> EndUseShares | None:
    eligible = [record for record in records if record.year <= source_year]
    return max(eligible or records, key=lambda record: record.year, default=None)


def _snapshot_mw_by_sector(
    peak_mw_by_sector: dict[str, float],
    assumptions: CalibrationAssumptions,
    end_use: EndUseShares | None,
) -> dict[str, dict[str, float]]:
    air_conditioning_share = (end_use.shares.get("air_conditioning", 0.0) if end_use else 0.0)
    snapshot_values: dict[str, dict[str, float]] = {}
    for sector, peak_mw in peak_mw_by_sector.items():
        snapshot_values[sector] = {}
        for snapshot, multiplier in assumptions.sector_snapshot_multipliers[sector].items():
            adjusted = multiplier
            if snapshot == "cooling_peak_18h":
                adjusted += air_conditioning_share * assumptions.cooling_air_conditioning_sensitivity
            snapshot_values[sector][snapshot] = round(peak_mw * adjusted, 3)
    return snapshot_values
