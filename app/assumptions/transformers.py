from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from app.assumptions.provenance import TABLES_BY_KEY, read_table_rows, table_payload


TRANSFORMER_TABLE_KEYS = (
    "transformer_capacity_defaults",
    "transformer_tap_defaults",
)


def transformer_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY[key]) for key in TRANSFORMER_TABLE_KEYS]


@lru_cache(maxsize=1)
def _table_rows_by_key() -> dict[str, list[dict[str, str]]]:
    return {key: read_table_rows(TABLES_BY_KEY[key])[1] for key in TRANSFORMER_TABLE_KEYS}


def transformer_lookup_metadata() -> dict[str, Any]:
    capacity_rows = _table_rows_by_key()["transformer_capacity_defaults"]
    return {
        "transformer_voltage_pairs": [
            {
                "primary_kv": float(row["primary_kv"]),
                "secondary_kv": float(row["secondary_kv"]),
                "facility_class": row["facility_class"],
            }
            for row in capacity_rows
        ],
    }


def transformer_parameter_defaults(high_kv: float, low_kv: float) -> dict[str, Any]:
    rows_by_key = _table_rows_by_key()
    capacity_row = _nearest_voltage_pair_row(rows_by_key["transformer_capacity_defaults"], high_kv, low_kv)
    tap_row = _nearest_voltage_pair_row(rows_by_key["transformer_tap_defaults"], high_kv, low_kv)
    if capacity_row is None or tap_row is None:
        return {
            "br_r": 0.005,
            "br_x": 0.1,
            "rate_mva": 100.0,
            "tap": 1.0,
            "parameter_source": "missing_transformer_assumption_fallback",
            "parameter_table": "transformer_missing_assumption_fallback",
        }

    confidence = min(float(capacity_row["confidence"]), float(tap_row["confidence"]))
    pair_distance = _voltage_pair_distance(capacity_row, high_kv, low_kv)
    if pair_distance > 0.01:
        confidence = max(0.0, confidence - min(0.2, pair_distance))

    facility_class = capacity_row["facility_class"]
    parameter_table = "transformer_autotransformer_defaults" if "auto" in facility_class else "transformer_two_winding_defaults"
    return {
        "br_r": float(capacity_row["r_pu"]),
        "br_x": float(capacity_row["x_pu"]),
        "rate_mva": float(capacity_row["sn_mva_default"]),
        "sn_mva_default": float(capacity_row["sn_mva_default"]),
        "tap": float(tap_row["tap_neutral"]),
        "tap_side": tap_row["tap_side"],
        "tap_min": float(tap_row["tap_min"]),
        "tap_max": float(tap_row["tap_max"]),
        "tap_step_percent": float(tap_row["tap_step_percent"]),
        "matched_primary_kv": float(capacity_row["primary_kv"]),
        "matched_secondary_kv": float(capacity_row["secondary_kv"]),
        "facility_class": facility_class,
        "parameter_source": "transformer_assumption_table_lookup",
        "parameter_table": parameter_table,
        "parameter_table_keys": ["transformer_capacity_defaults", "transformer_tap_defaults"],
        "parameter_method": "nearest_voltage_pair_facility_lookup",
        "parameter_provenance": _combine_provenance(capacity_row, tap_row),
        "parameter_confidence": round(confidence, 3),
        "parameter_assumptions": _combine_text(capacity_row.get("assumptions"), tap_row.get("assumptions")),
        "parameter_source_detail": _combine_text(capacity_row.get("source"), tap_row.get("source")),
    }


def _nearest_voltage_pair_row(
    rows: list[dict[str, str]],
    high_kv: float,
    low_kv: float,
) -> dict[str, str] | None:
    if not rows:
        return None
    return min(rows, key=lambda row: _voltage_pair_distance(row, high_kv, low_kv))


def _voltage_pair_distance(row: Mapping[str, str], high_kv: float, low_kv: float) -> float:
    primary = float(row["primary_kv"])
    secondary = float(row["secondary_kv"])
    high = max(float(high_kv), float(low_kv))
    low = min(float(high_kv), float(low_kv))
    return abs(primary - high) / max(high, 1.0) + abs(secondary - low) / max(low, 1.0)


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
