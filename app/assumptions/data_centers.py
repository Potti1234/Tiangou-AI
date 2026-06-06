from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.assumptions.provenance import TABLES_BY_KEY, table_payload


DATA_CENTER_PUE_DEFAULT = 1.45
DATA_CENTER_UTILIZATION_FACTOR = 0.45
DATA_CENTER_KW_PER_M2 = 1.2
DATA_CENTER_SMALL_IT_MW = 2.0
DATA_CENTER_NAMED_IT_MW = 12.0
DATA_CENTER_LARGE_IT_MW = 60.0
DATA_CENTER_IT_CAP_MW = 120.0


def data_center_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY["data_center_site_assumptions"])]


def is_data_center_proxy(proxy: Mapping[str, Any]) -> bool:
    proxy_type = str(proxy.get("proxy_type") or "").lower()
    tags = proxy.get("tags") if isinstance(proxy.get("tags"), Mapping) else {}
    name_text = " ".join(
        str(value or "").lower()
        for value in (
            proxy.get("name"),
            tags.get("name"),
            tags.get("name:en"),
            tags.get("operator"),
            tags.get("brand"),
        )
    )
    return (
        proxy_type == "data_center"
        or str(tags.get("telecom") or "").lower() == "data_center"
        or str(tags.get("building") or "").lower() == "data_center"
        or "data center" in name_text
        or "data centre" in name_text
    )


def estimate_data_center_load(proxy: Mapping[str, Any]) -> dict[str, Any] | None:
    if not is_data_center_proxy(proxy):
        return None

    name = str(proxy.get("name") or "Unnamed data-center proxy")
    weight = _positive_float(proxy.get("weight"))
    weight_method = str(proxy.get("weight_method") or "")
    gross_floor_area_m2 = weight if weight_method in {"building_floor_area_proxy", "landuse_polygon_area_proxy"} else None
    method = "data_center_proxy_floor_area_estimator"
    confidence = min(float(proxy.get("confidence") or 0.45), 0.62)

    if gross_floor_area_m2 is not None:
        it_mw = gross_floor_area_m2 * DATA_CENTER_UTILIZATION_FACTOR * DATA_CENTER_KW_PER_M2 / 1000.0
        floor_area_method = weight_method
        if gross_floor_area_m2 >= 60_000:
            it_mw = max(it_mw, DATA_CENTER_LARGE_IT_MW)
        it_mw = min(max(it_mw, 0.5), DATA_CENTER_IT_CAP_MW)
    elif name and name != "Unnamed data-center proxy":
        it_mw = DATA_CENTER_NAMED_IT_MW
        floor_area_method = "named_site_default"
        confidence = min(confidence, 0.46)
    else:
        it_mw = DATA_CENTER_SMALL_IT_MW
        floor_area_method = "poi_or_small_building_default"
        confidence = min(confidence, 0.42)

    facility_mw = it_mw * DATA_CENTER_PUE_DEFAULT
    return {
        "estimated_it_mw": round(it_mw, 3),
        "estimated_facility_mw": round(facility_mw, 3),
        "pue": DATA_CENTER_PUE_DEFAULT,
        "gross_floor_area_m2": round(gross_floor_area_m2, 3) if gross_floor_area_m2 is not None else None,
        "floor_area_method": floor_area_method,
        "method": method,
        "provenance": "synthetic_engineering_default",
        "confidence": round(confidence, 3),
        "assumptions": "IT MW = gross floor area * utilization factor * kW/m2 / 1000 where area is available; otherwise named/small archetype defaults; facility MW = IT MW * PUE; capped at 120 MW IT.",
        "source": "OSM data-center proxy tags and conservative engineering load-density defaults",
    }


def _positive_float(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
