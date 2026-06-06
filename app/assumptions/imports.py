from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.assumptions.provenance import TABLES_BY_KEY, read_table_rows, table_payload


def import_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY["cross_border_import_limits"])]


@lru_cache(maxsize=1)
def _import_limits_by_boundary() -> dict[str, dict[str, Any]]:
    _, rows = read_table_rows(TABLES_BY_KEY["cross_border_import_limits"])
    limits: dict[str, dict[str, Any]] = {}
    for row in rows:
        limits[row["boundary_id"]] = {
            "boundary_id": row["boundary_id"],
            "from_region": row["from_region"],
            "to_region": row["to_region"],
            "nominal_mw": float(row["nominal_mw"]),
            "emergency_mw": float(row["emergency_mw"]),
            "derate_scenarios": [float(item) for item in row["derate_scenarios"].split(";") if item],
            "availability": float(row["availability"]),
            "cost_class": row["cost_class"],
            "source": row["source"],
            "provenance": row["provenance"],
            "confidence": float(row["confidence"]),
            "method": row["method"],
            "assumptions": row["assumptions"],
        }
    return limits


def import_boundary_defaults(boundary_id: str) -> dict[str, Any]:
    return dict(_import_limits_by_boundary()[boundary_id])
