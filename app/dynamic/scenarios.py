from __future__ import annotations

from typing import Any

from app.dynamic.adapter import DynamicGridConfig


def build_scenarios(config: DynamicGridConfig) -> list[dict[str, Any]]:
    sources = config.grid_config.get("sources", [])
    scenarios = [
        _largest_generator_trip(sources),
        _import_loss(sources),
        _datacenter_spike(config.data_centers),
        _renewable_weather_loss(sources),
    ]
    available = [scenario for scenario in scenarios if scenario["available"]]
    combined = _combined_stress(available)
    if combined:
        scenarios.append(combined)
    return scenarios


def scenario_by_id(config: DynamicGridConfig, scenario_id: str) -> dict[str, Any] | None:
    return next((scenario for scenario in build_scenarios(config) if scenario["id"] == scenario_id), None)


def _largest_generator_trip(sources: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [s for s in sources if s.get("online") and s.get("H", 0) > 0]
    if not candidates:
        return _unavailable("largest_generator_trip", "No online synchronous generator is present in the dynamic config.")
    source = max(candidates, key=lambda row: float(row.get("current_output_mw") or row.get("capacity_mw") or 0.0))
    magnitude = -float(source.get("current_output_mw") or source.get("capacity_mw") or 0.0)
    return _scenario(
        "largest_generator_trip",
        f"Trip largest synchronous source: {source['name']}",
        "generation_loss",
        [source],
        magnitude,
        "step",
        "PowerModels generator mapped to dynamic synchronous source.",
        "Uses current dispatch estimate when available, otherwise capacity.",
    )


def _import_loss(sources: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [s for s in sources if s.get("type") in {"imports", "nuclear"} and s.get("online")]
    if not candidates:
        return _unavailable("import_loss", "No import/equivalent supply source exists in the current grid-derived case.")
    source = max(candidates, key=lambda row: float(row.get("current_output_mw") or row.get("capacity_mw") or 0.0))
    magnitude = -float(source.get("current_output_mw") or source.get("capacity_mw") or 0.0)
    return _scenario("import_loss", f"Loss of import/equivalent source: {source['name']}", "generation_loss", [source], magnitude, "step", "PowerModels import/equivalent generator.", "Treats equivalent imports as synchronous supply for frequency dynamics.")


def _datacenter_spike(data_centers: list[dict[str, Any]]) -> dict[str, Any]:
    if data_centers:
        center = data_centers[0]
        magnitude = max(float(center["estimated_facility_mw"]), 25.0)
        return {
            "id": "datacenter_spike",
            "description": f"Demand ramp from top data-center proxy: {center['name']}",
            "type": "demand_increase",
            "affected_sources": [],
            "affected_loads": [center],
            "magnitude_mw": round(magnitude, 3),
            "profile": "ramp",
            "ramp_time_s": 120,
            "available": True,
            "provenance": "important_consumer_proxy_data_center_estimate",
            "assumptions": "Uses the top estimated facility MW from public proxy tags and assumption-table load estimator.",
        }
    return {
        "id": "datacenter_spike",
        "description": "Synthetic data-center demand ramp",
        "type": "demand_increase",
        "affected_sources": [],
        "affected_loads": [],
        "magnitude_mw": 150.0,
        "profile": "ramp",
        "ramp_time_s": 120,
        "available": True,
        "provenance": "synthetic_dynamic_demo_default",
        "assumptions": "No data-center proxies were available, so this is a labeled synthetic demand spike.",
    }


def _renewable_weather_loss(sources: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [s for s in sources if s.get("weather_dependent") and s.get("online")]
    if not candidates:
        return _unavailable("renewable_weather_loss", "No online wind or solar source exists in the current grid-derived case.")
    magnitude = -sum(float(s.get("current_output_mw") or s.get("capacity_mw") or 0.0) for s in candidates)
    return _scenario("renewable_weather_loss", "Weather-driven renewable ramp-down", "generation_loss", candidates, magnitude, "ramp", "PowerModels wind/solar sources mapped as weather dependent.", "Ramps down current renewable output over 60 seconds.", ramp_time_s=60)


def _combined_stress(available: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_id = {scenario["id"]: scenario for scenario in available}
    first = by_id.get("renewable_weather_loss") or by_id.get("largest_generator_trip")
    second = by_id.get("datacenter_spike")
    if not first or not second:
        return None
    return {
        "id": "combined_stress",
        "description": f"{first['description']} plus data-center load growth",
        "type": "combined",
        "sub_events": [first, second],
        "affected_sources": first.get("affected_sources", []),
        "magnitude_mw": round(float(first.get("magnitude_mw") or 0.0) + float(second.get("magnitude_mw") or 0.0), 3),
        "profile": "combined",
        "available": True,
        "provenance": "composed_from_real_grid_dynamic_scenarios",
        "assumptions": "Combines the available renewable/generator stress with data-center demand stress.",
    }


def _scenario(
    scenario_id: str,
    description: str,
    scenario_type: str,
    sources: list[dict[str, Any]],
    magnitude: float,
    profile: str,
    provenance: str,
    assumptions: str,
    ramp_time_s: int | None = None,
) -> dict[str, Any]:
    payload = {
        "id": scenario_id,
        "description": description,
        "type": scenario_type,
        "affected_sources": [source["name"] for source in sources],
        "affected_source_ids": [source["source_id"] for source in sources],
        "magnitude_mw": round(magnitude, 3),
        "profile": profile,
        "available": True,
        "provenance": provenance,
        "assumptions": assumptions,
    }
    if ramp_time_s is not None:
        payload["ramp_time_s"] = ramp_time_s
    return payload


def _unavailable(scenario_id: str, reason: str) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "description": reason,
        "type": "unavailable",
        "affected_sources": [],
        "magnitude_mw": 0.0,
        "profile": "step",
        "available": False,
        "unavailable_reason": reason,
        "provenance": "real_grid_dynamic_scenario_builder",
        "assumptions": "Scenario is disabled rather than fabricated when the required real-grid asset class is absent.",
    }
