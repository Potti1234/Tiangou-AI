from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.assumptions.demand_profiles import demand_profile_for_sector


@dataclass
class DynamicGridConfig:
    grid_config: dict[str, Any]
    demand_profile_mw: dict[int, float]
    ev_stations: list[dict[str, Any]]
    source_mapping: dict[str, Any]
    provenance: dict[str, Any]
    data_centers: list[dict[str, Any]]


def build_dynamic_config(
    powermodels_case: dict[str, Any],
    consumer_proxies: list[dict[str, Any]] | None = None,
    demand_snapshot: str = "peak_16h",
) -> DynamicGridConfig:
    base_mva = float(powermodels_case.get("baseMVA") or 100.0)
    sources = [_source_from_generator(source_id, gen, base_mva) for source_id, gen in powermodels_case.get("gen", {}).items()]
    total_demand = _total_case_demand_mw(powermodels_case)
    sources = _apply_merit_order_dispatch(sources, total_demand)
    demand_profile = _build_demand_profile(powermodels_case, total_demand)
    if demand_snapshot == "overnight_04h" and 4 in demand_profile:
        start_demand = demand_profile[4]
    else:
        start_demand = demand_profile.get(16, total_demand)
    scale = total_demand / start_demand if start_demand > 0 else 1.0
    demand_profile = {hour: round(value * scale, 3) for hour, value in demand_profile.items()}
    ev_stations = _ev_stations_from_proxies(consumer_proxies or [])
    data_centers = _data_centers_from_proxies(consumer_proxies or [])
    provenance_counts = _provenance_counts(sources)
    return DynamicGridConfig(
        grid_config={
            "sources": sources,
            "base_mva": powermodels_case.get("baseMVA", 100.0),
            "nominal_frequency_hz": 50.0,
            "demand_snapshot": demand_snapshot,
        },
        demand_profile_mw=demand_profile,
        ev_stations=ev_stations,
        source_mapping={
            "generator_count": len(sources),
            "types": _type_counts(sources),
            "source_ids": {source["source_id"]: source["type"] for source in sources},
        },
        provenance={
            "schema": "tiangou.dynamic.real_grid.v1",
            "source": "powermodels_case",
            "demand_snapshot": demand_snapshot,
            "total_demand_mw": round(total_demand, 3),
            "provenance_summary": provenance_counts,
            "synthetic_or_inferred_source_count": sum(
                count for key, count in provenance_counts.items() if key.startswith("synthetic") or key.startswith("inferred")
            ),
            "assumptions": [
                "Generator inertia defaults are assigned by normalized source type.",
                "PowerModels p.u. generation and load values are converted with baseMVA.",
                "Hourly demand uses exported load profiles where present, otherwise table-backed Hong Kong sector profiles.",
            ],
        },
        data_centers=data_centers,
    )


_DISPATCH_PRIORITY: dict[str, int] = {
    "offshore_wind": 0,
    "solar_pv": 0,
    "nuclear": 1,
    "imports": 2,
    "coal": 3,
    "gas_ccgt": 4,
    "other_dispatchable": 5,
    "bess": 6,
    "generic_capacity_equivalent": 10,
}


def _apply_merit_order_dispatch(sources: list[dict[str, Any]], total_demand_mw: float) -> list[dict[str, Any]]:
    """Dispatch sources in merit order until generation matches demand.

    When pg=0 in the PowerModels case (no OPF has been run), every generator
    falls back to pmax in _source_from_generator, causing massive overgeneration.
    This function replaces those outputs with a simple merit-order dispatch so
    the simulation starts near 50 Hz.
    """
    if total_demand_mw <= 0:
        return sources

    ranked = sorted(sources, key=lambda s: _DISPATCH_PRIORITY.get(s["type"], 5))
    remaining = total_demand_mw
    id_to_output: dict[str, float] = {}

    for source in ranked:
        cap = source["capacity_mw"]
        if remaining <= 0 or cap <= 0:
            id_to_output[source["source_id"]] = 0.0
        else:
            dispatched = min(cap, remaining)
            id_to_output[source["source_id"]] = round(dispatched, 3)
            remaining -= dispatched

    return [
        {**s, "current_output_mw": id_to_output.get(s["source_id"], 0.0)}
        for s in sources
    ]


def _source_from_generator(source_id: str, gen: dict[str, Any], base_mva: float) -> dict[str, Any]:
    pmax_mw = max(float(gen.get("pmax") or 0.0) * base_mva, 0.0)
    output_mw = max(float(gen.get("pg") or gen.get("pmax") or 0.0) * base_mva, 0.0)
    normalized_type = _normalize_source_type(gen)
    return {
        "name": gen.get("name") or gen.get("source_id") or source_id,
        "source_id": gen.get("source_id") or source_id,
        "type": normalized_type,
        "capacity_mw": round(pmax_mw, 3),
        "current_output_mw": round(min(output_mw, pmax_mw), 3),
        "H": _inertia_default(normalized_type),
        "online": pmax_mw > 0,
        "ramp_rate_mw_per_min": _ramp_rate_default(normalized_type, pmax_mw),
        "weather_dependent": normalized_type in {"offshore_wind", "solar_pv"},
        "provenance": gen.get("provenance"),
        "confidence": gen.get("confidence"),
        "original": {
            "resource_type": gen.get("resource_type"),
            "energy_source": gen.get("energy_source"),
            "operator": gen.get("operator"),
            "capacity_tag": gen.get("capacity_tag"),
            "connection_method": gen.get("connection_method"),
        },
    }


def _normalize_source_type(gen: dict[str, Any]) -> str:
    text = " ".join(str(gen.get(key) or "").lower() for key in ("energy_source", "source", "resource_type", "name", "provenance"))
    if "coal" in text:
        return "coal"
    if "gas" in text or "ccgt" in text:
        return "gas_ccgt"
    if "nuclear" in text:
        return "nuclear"
    # Territory-level capacity equivalents are synthetic placeholders — treat as last-resort
    if "capacity_equivalent" in text or "territory_equivalent" in text or "island_local_supply_equivalent" in text:
        return "generic_capacity_equivalent"
    if "import" in text:
        return "imports"
    if "wind" in text:
        return "offshore_wind"
    if "solar" in text:
        return "solar_pv"
    if "battery" in text or "bess" in text:
        return "bess"
    if "waste" in text:
        return "other_dispatchable"
    if "equivalent" in text:
        return "generic_capacity_equivalent"
    return "other_dispatchable"


def _inertia_default(source_type: str) -> float:
    return {
        "coal": 5.0,
        "gas_ccgt": 4.0,
        "nuclear": 6.0,
        "imports": 6.0,
        "offshore_wind": 0.0,
        "solar_pv": 0.0,
        "bess": 0.0,
        "other_dispatchable": 3.0,
        "generic_capacity_equivalent": 3.5,
    }.get(source_type, 3.0)


def _ramp_rate_default(source_type: str, capacity_mw: float) -> float:
    fraction = {
        "coal": 0.02,
        "gas_ccgt": 0.08,
        "nuclear": 0.01,
        "imports": 0.15,
        "bess": 1.0,
        "other_dispatchable": 0.05,
        "generic_capacity_equivalent": 0.05,
    }.get(source_type, 0.04)
    return round(max(capacity_mw * fraction, 1.0), 3)


def _total_case_demand_mw(case: dict[str, Any]) -> float:
    metadata = case.get("_metadata", {})
    if isinstance(metadata.get("total_pd_mw"), (int, float)):
        return float(metadata["total_pd_mw"])
    base_mva = float(case.get("baseMVA") or 100.0)
    return sum(float(load.get("pd") or 0.0) * base_mva for load in case.get("load", {}).values())


def _build_demand_profile(case: dict[str, Any], total_demand_mw: float) -> dict[int, float]:
    hourly_totals = [0.0] * 24
    used_exported_profile = False
    for load in case.get("load", {}).values():
        hourly = load.get("hourly_pd_mw")
        if isinstance(hourly, list) and len(hourly) == 24:
            used_exported_profile = True
            for hour, value in enumerate(hourly):
                hourly_totals[hour] += float(value)
    if used_exported_profile and max(hourly_totals) > 0:
        return {hour: round(value, 3) for hour, value in enumerate(hourly_totals)}
    profile = demand_profile_for_sector("commercial")
    shares = profile["shares"]
    peak_share = max(shares) if shares else 1.0
    return {hour: round(total_demand_mw * share / peak_share, 3) for hour, share in enumerate(shares)}


def _ev_stations_from_proxies(proxies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stations = []
    for proxy in proxies:
        if proxy.get("reason") != "charging_station" and proxy.get("proxy_type") != "charging_station":
            continue
        load = min(max(float(proxy.get("weight") or 1.0) * 0.15, 0.15), 2.0)
        stations.append({
            "id": proxy.get("id"),
            "name": proxy.get("name") or proxy.get("id"),
            "lat": proxy.get("lat"),
            "lon": proxy.get("lon"),
            "max_load_mw": round(load, 3),
            "active": True,
            "provenance": "osm_consumer_proxy_with_assumed_charger_load",
            "confidence": proxy.get("confidence"),
        })
    return stations


def _data_centers_from_proxies(proxies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    centers = []
    for proxy in proxies:
        estimate = proxy.get("data_center_load_estimate")
        if proxy.get("reason") != "data_center" and not estimate:
            continue
        facility_mw = float((estimate or {}).get("estimated_facility_mw") or 25.0)
        centers.append({
            "id": proxy.get("id"),
            "name": proxy.get("name") or proxy.get("id"),
            "lat": proxy.get("lat"),
            "lon": proxy.get("lon"),
            "estimated_facility_mw": round(facility_mw, 3),
            "estimate": estimate or {
                "provenance": "synthetic_dynamic_demo_default",
                "assumptions": "Fallback data-center spike where no public per-site load is available.",
                "confidence": 0.3,
            },
        })
    return sorted(centers, key=lambda row: row["estimated_facility_mw"], reverse=True)


def _type_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        counts[source["type"]] = counts.get(source["type"], 0) + 1
    return counts


def _provenance_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        key = str(source.get("provenance") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts
