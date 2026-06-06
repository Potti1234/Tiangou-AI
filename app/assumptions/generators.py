from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.assumptions.provenance import TABLES_BY_KEY, read_table_rows, table_payload


GENERATOR_TABLE_KEYS = (
    "generator_cost_availability_defaults",
    "generator_dispatch_merit_order",
)


def generator_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY[key]) for key in GENERATOR_TABLE_KEYS]


@lru_cache(maxsize=1)
def _generator_defaults_by_source() -> dict[str, dict[str, Any]]:
    _, cost_rows = read_table_rows(TABLES_BY_KEY["generator_cost_availability_defaults"])
    _, merit_rows = read_table_rows(TABLES_BY_KEY["generator_dispatch_merit_order"])
    merit_by_source = {row["energy_source"]: row for row in merit_rows}
    defaults: dict[str, dict[str, Any]] = {}
    for row in cost_rows:
        source = row["energy_source"]
        merit = merit_by_source.get(source, {})
        variable_cost = float(row["variable_cost_usd_per_mwh"])
        defaults[source] = {
            "energy_source": source,
            "cost": [0.0, variable_cost, 0.0],
            "variable_cost_usd_per_mwh": variable_cost,
            "startup_cost_usd": float(row["startup_cost_usd"]),
            "availability_factor": float(row["availability_factor"]),
            "forced_outage_rate": float(row["forced_outage_rate"]),
            "co2_t_per_mwh": float(row["co2_t_per_mwh"]),
            "pmin_fraction": float(row["pmin_fraction"]),
            "ramp_rate_mw_per_min": float(row["ramp_rate_mw_per_min"]),
            "cost_class": merit.get("cost_class") or source,
            "dispatch_priority": int(merit.get("dispatch_priority") or 99),
            "synthetic_cost_provenance": row["provenance"],
            "cost_confidence": float(row["confidence"]),
            "cost_method": row["method"],
            "cost_source": row["source"],
            "cost_assumptions": row["assumptions"],
        }
    return defaults


def generator_defaults(source: str) -> dict[str, Any]:
    defaults = _generator_defaults_by_source()
    return dict(defaults.get(source) or defaults["unknown"])


def equivalent_generator_defaults(territory: str) -> dict[str, Any]:
    source = {
        "clp": "territory_equivalent_import_or_local_supply",
        "hk-electric": "island_local_supply_equivalent",
    }.get(territory, "generic_capacity_equivalent")
    return generator_defaults(source)


def generator_lookup_metadata() -> dict[str, Any]:
    defaults = _generator_defaults_by_source()
    return {
        "generator_energy_sources": sorted(defaults),
        "generator_dispatch_priorities": {
            source: defaults[source]["dispatch_priority"]
            for source in sorted(defaults)
        },
    }
