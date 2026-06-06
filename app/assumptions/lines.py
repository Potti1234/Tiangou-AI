from __future__ import annotations

import math
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from app.assumptions.provenance import TABLES_BY_KEY, read_table_rows, table_payload


LINE_TABLE_KEYS = (
    "line_thermal_rating_defaults",
    "cable_impedance_defaults",
    "overhead_line_impedance_defaults",
)

DEFAULT_FREQUENCY_HZ = 50.0


def line_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY[key]) for key in LINE_TABLE_KEYS]


@lru_cache(maxsize=1)
def _table_rows_by_key() -> dict[str, list[dict[str, str]]]:
    return {key: read_table_rows(TABLES_BY_KEY[key])[1] for key in LINE_TABLE_KEYS}


def line_lookup_voltage_metadata() -> dict[str, list[float]]:
    rows_by_key = _table_rows_by_key()
    return {
        "overhead_line_voltage_kv": _sorted_voltages(rows_by_key["overhead_line_impedance_defaults"]),
        "underground_cable_voltage_kv": _sorted_voltages(
            [
                row
                for row in rows_by_key["cable_impedance_defaults"]
                if row.get("location_class") == "underground"
            ]
        ),
        "submarine_cable_voltage_kv": _sorted_voltages(
            [
                row
                for row in rows_by_key["cable_impedance_defaults"]
                if row.get("location_class") == "submarine"
            ]
        ),
    }


def branch_parameter_defaults(
    power: str,
    voltage_kv: float | None,
    *,
    location: str | None = None,
    circuit_count: int = 1,
) -> dict[str, Any]:
    if voltage_kv is None:
        return {"r_ohm_per_km": None, "x_ohm_per_km": None, "rate_mva": None, "parameter_table": None}

    asset_type = "cable" if power == "cable" else "line"
    location_class = infer_location_class(power, location)
    rows_by_key = _table_rows_by_key()
    impedance_key = "cable_impedance_defaults" if asset_type == "cable" else "overhead_line_impedance_defaults"
    impedance_row = _nearest_row(rows_by_key[impedance_key], asset_type, location_class, voltage_kv)
    rating_row = _nearest_row(rows_by_key["line_thermal_rating_defaults"], asset_type, location_class, voltage_kv)

    if impedance_row is None or rating_row is None:
        return {"r_ohm_per_km": None, "x_ohm_per_km": None, "rate_mva": None, "parameter_table": None}

    matched_voltage = float(impedance_row["voltage_kv"])
    per_circuit_rate = float(rating_row["rate_mva_per_circuit"])
    effective_circuits = max(1, int(circuit_count or 1))
    c_nf_per_km = float(impedance_row["c_nf_per_km"])
    b_us_per_km = _capacitance_nf_to_susceptance_us(c_nf_per_km)
    table_name = "underground_cable_defaults" if asset_type == "cable" else "overhead_line_defaults"

    confidence = min(float(impedance_row["confidence"]), float(rating_row["confidence"]))
    if abs(matched_voltage - float(voltage_kv)) > 0.01:
        confidence = max(0.0, confidence - 0.08)

    return {
        "r_ohm_per_km": float(impedance_row["r_ohm_per_km"]),
        "x_ohm_per_km": float(impedance_row["x_ohm_per_km"]),
        "c_nf_per_km": c_nf_per_km,
        "b_us_per_km": b_us_per_km,
        "rate_mva": round(per_circuit_rate * effective_circuits, 6),
        "rate_mva_per_circuit": per_circuit_rate,
        "emergency_factor": float(rating_row["emergency_factor"]),
        "matched_voltage_kv": matched_voltage,
        "location_class": impedance_row["location_class"],
        "parameter_table": table_name,
        "parameter_table_keys": [impedance_key, "line_thermal_rating_defaults"],
        "parameter_source": "assumption_table_lookup",
        "parameter_method": "nearest_voltage_asset_location_lookup",
        "parameter_provenance": _combine_provenance(impedance_row, rating_row),
        "parameter_confidence": round(confidence, 3),
        "parameter_assumptions": _combine_text(impedance_row.get("assumptions"), rating_row.get("assumptions")),
        "parameter_source_detail": _combine_text(impedance_row.get("source"), rating_row.get("source")),
    }


def infer_location_class(power: str, location: str | None) -> str:
    text = str(location or "").lower()
    if "submarine" in text or "underwater" in text or "sea" in text:
        return "submarine"
    if power == "cable" or "underground" in text or "tunnel" in text:
        return "underground"
    return "overhead"


def _nearest_row(
    rows: list[dict[str, str]],
    asset_type: str,
    location_class: str,
    voltage_kv: float,
) -> dict[str, str] | None:
    candidates = [
        row
        for row in rows
        if row.get("asset_type") == asset_type and row.get("location_class") == location_class
    ]
    if not candidates and location_class == "submarine":
        candidates = [
            row
            for row in rows
            if row.get("asset_type") == asset_type and row.get("location_class") == "underground"
        ]
    if not candidates:
        candidates = [row for row in rows if row.get("asset_type") == asset_type]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(float(row["voltage_kv"]) - float(voltage_kv)))


def _sorted_voltages(rows: list[dict[str, str]]) -> list[float]:
    return sorted({float(row["voltage_kv"]) for row in rows})


def _capacitance_nf_to_susceptance_us(c_nf_per_km: float) -> float:
    return round((2.0 * math.pi * DEFAULT_FREQUENCY_HZ * c_nf_per_km * 1e-9) * 1e6, 6)


def _combine_provenance(*rows: Mapping[str, str]) -> str:
    values = {row.get("provenance", "") for row in rows if row.get("provenance")}
    if len(values) == 1:
        return next(iter(values))
    return "mixed"


def _combine_text(*values: str | None) -> str:
    parts = []
    for value in values:
        if value and value not in parts:
            parts.append(value)
    return " | ".join(parts)
