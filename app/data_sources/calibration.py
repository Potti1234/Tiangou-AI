from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.data_sources.census_statistics import MonthlyElectricityConsumption, load_monthly_electricity_by_user_type
from app.data_sources.emsd import (
    ElectricitySectorConsumption,
    EndUseShares,
    load_electricity_consumption_by_sector,
    load_end_use_shares,
)
from app.data_sources.hk_electric import (
    CustomerTypeConsumption,
    DistrictConsumption,
    load_customer_type_consumption,
    load_district_consumption,
)


HKE_SECTORS = ("residential", "commercial", "industrial")
CALIBRATION_SECTORS = ("residential", "commercial", "industrial", "transport_or_public_services")
SNAPSHOTS = ("overnight_04h", "shoulder_10h", "peak_16h", "cooling_peak_18h")
COMPLETE_PERIODS = {"first_half", "second_half"}
HOURS_PER_YEAR = 8760.0
TRANSPORT_PUBLIC_SERVICES_SECTORS = {"transport", "street_lighting"}


@dataclass(frozen=True)
class CalibrationAssumptions:
    sector_load_factors: dict[str, float] = field(
        default_factory=lambda: {
            "residential": 0.45,
            "commercial": 0.55,
            "industrial": 0.70,
            "transport_or_public_services": 0.60,
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
            "transport_or_public_services": {
                "overnight_04h": 0.62,
                "shoulder_10h": 0.82,
                "peak_16h": 0.92,
                "cooling_peak_18h": 0.96,
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
    hk_total_sector_gwh: dict[str, float]
    hk_total_sector_source: dict[str, Any] | None
    inferred_clp_sector_gwh: dict[str, float]
    inferred_clp_total_gwh: float
    clp_inference_method: str | None
    clp_average_mw_by_sector: dict[str, float]
    clp_peak_mw_by_sector: dict[str, float]
    clp_snapshot_mw_by_sector: dict[str, dict[str, float]]
    clp_snapshot_total_mw: dict[str, float]
    territory_total_validation: dict[str, Any] | None
    monthly_total_validation: dict[str, Any] | None
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
            "hk_total_sector_gwh": self.hk_total_sector_gwh,
            "hk_total_sector_source": self.hk_total_sector_source,
            "inferred_clp_sector_gwh": self.inferred_clp_sector_gwh,
            "inferred_clp_total_gwh": self.inferred_clp_total_gwh,
            "clp_inference_method": self.clp_inference_method,
            "clp_average_mw_by_sector": self.clp_average_mw_by_sector,
            "clp_peak_mw_by_sector": self.clp_peak_mw_by_sector,
            "clp_snapshot_mw_by_sector": self.clp_snapshot_mw_by_sector,
            "clp_snapshot_total_mw": self.clp_snapshot_total_mw,
            "territory_total_validation": self.territory_total_validation,
            "monthly_total_validation": self.monthly_total_validation,
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
    electricity_sector_records = _try_load_electricity_sector_records(raw_dir)
    census_records = _try_load_census_records(raw_dir)
    if not customer_records:
        raise ValueError("No HK Electric customer-type consumption records were found.")

    source_year = year if year is not None else _latest_calibration_year(customer_records, electricity_sector_records)
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
        for sector in HKE_SECTORS
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
    hk_total_sector_gwh, hk_total_sector_source = _hk_total_sector_gwh(electricity_sector_records, source_year)
    inferred_clp_sector_gwh = _inferred_clp_sector_gwh(hk_total_sector_gwh, sector_gwh)
    inferred_clp_total_gwh = round(sum(inferred_clp_sector_gwh.values()), 3)
    clp_inference_method = (
        "hk_total_sector_minus_observed_hk_electric"
        if hk_total_sector_gwh
        else None
    )
    clp_average_mw_by_sector = {
        sector: round(gwh * 1000.0 / HOURS_PER_YEAR, 3)
        for sector, gwh in inferred_clp_sector_gwh.items()
    }
    clp_peak_mw_by_sector = {
        sector: round(clp_average_mw_by_sector[sector] / assumptions.sector_load_factors[sector], 3)
        for sector in CALIBRATION_SECTORS
        if sector in clp_average_mw_by_sector
    }
    clp_snapshot_mw_by_sector = _snapshot_mw_by_sector(clp_peak_mw_by_sector, assumptions, end_use)
    clp_snapshot_total_mw = {
        snapshot: round(sum(sector_values.get(snapshot, 0.0) for sector_values in clp_snapshot_mw_by_sector.values()), 3)
        for snapshot in SNAPSHOTS
    }
    territory_total_validation = _territory_total_validation(
        source_year=source_year,
        hk_total_sector_gwh=hk_total_sector_gwh,
        hke_sector_gwh=sector_gwh,
        inferred_clp_sector_gwh=inferred_clp_sector_gwh,
        census_records=census_records,
    )
    monthly_total_validation = _monthly_total_validation(census_records)
    if clp_inference_method:
        warnings.append("CLP demand inferred from official Hong Kong totals minus observed HK Electric demand. Spatial placement remains inferred from OSM substations.")
    else:
        warnings.append("CLP inference missing public territory totals; synthetic CLP fallback is required.")

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
        hk_total_sector_gwh=hk_total_sector_gwh,
        hk_total_sector_source=hk_total_sector_source,
        inferred_clp_sector_gwh=inferred_clp_sector_gwh,
        inferred_clp_total_gwh=inferred_clp_total_gwh,
        clp_inference_method=clp_inference_method,
        clp_average_mw_by_sector=clp_average_mw_by_sector,
        clp_peak_mw_by_sector=clp_peak_mw_by_sector,
        clp_snapshot_mw_by_sector=clp_snapshot_mw_by_sector,
        clp_snapshot_total_mw=clp_snapshot_total_mw,
        territory_total_validation=territory_total_validation,
        monthly_total_validation=monthly_total_validation,
        assumptions=assumptions,
        metadata={
            "territory": "hk-electric",
            "provenance": "observed_hk_electric_public_consumption",
            "district_source_file": str(raw_dir / "hk_electric/consumption_by_district_and_customer_type.csv"),
            "customer_type_source_file": str(raw_dir / "hk_electric/consumption_by_customer_type.csv"),
            "end_use_source_file": str(raw_dir / "emsd/energy_end_use_table12.csv"),
            "hk_total_sector_source_file": str(raw_dir / "emsd/electricity_consumption_by_sector_table08.csv"),
            "census_validation_source_file": str(raw_dir / "census_statistics/monthly_electricity_gas_by_user_type_915_91201.csv"),
        },
        warnings=warnings,
    )


def _try_load_electricity_sector_records(raw_dir: Path) -> list[ElectricitySectorConsumption]:
    try:
        return load_electricity_consumption_by_sector(raw_dir)
    except (FileNotFoundError, ValueError):
        return []


def _try_load_census_records(raw_dir: Path) -> list[MonthlyElectricityConsumption]:
    try:
        return load_monthly_electricity_by_user_type(raw_dir)
    except (FileNotFoundError, ValueError):
        return []


def _latest_calibration_year(
    customer_records: list[CustomerTypeConsumption],
    electricity_sector_records: list[ElectricitySectorConsumption],
) -> int:
    complete_hke_years = set(_complete_hke_years(customer_records))
    territory_years = {record.year for record in electricity_sector_records}
    common_years = complete_hke_years & territory_years
    return max(common_years) if common_years else _latest_complete_or_available_year(customer_records)


def _complete_hke_years(records: list[CustomerTypeConsumption]) -> list[int]:
    by_year = {
        record.year: {candidate.period for candidate in records if candidate.year == record.year}
        for record in records
    }
    return [year for year, periods in by_year.items() if periods >= COMPLETE_PERIODS]


def _latest_complete_or_available_year(records: list[CustomerTypeConsumption]) -> int:
    by_year = {record.year: {candidate.period for candidate in records if candidate.year == record.year} for record in records}
    complete = [year for year, periods in by_year.items() if periods >= COMPLETE_PERIODS]
    return max(complete or by_year)


def _sector_totals(records: list[CustomerTypeConsumption]) -> dict[str, float]:
    totals = {sector: 0.0 for sector in HKE_SECTORS}
    for record in records:
        if record.sector in totals:
            totals[record.sector] += record.gwh
    return totals


def _district_sector_totals(records: list[DistrictConsumption]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for record in records:
        totals.setdefault(record.district, {sector: 0.0 for sector in HKE_SECTORS})
        totals[record.district][record.sector] += record.gwh
    return {
        district: {sector: round(value, 3) for sector, value in sectors.items()}
        for district, sectors in sorted(totals.items())
    }


def _latest_end_use(records: list[EndUseShares], source_year: int) -> EndUseShares | None:
    eligible = [record for record in records if record.year <= source_year]
    return max(eligible or records, key=lambda record: record.year, default=None)


def _hk_total_sector_gwh(
    records: list[ElectricitySectorConsumption],
    source_year: int,
) -> tuple[dict[str, float], dict[str, Any] | None]:
    selected = [record for record in records if record.year == source_year]
    if not selected:
        return {}, None
    totals = {sector: 0.0 for sector in CALIBRATION_SECTORS}
    source_file = selected[0].source_file
    for record in selected:
        sector = "transport_or_public_services" if record.sector == "transport" else record.sector
        if sector in totals:
            totals[sector] += record.gwh
    return (
        {sector: round(value, 3) for sector, value in totals.items()},
        {
            "source": "emsd_table08_electricity_consumption_by_sector",
            "source_file": source_file,
            "source_year": source_year,
            "unit": "GWh",
            "conversion": "GWh = TJ / 3.6",
        },
    )


def _inferred_clp_sector_gwh(
    hk_total_sector_gwh: dict[str, float],
    hke_sector_gwh: dict[str, float],
) -> dict[str, float]:
    if not hk_total_sector_gwh:
        return {}
    inferred: dict[str, float] = {}
    for sector in CALIBRATION_SECTORS:
        hk_total = hk_total_sector_gwh.get(sector, 0.0)
        hke_total = hke_sector_gwh.get(sector, 0.0)
        inferred[sector] = round(max(hk_total - hke_total, 0.0), 3)
    return inferred


def _territory_total_validation(
    *,
    source_year: int,
    hk_total_sector_gwh: dict[str, float],
    hke_sector_gwh: dict[str, float],
    inferred_clp_sector_gwh: dict[str, float],
    census_records: list[MonthlyElectricityConsumption],
) -> dict[str, Any] | None:
    if not hk_total_sector_gwh:
        return None
    modeled_gwh = round(sum(hke_sector_gwh.values()) + sum(inferred_clp_sector_gwh.values()), 3)
    emsd_gwh = round(sum(hk_total_sector_gwh.values()), 3)
    annual_census = [record for record in census_records if record.month is None and record.user_type == "all_groups"]
    same_year_census = next((record for record in annual_census if record.year == source_year), None)
    reference_census = same_year_census or max(annual_census, key=lambda record: record.year, default=None)
    return {
        "source_year": source_year,
        "modeled_source_energy_gwh": modeled_gwh,
        "emsd_total_gwh": emsd_gwh,
        "emsd_error_pct": _percent_error(modeled_gwh, emsd_gwh),
        "status": "pass" if _percent_error(modeled_gwh, emsd_gwh) <= 1.0 else "warn",
        "census_total_gwh": round(reference_census.gwh, 3) if reference_census else None,
        "census_year": reference_census.year if reference_census else None,
        "census_comparison": "same_year" if same_year_census else "latest_reference_only" if reference_census else "missing",
        "census_error_pct": _percent_error(modeled_gwh, reference_census.gwh) if reference_census else None,
    }


def _monthly_total_validation(records: list[MonthlyElectricityConsumption]) -> dict[str, Any] | None:
    monthly = [record for record in records if record.month is not None and record.user_type == "all_groups"]
    if not monthly:
        return None
    latest_year = max(record.year for record in monthly)
    selected = [record for record in monthly if record.year == latest_year]
    annual_total = sum(record.gwh for record in selected)
    return {
        "source": "census_statistics_table_915_91201",
        "source_year": latest_year,
        "monthly_count": len(selected),
        "monthly_total_gwh": round(annual_total, 3),
        "month_multipliers": {
            record.month: round(record.gwh / (annual_total / len(selected)), 6) if annual_total else 0.0
            for record in selected
        },
    }


def _percent_error(modeled: float, observed: float) -> float:
    if observed == 0.0:
        return 0.0 if modeled == 0.0 else 100.0
    return round(abs(modeled - observed) / observed * 100.0, 6)


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
