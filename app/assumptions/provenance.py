from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class ProvenanceClass(StrEnum):
    OBSERVED_PUBLIC = "observed_public"
    INFERRED_FROM_PUBLIC_STATISTICS = "inferred_from_public_statistics"
    SYNTHETIC_ENGINEERING_DEFAULT = "synthetic_engineering_default"


REQUIRED_PROVENANCE_COLUMNS = (
    "unit",
    "source",
    "provenance",
    "confidence",
    "method",
    "assumptions",
    "date_or_year",
)


@dataclass(frozen=True)
class AssumptionTable:
    key: str
    category: str
    path: Path
    required_columns: tuple[str, ...]
    value_columns: tuple[str, ...] = ()


ASSUMPTIONS_ROOT = Path("data/assumptions")


ASSUMPTION_TABLES: tuple[AssumptionTable, ...] = (
    AssumptionTable(
        key="line_thermal_rating_defaults",
        category="lines",
        path=ASSUMPTIONS_ROOT / "line_thermal_rating_defaults.csv",
        required_columns=(
            "asset_type",
            "voltage_kv",
            "location_class",
            "circuits_min",
            "circuits_max",
            "rate_mva_per_circuit",
            "emergency_factor",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("rate_mva_per_circuit", "emergency_factor"),
    ),
    AssumptionTable(
        key="cable_impedance_defaults",
        category="lines",
        path=ASSUMPTIONS_ROOT / "cable_impedance_defaults.csv",
        required_columns=(
            "asset_type",
            "voltage_kv",
            "location_class",
            "r_ohm_per_km",
            "x_ohm_per_km",
            "c_nf_per_km",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km"),
    ),
    AssumptionTable(
        key="overhead_line_impedance_defaults",
        category="lines",
        path=ASSUMPTIONS_ROOT / "overhead_line_impedance_defaults.csv",
        required_columns=(
            "asset_type",
            "voltage_kv",
            "location_class",
            "r_ohm_per_km",
            "x_ohm_per_km",
            "c_nf_per_km",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km"),
    ),
    AssumptionTable(
        key="transformer_capacity_defaults",
        category="transformers",
        path=ASSUMPTIONS_ROOT / "transformer_capacity_defaults.csv",
        required_columns=(
            "primary_kv",
            "secondary_kv",
            "facility_class",
            "sn_mva_default",
            "x_pu",
            "r_pu",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("sn_mva_default", "x_pu", "r_pu"),
    ),
    AssumptionTable(
        key="transformer_tap_defaults",
        category="transformers",
        path=ASSUMPTIONS_ROOT / "transformer_tap_defaults.csv",
        required_columns=(
            "primary_kv",
            "secondary_kv",
            "facility_class",
            "tap_side",
            "tap_neutral",
            "tap_min",
            "tap_max",
            "tap_step_percent",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("tap_neutral", "tap_min", "tap_max", "tap_step_percent"),
    ),
    AssumptionTable(
        key="hong_kong_sector_hourly_profiles",
        category="demand_profiles",
        path=ASSUMPTIONS_ROOT / "demand_profiles" / "hong_kong_sector_hourly_profiles.csv",
        required_columns=(
            "profile_id",
            "hour",
            "sector",
            "base_share",
            "weekday_factor",
            "weekend_factor",
            "cooling_sensitivity",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("base_share", "weekday_factor", "weekend_factor", "cooling_sensitivity"),
    ),
    AssumptionTable(
        key="weather_sensitivity_profiles",
        category="demand_profiles",
        path=ASSUMPTIONS_ROOT / "demand_profiles" / "weather_sensitivity_profiles.csv",
        required_columns=(
            "profile_id",
            "sector",
            "temperature_c",
            "humidity_percent",
            "load_multiplier",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("temperature_c", "humidity_percent", "load_multiplier"),
    ),
    AssumptionTable(
        key="data_center_site_assumptions",
        category="data_centers",
        path=ASSUMPTIONS_ROOT / "data_centers" / "data_center_site_assumptions.csv",
        required_columns=(
            "site_id",
            "name",
            "lat",
            "lon",
            "estimated_it_mw",
            "estimated_facility_mw",
            "pue",
            "floor_area_method",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("estimated_it_mw", "estimated_facility_mw", "pue"),
    ),
    AssumptionTable(
        key="generator_cost_availability_defaults",
        category="generators",
        path=ASSUMPTIONS_ROOT / "generators" / "generator_cost_availability_defaults.csv",
        required_columns=(
            "energy_source",
            "variable_cost_usd_per_mwh",
            "startup_cost_usd",
            "availability_factor",
            "forced_outage_rate",
            "co2_t_per_mwh",
            "pmin_fraction",
            "ramp_rate_mw_per_min",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=(
            "variable_cost_usd_per_mwh",
            "startup_cost_usd",
            "availability_factor",
            "forced_outage_rate",
            "co2_t_per_mwh",
            "pmin_fraction",
            "ramp_rate_mw_per_min",
        ),
    ),
    AssumptionTable(
        key="generator_dispatch_merit_order",
        category="generators",
        path=ASSUMPTIONS_ROOT / "generators" / "generator_dispatch_merit_order.csv",
        required_columns=("dispatch_priority", "energy_source", "cost_class", *REQUIRED_PROVENANCE_COLUMNS),
        value_columns=("dispatch_priority",),
    ),
    AssumptionTable(
        key="synthetic_contingency_library",
        category="contingencies",
        path=ASSUMPTIONS_ROOT / "contingencies" / "synthetic_contingency_library.csv",
        required_columns=(
            "contingency_id",
            "type",
            "target_selector",
            "probability_class",
            "duration_class",
            "severity",
            "reason",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("severity",),
    ),
    AssumptionTable(
        key="cross_border_import_limits",
        category="imports",
        path=ASSUMPTIONS_ROOT / "imports" / "cross_border_import_limits.csv",
        required_columns=(
            "boundary_id",
            "from_region",
            "to_region",
            "nominal_mw",
            "emergency_mw",
            "derate_scenarios",
            "availability",
            "cost_class",
            *REQUIRED_PROVENANCE_COLUMNS,
        ),
        value_columns=("nominal_mw", "emergency_mw", "availability"),
    ),
)


TABLES_BY_KEY = {table.key: table for table in ASSUMPTION_TABLES}


def read_table_rows(table: AssumptionTable) -> tuple[list[str], list[dict[str, str]]]:
    with table.path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def summarize_by_provenance(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {provenance.value: 0 for provenance in ProvenanceClass}
    for row in rows:
        provenance = row.get("provenance", "")
        counts[provenance] = counts.get(provenance, 0) + 1
    return {key: value for key, value in counts.items() if value}


def table_payload(table: AssumptionTable) -> dict[str, Any]:
    fieldnames, rows = read_table_rows(table)
    return {
        "key": table.key,
        "category": table.category,
        "path": table.path.as_posix(),
        "required_columns": list(table.required_columns),
        "columns": fieldnames,
        "row_count": len(rows),
        "provenance_counts": summarize_by_provenance(rows),
        "rows": rows,
    }
