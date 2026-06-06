import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.data_sources import CalibrationBundle, load_calibration_bundle


BRANCH_POWER_VALUES = {"line", "minor_line", "cable"}
BUS_POWER_VALUES = {
    "plant",
    "generator",
    "substation",
    "sub_station",
    "transformer",
    "terminal",
    "converter",
    "compensator",
    "busbar",
    "bay",
    "switchgear",
    "switch",
}
SUPPORT_POWER_VALUES = {"tower", "pole", "portal", "insulator"}

RAW_DATA_DIR = Path("data/raw")
SYNTHETIC_CLP_PEAK_DEMAND_MW = 7336.0
SYNTHETIC_CLP_SNAPSHOT_FACTORS = {
    "peak_16h": 1.0,
    "overnight_04h": 0.55,
    "shoulder_10h": 0.75,
    "cooling_peak_18h": 1.12,
}
HK_INTERTIE_RATE_MVA = 720.0
DEMAND_SNAPSHOTS = {
    "peak_16h": {
        "label": "Hong Kong 2024 peak demand, 16h representative snapshot",
        "load_factor": 1.0,
    },
    "overnight_04h": {
        "label": "Hong Kong 2024 overnight low-load, 04h representative snapshot",
        "load_factor": 0.55,
    },
    "shoulder_10h": {
        "label": "Hong Kong 2024 shoulder-demand, 10h representative snapshot",
        "load_factor": 0.75,
    },
    "cooling_peak_18h": {
        "label": "Hong Kong high-temperature cooling stress, 18h representative snapshot",
        "load_factor": 1.12,
    },
}
BASE_MVA = 100.0
SOLVER_INCLUDE_POLICIES = {"strict_transmission", "demo_full_osm"}
DEFAULT_SOLVER_INCLUDE_POLICY = "demo_full_osm"
DEFAULT_MIN_SOLVER_GENERATOR_MW = 0.5
LOAD_DEFAULTS = {
    "power_factor": 0.95,
}
HK_ELECTRIC_DISTRICT_CENTROIDS = {
    "central_western": (22.285, 114.147),
    "eastern": (22.284, 114.224),
    "wan_chai": (22.276, 114.176),
    "southern": (22.247, 114.158),
    "lamma": (22.206, 114.126),
}

OVERHEAD_LINE_DEFAULTS = {
    400.0: {"r_ohm_per_km": 0.028, "x_ohm_per_km": 0.32, "b_us_per_km": 3.6, "rate_mva": 1800.0},
    275.0: {"r_ohm_per_km": 0.035, "x_ohm_per_km": 0.34, "b_us_per_km": 3.2, "rate_mva": 1200.0},
    220.0: {"r_ohm_per_km": 0.045, "x_ohm_per_km": 0.38, "b_us_per_km": 2.8, "rate_mva": 900.0},
    132.0: {"r_ohm_per_km": 0.08, "x_ohm_per_km": 0.42, "b_us_per_km": 2.2, "rate_mva": 450.0},
    110.0: {"r_ohm_per_km": 0.10, "x_ohm_per_km": 0.45, "b_us_per_km": 2.0, "rate_mva": 350.0},
    33.0: {"r_ohm_per_km": 0.25, "x_ohm_per_km": 0.35, "b_us_per_km": 1.2, "rate_mva": 90.0},
}
UNDERGROUND_CABLE_DEFAULTS = {
    400.0: {"r_ohm_per_km": 0.018, "x_ohm_per_km": 0.12, "b_us_per_km": 38.0, "rate_mva": 1400.0},
    275.0: {"r_ohm_per_km": 0.023, "x_ohm_per_km": 0.13, "b_us_per_km": 32.0, "rate_mva": 900.0},
    220.0: {"r_ohm_per_km": 0.03, "x_ohm_per_km": 0.14, "b_us_per_km": 26.0, "rate_mva": 700.0},
    132.0: {"r_ohm_per_km": 0.055, "x_ohm_per_km": 0.16, "b_us_per_km": 18.0, "rate_mva": 300.0},
    110.0: {"r_ohm_per_km": 0.07, "x_ohm_per_km": 0.18, "b_us_per_km": 15.0, "rate_mva": 250.0},
    33.0: {"r_ohm_per_km": 0.20, "x_ohm_per_km": 0.20, "b_us_per_km": 8.0, "rate_mva": 75.0},
}
BRANCH_PARAMETER_TABLES = {
    "line": OVERHEAD_LINE_DEFAULTS,
    "minor_line": OVERHEAD_LINE_DEFAULTS,
    "cable": UNDERGROUND_CABLE_DEFAULTS,
}
TRANSFORMER_DEFAULTS = {
    "autotransformer": {"br_r": 0.005, "br_x": 0.08},
    "two_winding": {"br_r": 0.005, "br_x": 0.1},
}
GENERATOR_FUEL_DEFAULTS = {
    "coal": {"cost": [0.012, 26.0, 0.0], "cost_class": "thermal_coal", "pmin_fraction": 0.0, "power_factor": 0.86},
    "gas": {"cost": [0.01, 22.0, 0.0], "cost_class": "thermal_gas", "pmin_fraction": 0.0, "power_factor": 0.86},
    "nuclear": {"cost": [0.004, 12.0, 0.0], "cost_class": "low_variable_cost_import_or_nuclear", "pmin_fraction": 0.0, "power_factor": 0.9},
    "solar": {"cost": [0.0, 2.0, 0.0], "cost_class": "low_variable_cost_renewable", "pmin_fraction": 0.0, "power_factor": 0.95},
    "wind": {"cost": [0.0, 2.0, 0.0], "cost_class": "low_variable_cost_renewable", "pmin_fraction": 0.0, "power_factor": 0.95},
    "waste": {"cost": [0.006, 18.0, 0.0], "cost_class": "waste_to_energy", "pmin_fraction": 0.0, "power_factor": 0.86},
    "unknown": {"cost": [0.01, 24.0, 0.0], "cost_class": "generic_dispatchable", "pmin_fraction": 0.0, "power_factor": 0.86},
}
EQUIVALENT_GENERATOR_DEFAULTS = {
    "clp": {"cost": [0.01, 20.0, 0.0], "cost_class": "territory_equivalent_import_or_local_supply", "pmin_fraction": 0.0, "power_factor": 0.86},
    "hk-electric": {"cost": [0.01, 24.0, 0.0], "cost_class": "island_local_supply_equivalent", "pmin_fraction": 0.0, "power_factor": 0.86},
    "default": {"cost": [0.01, 30.0, 0.0], "cost_class": "generic_capacity_equivalent", "pmin_fraction": 0.0, "power_factor": 0.86},
}
FACILITY_FOOTPRINT_RADIUS_MIN_KM = 0.02
FACILITY_FOOTPRINT_RADIUS_MAX_KM = 0.25
POINT_FACILITY_BUFFER_KM = 0.15


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def normalize_voltage(raw: Any) -> list[float]:
    if raw in (None, ""):
        return []

    text = str(raw).lower().replace("kv", "").replace("v", "")
    values: list[float] = []
    for token in re.split(r"[;,/| ]+", text):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            continue
        if value <= 0:
            continue
        values.append(round(value / 1000.0 if value > 1000 else value, 3))

    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def parse_power_mw(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    text = str(raw).lower().replace(",", "").strip()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?w)?", text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or "mw"
    if unit == "kw":
        value /= 1000.0
    elif unit == "gw":
        value *= 1000.0
    elif unit == "tw":
        value *= 1_000_000.0
    elif unit not in {"mw", "w"}:
        return None
    elif unit == "w":
        value /= 1_000_000.0
    if value <= 0:
        return None
    return round(value, 3)


def parse_circuit_count(tags: Mapping[str, Any]) -> tuple[int, str]:
    circuits = _parse_positive_int(tags.get("circuits"))
    if circuits is not None:
        return circuits, "circuits"

    cables = _parse_positive_int(tags.get("cables"))
    if cables is not None:
        return max(1, cables // 3), "cables_div_3"

    voltages = normalize_voltage(tags.get("voltage"))
    if len(voltages) > 1:
        return len(voltages), "multi_voltage"

    return 1, "default_single_circuit"


def split_voltage_circuits(tags: Mapping[str, Any]) -> list[dict[str, Any]]:
    voltages = normalize_voltage(tags.get("voltage"))
    if not voltages:
        circuit_count, source = parse_circuit_count(tags)
        return [{"voltage_kv": None, "circuit_count": circuit_count, "count_source": source}]

    circuit_count, source = parse_circuit_count(tags)
    if len(voltages) <= 1:
        return [{"voltage_kv": voltages[0], "circuit_count": circuit_count, "count_source": source}]

    return [
        {
            "voltage_kv": voltage,
            "circuit_count": 1,
            "count_source": "multi_voltage_split",
        }
        for voltage in voltages
    ]


def _parse_positive_int(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    match = re.search(r"\d+", str(raw))
    if not match:
        return None
    value = int(match.group(0))
    return value if value > 0 else None


def voltage_band(voltage_kv: float | None) -> str:
    if voltage_kv is None:
        return "unknown"
    if voltage_kv >= 220:
        return "extra_high_voltage"
    if voltage_kv >= 100:
        return "high_voltage"
    if voltage_kv >= 33:
        return "subtransmission"
    return "distribution"


def infer_service_territory(tags: Mapping[str, Any], name: str | None) -> str | None:
    haystack = " ".join(
        str(value)
        for value in (
            name,
            tags.get("operator"),
            tags.get("owner"),
            tags.get("brand"),
            tags.get("network"),
        )
        if value
    ).lower()
    if "hk electric" in haystack or "hongkong electric" in haystack or "hke" in haystack:
        return "hk-electric"
    if "clp" in haystack or "china light" in haystack:
        return "clp"
    return None


def _asset_kind(power: str) -> str:
    if power in BRANCH_POWER_VALUES:
        return "branch"
    if power in BUS_POWER_VALUES:
        return "bus_candidate"
    if power in SUPPORT_POWER_VALUES:
        return "support"
    return "other"


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _geometry_length_km(geometry: list[dict[str, Any]]) -> float | None:
    points = [(point.get("lat"), point.get("lon")) for point in geometry]
    coords = [(lat, lon) for lat, lon in points if lat is not None and lon is not None]
    if len(coords) < 2:
        return None
    return sum(_haversine_km(coords[index - 1], coords[index]) for index in range(1, len(coords)))


def _nearest_bus(
    buses: list[dict[str, Any]],
    point: tuple[float, float],
    snap_tolerance_km: float,
    *,
    voltage_kv: float | None = None,
) -> tuple[str | None, float | None]:
    candidates = []
    for bus in buses:
        if bus["lat"] is None or bus["lon"] is None:
            continue
        distance = _haversine_km(point, (bus["lat"], bus["lon"]))
        effective_distance = max(0.0, distance - float(bus.get("facility_radius_km") or 0.0))
        bus_voltage = bus.get("base_kv")
        voltage_delta = abs(float(bus_voltage) - voltage_kv) if bus_voltage is not None and voltage_kv is not None else math.inf
        candidates.append(
            {
                "id": bus["id"],
                "distance": distance,
                "effective_distance": effective_distance,
                "voltage_delta": voltage_delta,
            }
        )
    if not candidates:
        return None, None
    nearest_actual = min(candidates, key=lambda candidate: (candidate["distance"], candidate["voltage_delta"]))
    if nearest_actual["distance"] <= snap_tolerance_km:
        return str(nearest_actual["id"]), float(nearest_actual["distance"])
    nearest_effective = min(candidates, key=lambda candidate: (candidate["effective_distance"], candidate["distance"], candidate["voltage_delta"]))
    footprint_margin_km = min(snap_tolerance_km, FACILITY_FOOTPRINT_RADIUS_MIN_KM)
    if nearest_effective["effective_distance"] > footprint_margin_km:
        return None, nearest_actual["distance"]
    return str(nearest_effective["id"]), float(nearest_effective["distance"])


def _branch_defaults(power: str, voltage_kv: float | None) -> dict[str, Any]:
    if voltage_kv is None:
        return {"r_ohm_per_km": None, "x_ohm_per_km": None, "rate_mva": None, "parameter_table": None}
    table_name = "underground_cable_defaults" if power == "cable" else "overhead_line_defaults"
    table = BRANCH_PARAMETER_TABLES.get(power, OVERHEAD_LINE_DEFAULTS)
    nearest = min(table, key=lambda candidate: abs(candidate - voltage_kv))
    defaults = dict(table[nearest])
    defaults["matched_voltage_kv"] = nearest
    defaults["parameter_table"] = table_name
    defaults["parameter_source"] = "lookup_table"
    return defaults


def _classify_preview_branch(
    from_bus_id: str | None,
    to_bus_id: str | None,
    bus_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    if from_bus_id is None or to_bus_id is None:
        return "isolated"
    if from_bus_id == to_bus_id:
        return "self_loop"
    if from_bus_id.startswith("synthetic:") and to_bus_id.startswith("synthetic:"):
        return "isolated"
    if from_bus_id.startswith("synthetic:") or to_bus_id.startswith("synthetic:"):
        return "tap"
    if bus_by_id is not None:
        from_facility = bus_by_id.get(from_bus_id, {}).get("facility_id")
        to_facility = bus_by_id.get(to_bus_id, {}).get("facility_id")
        if from_facility and from_facility == to_facility:
            return "loop"
    return "inter_facility"


def _circuit_count_source(candidates: list[Mapping[str, Any]]) -> str:
    sources = {str(candidate.get("count_source") or "unknown") for candidate in candidates}
    if len(sources) == 1:
        return next(iter(sources))
    return "mixed"


def _circuit_tags(record: Mapping[str, Any]) -> dict[str, Any]:
    tags = dict(record.get("tags") or {})
    for key in ("voltage", "circuits", "cables"):
        if record.get(key) not in (None, ""):
            tags[key] = record.get(key)
    return tags


def _merge_fragmented_circuits(branches: list[dict[str, Any]]) -> dict[str, Any]:
    by_synthetic_endpoint: dict[str, list[int]] = {}
    for index, branch in enumerate(branches):
        for endpoint in (branch.get("from_bus_id"), branch.get("to_bus_id")):
            if isinstance(endpoint, str) and endpoint.startswith("synthetic:"):
                by_synthetic_endpoint.setdefault(endpoint, []).append(index)

    adjacency: dict[int, set[int]] = {index: set() for index in range(len(branches))}
    for indexes in by_synthetic_endpoint.values():
        for left in indexes:
            for right in indexes:
                if left == right:
                    continue
                if _merge_compatible(branches[left], branches[right]):
                    adjacency[left].add(right)

    seen: set[int] = set()
    output: list[dict[str, Any]] = []
    merged_circuit_count = 0
    merged_segment_count = 0
    for index, branch in enumerate(branches):
        if index in seen:
            continue
        stack = [index]
        group: set[int] = set()
        while stack:
            current = stack.pop()
            if current in group:
                continue
            group.add(current)
            stack.extend(adjacency[current] - group)
        seen.update(group)

        if len(group) == 1:
            output.append(branch)
            continue

        merged = _merged_circuit_branch([branches[item] for item in sorted(group)])
        if merged is None:
            output.extend(branches[item] for item in sorted(group))
            continue

        output.append(merged)
        merged_circuit_count += 1
        merged_segment_count += len(group)

    return {
        "branches": output,
        "merged_circuit_count": merged_circuit_count,
        "merged_segment_count": merged_segment_count,
    }


def _merge_compatible(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("power") == right.get("power")
        and left.get("voltage_kv") == right.get("voltage_kv")
        and left.get("location") == right.get("location")
    )


def _merged_circuit_branch(group: list[dict[str, Any]]) -> dict[str, Any] | None:
    endpoint_counts: dict[str, int] = {}
    endpoint_quality_by_bus: dict[str, Mapping[str, Any]] = {}
    for branch in group:
        qualities = list(branch.get("endpoint_quality") or [])
        for index, endpoint in enumerate((branch.get("from_bus_id"), branch.get("to_bus_id"))):
            if not isinstance(endpoint, str):
                return None
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
            if index < len(qualities):
                endpoint_quality_by_bus.setdefault(endpoint, qualities[index])

    boundary_endpoints = [
        endpoint
        for endpoint, count in endpoint_counts.items()
        if count == 1 or not endpoint.startswith("synthetic:")
    ]
    boundary_endpoints = _unique_strings(boundary_endpoints)
    if len(boundary_endpoints) != 2:
        return None

    first = group[0]
    source_ids = [str(branch["id"]) for branch in group]
    circuit_candidates = list(first.get("circuit_candidates") or [])
    circuit_count = max(int(branch.get("circuit_count") or 1) for branch in group)
    merged = dict(first)
    merged.update(
        {
            "id": "merged:" + "|".join(source_ids),
            "source": {"merged_source_ids": source_ids},
            "name": first.get("name") or "Merged circuit",
            "from_bus_id": boundary_endpoints[0],
            "to_bus_id": boundary_endpoints[1],
            "length_km": round(sum(float(branch.get("length_km") or 0.0) for branch in group), 6),
            "circuit_candidates": circuit_candidates,
            "circuit_count": circuit_count,
            "circuit_count_source": "merged_" + str(first.get("circuit_count_source") or "unknown"),
            "circuit_class": _classify_preview_branch(boundary_endpoints[0], boundary_endpoints[1]),
            "endpoint_quality": [
                dict(endpoint_quality_by_bus.get(boundary_endpoints[0], {"snap": "merged_boundary"})),
                dict(endpoint_quality_by_bus.get(boundary_endpoints[1], {"snap": "merged_boundary"})),
            ],
            "provenance": "merged_osm_circuit",
            "confidence": min(0.75, max(float(branch.get("confidence") or 0.0) for branch in group) + 0.05),
            "merged_segment_count": len(group),
            "merged_source_ids": source_ids,
            "merge_method": "synthetic_junction_union_find_voltage_compatible",
        }
    )
    return merged


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _drop_unreferenced_synthetic_buses(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    referenced = {
        endpoint
        for branch in branches
        for endpoint in (branch.get("from_bus_id"), branch.get("to_bus_id"))
        if isinstance(endpoint, str)
    }
    return [
        bus
        for bus in buses
        if not str(bus.get("id", "")).startswith("synthetic:") or bus["id"] in referenced
    ]


def _inferred_facility_transformers(buses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buses_by_facility: dict[str, list[dict[str, Any]]] = {}
    for bus in buses:
        facility_id = bus.get("facility_id")
        base_kv = bus.get("base_kv")
        if not facility_id or base_kv is None:
            continue
        buses_by_facility.setdefault(str(facility_id), []).append(bus)

    transformers = []
    for facility_id, facility_buses in sorted(buses_by_facility.items()):
        voltage_buses = sorted(
            facility_buses,
            key=lambda bus: float(bus.get("base_kv") or 0.0),
            reverse=True,
        )
        if len(voltage_buses) < 2:
            continue
        for index, (high_bus, low_bus) in enumerate(zip(voltage_buses, voltage_buses[1:]), start=1):
            high_kv = float(high_bus["base_kv"])
            low_kv = float(low_bus["base_kv"])
            defaults = _branch_defaults("line", high_kv)
            defaults["rate_mva"] = max(float(defaults.get("rate_mva") or 0.0), 300.0)
            transformers.append(
                {
                    "id": f"inferred:transformer:{facility_id}:{_format_voltage_id(high_kv)}-{_format_voltage_id(low_kv)}:{index}",
                    "source": {"facility_id": facility_id, "method": "multi_voltage_facility_split"},
                    "name": f"{high_bus.get('name') or facility_id} {high_kv:g}/{low_kv:g} kV transformer",
                    "power": "transformer",
                    "from_bus_id": high_bus["id"],
                    "to_bus_id": low_bus["id"],
                    "voltage_kv": high_kv,
                    "voltage_band": voltage_band(high_kv),
                    "length_km": 0.1,
                    "location": "facility",
                    "circuits": None,
                    "cables": None,
                    "circuit_candidates": [{"voltage_kv": high_kv, "circuit_count": 1, "count_source": "inferred_facility_transformer"}],
                    "circuit_count": 1,
                    "circuit_count_source": "inferred_facility_transformer",
                    "circuit_class": "inter_facility",
                    "parameter_defaults": defaults,
                    "endpoint_quality": [
                        {"snap": "facility_voltage_level", "bus_id": high_bus["id"]},
                        {"snap": "facility_voltage_level", "bus_id": low_bus["id"]},
                    ],
                    "provenance": "inferred_multi_voltage_facility_transformer",
                    "confidence": 0.6,
                }
            )
    return transformers


def _generator_capacity(tags: Mapping[str, Any]) -> tuple[float | None, str | None]:
    for key in (
        "generator:output:electricity",
        "plant:output:electricity",
        "output:electricity",
        "generator:output",
        "capacity",
    ):
        value = parse_power_mw(tags.get(key))
        if value is not None:
            return value, key
    return None, None


def _row_to_record(row: Any) -> dict[str, Any]:
    data = dict(row)
    tags = _load_json(data.pop("tags_json", None), {})
    geometry = _load_json(data.pop("geometry_json", None), None)
    data["tags"] = tags
    data["geometry"] = geometry
    data["voltage_kv"] = normalize_voltage(data.get("voltage") or tags.get("voltage"))
    data["asset_kind"] = _asset_kind(data["power"])
    data["service_territory"] = infer_service_territory(tags, data.get("name"))
    return data


def _facility_radius_km(record: Mapping[str, Any], lat: float | None, lon: float | None) -> tuple[float, str]:
    if lat is None or lon is None:
        return 0.0, "none"
    geometry = record.get("geometry") or []
    coords = [
        (point.get("lat"), point.get("lon"))
        for point in geometry
        if point.get("lat") is not None and point.get("lon") is not None
    ]
    if coords:
        radius = max(_haversine_km((lat, lon), (float(point_lat), float(point_lon))) for point_lat, point_lon in coords)
        capped_radius = min(radius, FACILITY_FOOTPRINT_RADIUS_MAX_KM)
        return round(max(capped_radius, FACILITY_FOOTPRINT_RADIUS_MIN_KM), 6), "geometry_footprint"
    if record.get("asset_kind") == "bus_candidate" and record.get("power") in {"plant", "generator", "substation", "sub_station", "transformer"}:
        return POINT_FACILITY_BUFFER_KM, "buffered_point_facility"
    return 0.0, "point"


def _bus_id_for_voltage_level(base_bus_id: str, voltage_kv: float | None, voltage_levels: list[float | None]) -> str:
    if len([value for value in voltage_levels if value is not None]) <= 1:
        return base_bus_id
    if voltage_kv is None:
        return base_bus_id
    return f"{base_bus_id}:voltage:{_format_voltage_id(voltage_kv)}"


def _format_voltage_id(voltage_kv: float) -> str:
    return str(int(voltage_kv)) if float(voltage_kv).is_integer() else str(voltage_kv).replace(".", "_")


def build_topology_preview(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
    min_voltage_kv: float | None = None,
    consumer_proxies: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    _validate_derate(hk_intertie_derate)
    _validate_min_voltage(min_voltage_kv)
    calibration = _load_calibration_bundle()
    snapshot = _demand_snapshot(demand_snapshot, calibration)
    records = [_row_to_record(row) for row in rows]
    buses: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    generators: list[dict[str, Any]] = []

    for record in records:
        if record["asset_kind"] != "bus_candidate":
            continue
        base_bus_id = f"osm:{record['osm_type']}:{record['osm_id']}"
        facility_id = base_bus_id
        voltage_levels = record["voltage_kv"] or [None]
        facility_radius_km, facility_match_method = _facility_radius_km(record, record.get("lat"), record.get("lon"))
        for base_kv in sorted(voltage_levels, reverse=True, key=lambda value: value or 0.0):
            if _below_min_voltage(base_kv, min_voltage_kv):
                continue
            bus_id = _bus_id_for_voltage_level(base_bus_id, base_kv, voltage_levels)
            buses.append(
                {
                    "id": bus_id,
                    "source": {"osm_type": record["osm_type"], "osm_id": record["osm_id"]},
                    "facility_id": facility_id,
                    "name": record.get("name"),
                    "power": record["power"],
                    "lat": record.get("lat"),
                    "lon": record.get("lon"),
                    "facility_radius_km": facility_radius_km,
                    "facility_match_method": facility_match_method,
                    "base_kv": base_kv,
                    "voltage_band": voltage_band(base_kv),
                    "service_territory": record["service_territory"],
                    "provenance": "osm_voltage_level" if len(voltage_levels) > 1 else "osm",
                    "confidence": 0.85 if base_kv else 0.55,
                }
            )
        if record["power"] in {"plant", "generator"}:
            pmax_mw, capacity_tag = _generator_capacity(record["tags"])
            generators.append(
                {
                    "id": f"gen:{record['osm_type']}:{record['osm_id']}",
                    "source_osm_type": record["osm_type"],
                    "source_osm_id": record["osm_id"],
                    "bus_id": _bus_id_for_voltage_level(base_bus_id, max(record["voltage_kv"]) if record["voltage_kv"] else None, voltage_levels),
                    "name": record.get("name"),
                    "operator": record.get("operator") or record["tags"].get("operator"),
                    "source": record["tags"].get("generator:source"),
                    "method": record["tags"].get("generator:method"),
                    "pmax_mw": pmax_mw,
                    "capacity_tag": capacity_tag,
                    "capacity_raw": record["tags"].get(capacity_tag) if capacity_tag else None,
                    "provenance": "osm_capacity_tag" if pmax_mw is not None else "osm_without_capacity",
                    "provenance_chain": ["osm_capacity_tag"] if pmax_mw is not None else ["osm_without_capacity"],
                    "confidence": 0.7 if pmax_mw is not None else 0.45,
                }
            )

    synthetic_buses: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["asset_kind"] != "branch":
            continue
        voltage_kv = max(record["voltage_kv"]) if record["voltage_kv"] else None
        if _below_min_voltage(voltage_kv, min_voltage_kv):
            continue
        geometry = record.get("geometry") or []
        if len(geometry) < 2:
            continue

        endpoints = [geometry[0], geometry[-1]]
        endpoint_bus_ids = []
        endpoint_quality = []
        for index, endpoint in enumerate(endpoints):
            point = (endpoint.get("lat"), endpoint.get("lon"))
            if point[0] is None or point[1] is None:
                endpoint_bus_ids.append(None)
                endpoint_quality.append({"snap": "missing_geometry"})
                continue
            snap_candidates = [*buses, *synthetic_buses.values()]
            bus_id, distance = _nearest_bus(snap_candidates, point, snap_tolerance_km, voltage_kv=voltage_kv)
            if bus_id is None:
                synthetic_id = f"synthetic:{record['osm_type']}:{record['osm_id']}:{index}"
                if synthetic_id not in synthetic_buses:
                    synthetic_buses[synthetic_id] = {
                        "id": synthetic_id,
                        "source": {
                            "osm_type": record["osm_type"],
                            "osm_id": record["osm_id"],
                            "endpoint_index": index,
                        },
                        "name": None,
                        "power": "inferred_terminal",
                        "lat": point[0],
                        "lon": point[1],
                        "facility_radius_km": 0.0,
                        "facility_match_method": "synthetic_endpoint",
                        "base_kv": max(record["voltage_kv"]) if record["voltage_kv"] else None,
                        "voltage_band": voltage_band(max(record["voltage_kv"]) if record["voltage_kv"] else None),
                        "service_territory": record["service_territory"],
                        "provenance": "osm_branch_endpoint",
                        "confidence": 0.35,
                }
                endpoint_bus_ids.append(synthetic_id)
                endpoint_quality.append({"snap": "synthetic", "nearest_bus_km": distance})
            elif str(bus_id).startswith("synthetic:"):
                endpoint_bus_ids.append(bus_id)
                endpoint_quality.append({"snap": "matched_synthetic_junction", "distance_km": distance})
            else:
                endpoint_bus_ids.append(bus_id)
                endpoint_quality.append({"snap": "matched", "distance_km": distance})

        defaults = _branch_defaults(record["power"], voltage_kv)
        length_km = _geometry_length_km(geometry)
        circuit_candidates = split_voltage_circuits(_circuit_tags(record))
        bus_by_id_for_class = {bus["id"]: bus for bus in [*buses, *synthetic_buses.values()]}
        circuit_class = _classify_preview_branch(endpoint_bus_ids[0], endpoint_bus_ids[1], bus_by_id_for_class)
        branches.append(
            {
                "id": f"osm:{record['osm_type']}:{record['osm_id']}",
                "source": {"osm_type": record["osm_type"], "osm_id": record["osm_id"]},
                "name": record.get("name"),
                "power": record["power"],
                "from_bus_id": endpoint_bus_ids[0],
                "to_bus_id": endpoint_bus_ids[1],
                "voltage_kv": voltage_kv,
                "voltage_band": voltage_band(voltage_kv),
                "length_km": length_km,
                "location": record.get("location"),
                "circuits": record.get("circuits"),
                "cables": record.get("cables"),
                "circuit_candidates": circuit_candidates,
                "circuit_count": sum(candidate["circuit_count"] for candidate in circuit_candidates),
                "circuit_count_source": _circuit_count_source(circuit_candidates),
                "circuit_class": circuit_class,
                "parameter_defaults": defaults,
                "endpoint_quality": endpoint_quality,
                "provenance": "osm_with_inferred_parameters",
                "confidence": 0.65 if voltage_kv and length_km else 0.4,
            }
        )

    branches.extend(_inferred_facility_transformers(buses))
    buses.extend(synthetic_buses.values())
    merge_report = _merge_fragmented_circuits(branches)
    branches = merge_report["branches"]
    buses = _drop_unreferenced_synthetic_buses(buses, branches)
    if include_hk_interties:
        branches.extend(_hk_intertie_branches(buses, derate=hk_intertie_derate))
    load_allocations = _allocate_loads(
        buses,
        demand_snapshot=demand_snapshot,
        calibration=calibration,
        consumer_proxies=list(consumer_proxies or []),
    )
    allocation_validation = _load_allocation_validation(load_allocations)
    backbone_branches = _synthetic_service_territory_backbone(buses, branches, load_allocations)
    branches.extend(backbone_branches)
    circuit_class_counts = _count_by(branches, "circuit_class")
    circuit_candidate_count = sum(len(branch.get("circuit_candidates") or []) for branch in branches)
    circuit_count_total = sum(int(branch.get("circuit_count") or 1) for branch in branches)
    inferred_facility_transformer_count = sum(
        1
        for branch in branches
        if branch.get("provenance") == "inferred_multi_voltage_facility_transformer"
    )
    return {
        "metadata": {
            "schema": "tiangou.topology_preview.v1",
            "snap_tolerance_km": snap_tolerance_km,
            "demand_snapshot": demand_snapshot,
            "demand_snapshot_label": snapshot["label"],
            "load_factor": snapshot["load_factor"],
            "demand_allocation_method": allocation_validation["method"],
            "load_power_factor": LOAD_DEFAULTS["power_factor"],
            "load_allocation_validation": allocation_validation,
            "calibration": _topology_calibration_metadata(calibration),
            "calibration_warnings": calibration.warnings if calibration is not None else [],
            "include_hk_interties": include_hk_interties,
            "hk_intertie_derate": hk_intertie_derate,
            "min_voltage_kv": min_voltage_kv,
            "bus_count": len(buses),
            "branch_count": len(branches),
            "generator_count": len(generators),
            "load_count": len(load_allocations),
            "synthetic_service_territory_backbone_count": len(backbone_branches),
            "circuit_class_counts": circuit_class_counts,
            "circuit_candidate_count": circuit_candidate_count,
            "circuit_count_total": circuit_count_total,
            "merged_circuit_count": merge_report["merged_circuit_count"],
            "merged_segment_count": merge_report["merged_segment_count"],
            "inferred_facility_transformer_count": inferred_facility_transformer_count,
        },
        "buses": buses,
        "branches": branches,
        "generators": generators,
        "loads": load_allocations,
        "quality": _quality_summary(records, buses, branches, min_voltage_kv=min_voltage_kv),
    }


def build_powermodels_preview(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
    min_voltage_kv: float | None = None,
    consumer_proxies: Iterable[Mapping[str, Any]] | None = None,
    solver_include_policy: str = DEFAULT_SOLVER_INCLUDE_POLICY,
    min_solver_generator_mw: float = DEFAULT_MIN_SOLVER_GENERATOR_MW,
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    topology = build_topology_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
        consumer_proxies=consumer_proxies,
    )
    return topology_preview_to_powermodels(
        topology,
        solver_include_policy=solver_include_policy,
        min_solver_generator_mw=min_solver_generator_mw,
        include_synthetic_generator_connections=include_synthetic_generator_connections,
    )


def build_powermodels_validation(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
    min_voltage_kv: float | None = None,
    consumer_proxies: Iterable[Mapping[str, Any]] | None = None,
    solver_include_policy: str = DEFAULT_SOLVER_INCLUDE_POLICY,
    min_solver_generator_mw: float = DEFAULT_MIN_SOLVER_GENERATOR_MW,
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
        consumer_proxies=consumer_proxies,
        solver_include_policy=solver_include_policy,
        min_solver_generator_mw=min_solver_generator_mw,
        include_synthetic_generator_connections=include_synthetic_generator_connections,
    )
    return validate_powermodels_case(case)


def topology_preview_to_powermodels(
    topology: Mapping[str, Any],
    *,
    solver_include_policy: str = DEFAULT_SOLVER_INCLUDE_POLICY,
    min_solver_generator_mw: float = DEFAULT_MIN_SOLVER_GENERATOR_MW,
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    _validate_solver_include_policy(solver_include_policy)
    _validate_min_solver_generator_mw(min_solver_generator_mw)
    raw_buses = list(topology["buses"])
    raw_branch_candidates = [
        branch
        for branch in topology["branches"]
        if branch.get("from_bus_id") and branch.get("to_bus_id") and branch.get("from_bus_id") != branch.get("to_bus_id")
    ]
    raw_branches = _solver_branch_candidates(raw_branch_candidates, solver_include_policy=solver_include_policy)
    raw_loads = list(topology["loads"])
    tagged_generators = _tagged_generators(
        topology.get("generators", []),
        min_solver_generator_mw=min_solver_generator_mw,
    )
    active_selection = _active_preview_bus_selection(raw_buses, raw_branches, raw_loads, tagged_generators)
    active_bus_ids = active_selection["active_bus_ids"]
    buses = [bus for bus in raw_buses if bus["id"] in active_bus_ids]
    branches = [
        branch
        for branch in raw_branches
        if branch["from_bus_id"] in active_bus_ids and branch["to_bus_id"] in active_bus_ids
    ]
    loads = [load for load in raw_loads if load["bus_id"] in active_bus_ids]
    generator_promotion = _promote_generators_to_active_buses(
        generators=tagged_generators,
        raw_buses=raw_buses,
        buses=buses,
        branches=branches,
        active_bus_ids=active_bus_ids,
        include_synthetic_generator_connections=include_synthetic_generator_connections
        and solver_include_policy == "demo_full_osm",
    )
    buses = generator_promotion["buses"]
    branches = generator_promotion["branches"]
    tagged_generators = generator_promotion["generators"]
    voltage_inference = _infer_missing_bus_voltages(buses, branches)
    equivalent_generators = _equivalent_generators(buses, branches, loads)
    all_generators = [*tagged_generators, *equivalent_generators]

    bus_id_map = {bus["id"]: str(index) for index, bus in enumerate(buses, start=1)}
    gen_bus_ids = {generator["bus_id"] for generator in all_generators}
    load_bus_ids = {load["bus_id"] for load in loads}
    reference_bus_ids = _reference_bus_ids_by_island(buses, branches, gen_bus_ids)
    dropped_passive_branch_count = max(0, len(raw_branches) - len(branches))

    bus_dict = {}
    for bus in buses:
        bus_number = bus_id_map[bus["id"]]
        bus_type = _powermodels_bus_type(bus["id"], reference_bus_ids, gen_bus_ids, load_bus_ids)
        bus_dict[bus_number] = {
            "index": int(bus_number),
            "bus_i": int(bus_number),
            "bus_type": bus_type,
            "type": bus_type,
            "base_kv": bus.get("base_kv") or 132.0,
            "vmin": 0.9,
            "vmax": 1.1,
            "vm": 1.0,
            "va": 0.0,
            "area": 1,
            "zone": 1,
            "source_id": bus["id"],
            "name": bus.get("name"),
            "lat": bus.get("lat"),
            "lon": bus.get("lon"),
            "provenance": bus.get("provenance"),
            "confidence": bus.get("confidence"),
            "service_territory": bus.get("service_territory"),
            "voltage_band": bus.get("voltage_band"),
            "facility_id": bus.get("facility_id"),
            "facility_radius_km": bus.get("facility_radius_km"),
            "facility_match_method": bus.get("facility_match_method"),
        }

    bus_by_id = {bus["id"]: bus for bus in buses}
    branch_dict = {}
    for index, branch in enumerate(branches, start=1):
        branch_dict[str(index)] = _powermodels_branch(index, branch, bus_id_map, bus_by_id)

    load_dict = {}
    for index, load in enumerate(loads, start=1):
        load_dict[str(index)] = {
            "index": index,
            "load_bus": int(bus_id_map[load["bus_id"]]),
            "pd": round(load["pd_mw"] / BASE_MVA, 6),
            "qd": round(load["qd_mvar"] / BASE_MVA, 6),
            "status": 1,
            "source_id": load["id"],
            "provenance": load.get("provenance"),
            "confidence": load.get("confidence"),
            "service_territory": load.get("service_territory"),
            "district": load.get("district"),
            "sector": load.get("sector"),
            "snapshot": load.get("snapshot"),
            "allocation_method": load.get("allocation_method"),
            "allocation_weight": load.get("allocation_weight"),
            "source_file": load.get("source_file"),
            "source_files": load.get("source_files"),
            "source_year": load.get("source_year"),
            "source_period": load.get("source_period"),
            "source_periods": load.get("source_periods"),
            "source_energy_gwh": load.get("source_energy_gwh"),
            "inference_method": load.get("inference_method"),
            "geometry_provenance": load.get("geometry_provenance"),
            "proxy_count": load.get("proxy_count"),
            "proxy_total_weight": load.get("proxy_total_weight"),
            "proxy_assignment_distance_avg_km": load.get("proxy_assignment_distance_avg_km"),
            "proxy_assignment_distance_median_km": load.get("proxy_assignment_distance_median_km"),
        }

    gen_dict = {}
    for index, generator in enumerate(all_generators, start=1):
        gen_dict[str(index)] = {
            "index": index,
            "source_id": generator["id"],
            "source_osm_type": generator.get("source_osm_type"),
            "source_osm_id": generator.get("source_osm_id"),
            "name": generator.get("name"),
            "operator": generator.get("operator"),
            "gen_bus": int(bus_id_map[generator["bus_id"]]),
            "pg": 0.0,
            "qg": 0.0,
            "pmax": round(generator["pmax_mw"] / BASE_MVA, 6),
            "pmin": round(generator["pmax_mw"] * (generator.get("pmin_fraction") or 0.0) / BASE_MVA, 6),
            "qmax": round(generator["pmax_mw"] * 0.6 / BASE_MVA, 6),
            "qmin": round(-generator["pmax_mw"] * 0.6 / BASE_MVA, 6),
            "vg": 1.0,
            "mbase": BASE_MVA,
            "gen_status": 1,
            "model": 2,
            "ncost": 3,
            "cost": generator["cost"],
            "provenance": generator.get("provenance"),
            "provenance_chain": generator.get("provenance_chain"),
            "confidence": generator.get("confidence"),
            "service_territory": generator.get("service_territory"),
            "energy_source": generator.get("energy_source"),
            "resource_type": generator.get("resource_type"),
            "cost_class": generator.get("cost_class"),
            "capacity_tag": generator.get("capacity_tag"),
            "capacity_raw": generator.get("capacity_raw"),
            "connection_method": generator.get("connection_method"),
            "assigned_bus_id": generator.get("assigned_bus_id"),
            "original_bus_id": generator.get("original_bus_id"),
        }

    component_metadata = _solver_component_metadata(bus_dict, branch_dict, load_dict, gen_dict)

    return {
        "name": "hong_kong_osm_preview",
        "source_version": "tiangou.powermodels_preview.v1",
        "demand_snapshot": topology["metadata"]["demand_snapshot"],
        "demand_allocation_method": topology["metadata"]["demand_allocation_method"],
        "include_hk_interties": topology["metadata"]["include_hk_interties"],
        "hk_intertie_derate": topology["metadata"]["hk_intertie_derate"],
        "min_voltage_kv": topology["metadata"]["min_voltage_kv"],
        "solver_include_policy": solver_include_policy,
        "min_solver_generator_mw": min_solver_generator_mw,
        "include_synthetic_generator_connections": include_synthetic_generator_connections,
        "baseMVA": BASE_MVA,
        "per_unit": True,
        "bus": bus_dict,
        "branch": branch_dict,
        "gen": gen_dict,
        "load": load_dict,
        "shunt": {},
        "storage": {},
        "switch": {},
        "dcline": {},
        "_metadata": {
            "topology_schema": topology["metadata"]["schema"],
            "demand_snapshot": topology["metadata"]["demand_snapshot"],
            "demand_snapshot_label": topology["metadata"]["demand_snapshot_label"],
            "load_factor": topology["metadata"]["load_factor"],
            "demand_allocation_method": topology["metadata"]["demand_allocation_method"],
            "load_power_factor": topology["metadata"]["load_power_factor"],
            "load_allocation_validation": topology["metadata"].get("load_allocation_validation"),
            "calibration": topology["metadata"].get("calibration"),
            "calibration_warnings": topology["metadata"].get("calibration_warnings", []),
            "include_hk_interties": topology["metadata"]["include_hk_interties"],
            "hk_intertie_derate": topology["metadata"]["hk_intertie_derate"],
            "min_voltage_kv": topology["metadata"]["min_voltage_kv"],
            "solver_include_policy": solver_include_policy,
            "min_solver_generator_mw": min_solver_generator_mw,
            "include_synthetic_generator_connections": include_synthetic_generator_connections,
            "bus_count": len(bus_dict),
            "branch_count": len(branch_dict),
            "load_count": len(load_dict),
            "gen_count": len(gen_dict),
            "raw_bus_count": len(raw_buses),
            "raw_branch_count": len(raw_branch_candidates),
            "raw_solver_candidate_branch_count": len(raw_branches),
            "retained_bus_count": len(buses),
            "retained_branch_count": len(branches),
            "dropped_passive_bus_count": len(raw_buses) - len(buses),
            "dropped_passive_branch_count": dropped_passive_branch_count,
            "dropped_non_interfacility_branch_count": len(raw_branch_candidates) - len(raw_branches),
            "dropped_no_load_generation_island_count": active_selection["dropped_no_load_generation_island_count"],
            "dropped_no_load_generation_bus_count": active_selection["dropped_no_load_generation_bus_count"],
            "dropped_no_load_generation_pmax_mw": active_selection["dropped_no_load_generation_pmax_mw"],
            "component_count": component_metadata["component_count"],
            "load_bearing_component_count": component_metadata["load_bearing_component_count"],
            "largest_component_bus_count": component_metadata["largest_component_bus_count"],
            "largest_component_bus_share": component_metadata["largest_component_bus_share"],
            "largest_component_load_mw": component_metadata["largest_component_load_mw"],
            "largest_component_load_share": component_metadata["largest_component_load_share"],
            "largest_component_pmax_mw": component_metadata["largest_component_pmax_mw"],
            "largest_component_pmax_share": component_metadata["largest_component_pmax_share"],
            "cleanup_summary": {
                "raw_bus_count": len(raw_buses),
                "raw_branch_count": len(raw_branch_candidates),
                "raw_solver_candidate_branch_count": len(raw_branches),
                "retained_bus_count": len(buses),
                "retained_branch_count": len(branches),
                "dropped_passive_bus_count": len(raw_buses) - len(buses),
                "dropped_passive_branch_count": dropped_passive_branch_count,
                "dropped_non_interfacility_branch_count": len(raw_branch_candidates) - len(raw_branches),
                "dropped_no_load_generation_island_count": active_selection["dropped_no_load_generation_island_count"],
                "dropped_no_load_generation_bus_count": active_selection["dropped_no_load_generation_bus_count"],
                "dropped_no_load_generation_pmax_mw": active_selection["dropped_no_load_generation_pmax_mw"],
                "component_count": component_metadata["component_count"],
                "load_bearing_component_count": component_metadata["load_bearing_component_count"],
                "largest_component_bus_count": component_metadata["largest_component_bus_count"],
                "largest_component_bus_share": component_metadata["largest_component_bus_share"],
                "largest_component_load_mw": component_metadata["largest_component_load_mw"],
                "largest_component_load_share": component_metadata["largest_component_load_share"],
                "largest_component_pmax_mw": component_metadata["largest_component_pmax_mw"],
                "largest_component_pmax_share": component_metadata["largest_component_pmax_share"],
            },
            "tagged_gen_count": len(tagged_generators),
            "equivalent_gen_count": len(equivalent_generators),
            "synthetic_generator_connection_branch_count": sum(
                1
                for branch in branches
                if branch.get("provenance") == "synthetic_connection_to_nearest_substation"
            ),
            "synthetic_branch_count": sum(1 for branch in branches if _is_synthetic_branch(branch)),
            "inferred_transformer_branch_count": sum(1 for branch in branch_dict.values() if branch.get("transformer")),
            "solver_circuit_class_counts": _count_by(branch_dict.values(), "circuit_class"),
            "voltage_inference": voltage_inference,
            "parameter_lookup_tables": _parameter_lookup_metadata(),
            "reference_bus_count": len(reference_bus_ids),
            "total_pd_mw": round(sum(load["pd_mw"] for load in loads), 3),
            "total_tagged_pmax_mw": round(sum(gen["pmax_mw"] for gen in tagged_generators), 3),
            "total_equivalent_pmax_mw": round(sum(gen["pmax_mw"] for gen in equivalent_generators), 3),
            "total_pmax_mw": round(sum(gen["pmax_mw"] for gen in all_generators), 3),
            "provenance_summary": {
                "bus": _count_by(buses, "provenance"),
                "branch": _count_by(branches, "provenance"),
                "gen": _count_by(all_generators, "provenance"),
                "load": _count_by(loads, "provenance"),
            },
            "notes": [
                "This is a PowerModels handoff preview built from public OSM topology and inferred parameters.",
                "Equivalent generators represent territory-level local supply or imports; run relaxation and validation before optimization.",
            ],
        },
    }


def _solver_component_metadata(
    buses: Mapping[str, Any],
    branches: Mapping[str, Any],
    loads: Mapping[str, Any],
    generators: Mapping[str, Any],
) -> dict[str, Any]:
    island_report = _case_island_report(buses, branches, loads, generators)
    islands = island_report["islands"]
    total_buses = len(buses)
    total_load_mw = sum(float(island["pd_mw"]) for island in islands)
    total_pmax_mw = sum(float(island["pmax_mw"]) for island in islands)
    largest = max(
        islands,
        key=lambda island: (
            float(island["pd_mw"]),
            int(island["bus_count"]),
            float(island["pmax_mw"]),
        ),
        default={"bus_count": 0, "pd_mw": 0.0, "pmax_mw": 0.0},
    )

    return {
        "component_count": island_report["island_count"],
        "load_bearing_component_count": sum(1 for island in islands if float(island["pd_mw"]) > 0.0),
        "largest_component_bus_count": int(largest["bus_count"]),
        "largest_component_bus_share": round(int(largest["bus_count"]) / total_buses, 6) if total_buses else 0.0,
        "largest_component_load_mw": round(float(largest["pd_mw"]), 3),
        "largest_component_load_share": round(float(largest["pd_mw"]) / total_load_mw, 6) if total_load_mw else 0.0,
        "largest_component_pmax_mw": round(float(largest["pmax_mw"]), 3),
        "largest_component_pmax_share": round(float(largest["pmax_mw"]) / total_pmax_mw, 6) if total_pmax_mw else 0.0,
    }


def _active_preview_bus_selection(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
    loads: list[dict[str, Any]],
    tagged_generators: list[dict[str, Any]],
) -> dict[str, Any]:
    seed_bus_ids = {load["bus_id"] for load in loads}
    if not seed_bus_ids:
        return {
            "active_bus_ids": {bus["id"] for bus in buses},
            "dropped_no_load_generation_island_count": 0,
            "dropped_no_load_generation_bus_count": 0,
            "dropped_no_load_generation_pmax_mw": 0.0,
        }

    active_bus_ids: set[str] = set()
    dropped_generation_islands = 0
    dropped_generation_bus_count = 0
    dropped_generation_pmax_mw = 0.0
    generator_pmax_by_bus_id: dict[str, float] = {}
    for generator in tagged_generators:
        generator_pmax_by_bus_id[generator["bus_id"]] = generator_pmax_by_bus_id.get(generator["bus_id"], 0.0) + float(generator["pmax_mw"])

    for component in _preview_components(buses, branches):
        if component & seed_bus_ids:
            active_bus_ids.update(component)
        elif component & set(generator_pmax_by_bus_id):
            dropped_generation_islands += 1
            dropped_generation_bus_count += len(component)
            dropped_generation_pmax_mw += sum(generator_pmax_by_bus_id.get(bus_id, 0.0) for bus_id in component)
    return {
        "active_bus_ids": active_bus_ids,
        "dropped_no_load_generation_island_count": dropped_generation_islands,
        "dropped_no_load_generation_bus_count": dropped_generation_bus_count,
        "dropped_no_load_generation_pmax_mw": round(dropped_generation_pmax_mw, 3),
    }


def _solver_branch_candidates(
    branches: list[Mapping[str, Any]],
    *,
    solver_include_policy: str,
) -> list[dict[str, Any]]:
    if solver_include_policy == "strict_transmission":
        return [
            dict(branch)
            for branch in branches
            if branch.get("circuit_class") == "inter_facility"
        ]

    retained = []
    for branch in branches:
        circuit_class = str(branch.get("circuit_class") or "unknown")
        if circuit_class == "self_loop":
            continue
        retained_branch = dict(branch)
        if circuit_class == "inter_facility":
            retained_branch.setdefault("solver_retention_reason", "inter_facility")
        elif circuit_class in {"tap", "isolated"}:
            retained_branch["retention_policy"] = "demo_full_osm"
            retained_branch["solver_retention_reason"] = f"demo_retained_{circuit_class}"
            retained_branch["confidence"] = min(float(retained_branch.get("confidence") or 0.0), 0.45)
        else:
            retained_branch["retention_policy"] = "demo_full_osm"
            retained_branch["solver_retention_reason"] = f"demo_retained_{circuit_class}"
        retained.append(retained_branch)
    return retained


def _promote_generators_to_active_buses(
    *,
    generators: list[dict[str, Any]],
    raw_buses: list[dict[str, Any]],
    buses: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    active_bus_ids: set[str],
    include_synthetic_generator_connections: bool,
) -> dict[str, Any]:
    raw_by_id = {bus["id"]: bus for bus in raw_buses}
    promoted_generators = []
    promoted_branches = list(branches)
    promoted_buses = list(buses)
    promoted_bus_ids = {bus["id"] for bus in promoted_buses}

    for generator in generators:
        if generator["bus_id"] in active_bus_ids:
            promoted = dict(generator)
            promoted["connection_method"] = "existing_solver_bus"
            promoted["provenance_chain"] = _unique_strings([*promoted.get("provenance_chain", []), str(promoted.get("provenance") or "unknown")])
            promoted_generators.append(promoted)
            continue

        if not include_synthetic_generator_connections:
            continue
        source_bus = raw_by_id.get(generator["bus_id"])
        assigned_bus = _nearest_generator_connection_bus(source_bus, promoted_buses)
        if source_bus is None or assigned_bus is None:
            continue
        if source_bus["id"] not in promoted_bus_ids:
            site_bus = dict(source_bus)
            site_bus["provenance"] = "inferred_generator_connection"
            site_bus["confidence"] = min(float(site_bus.get("confidence") or 0.0), 0.55)
            promoted_buses.append(site_bus)
            promoted_bus_ids.add(site_bus["id"])

        promoted = dict(generator)
        promoted["connection_method"] = "synthetic_connection_to_nearest_substation"
        promoted["assigned_bus_id"] = assigned_bus["id"]
        promoted["original_bus_id"] = generator["bus_id"]
        promoted["provenance"] = "inferred_generator_connection"
        promoted["provenance_chain"] = _unique_strings([*promoted.get("provenance_chain", []), "inferred_generator_connection", "synthetic_connection_to_nearest_substation"])
        promoted["confidence"] = min(float(generator.get("confidence") or 0.0), 0.55)
        promoted_generators.append(promoted)

        connection_branch = _synthetic_generator_connection_branch(
            generator=promoted,
            source_bus=source_bus,
            assigned_bus=assigned_bus,
        )
        promoted_branches.append(connection_branch)

    return {
        "buses": promoted_buses,
        "branches": promoted_branches,
        "generators": promoted_generators,
    }


def _nearest_generator_connection_bus(
    source_bus: Mapping[str, Any] | None,
    buses: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if source_bus is None or source_bus.get("lat") is None or source_bus.get("lon") is None:
        return None
    point = (float(source_bus["lat"]), float(source_bus["lon"]))
    preferred_territory = source_bus.get("service_territory")
    candidates = [
        bus
        for bus in buses
        if bus.get("lat") is not None
        and bus.get("lon") is not None
        and bus.get("power") in {"substation", "sub_station", "transformer", "plant", "generator", "busbar", "switchgear"}
        and (preferred_territory is None or bus.get("service_territory") in {None, preferred_territory})
        and bus.get("voltage_band") in {"extra_high_voltage", "high_voltage", "subtransmission", "unknown"}
    ]
    if not candidates:
        candidates = [bus for bus in buses if bus.get("lat") is not None and bus.get("lon") is not None]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda bus: (
            _haversine_km(point, (float(bus["lat"]), float(bus["lon"]))),
            0 if bus.get("service_territory") == preferred_territory else 1,
            -(float(bus.get("base_kv") or 0.0)),
        ),
    )


def _synthetic_generator_connection_branch(
    *,
    generator: Mapping[str, Any],
    source_bus: Mapping[str, Any],
    assigned_bus: Mapping[str, Any],
) -> dict[str, Any]:
    from_point = (float(source_bus["lat"]), float(source_bus["lon"]))
    to_point = (float(assigned_bus["lat"]), float(assigned_bus["lon"]))
    length_km = max(_haversine_km(from_point, to_point), 0.1)
    voltage_kv = assigned_bus.get("base_kv") or source_bus.get("base_kv") or 132.0
    defaults = _branch_defaults("cable", float(voltage_kv))
    defaults["rate_mva"] = max(float(defaults.get("rate_mva") or 0.0), float(generator["pmax_mw"]) * 1.2)
    defaults["parameter_source"] = "synthetic_connection_to_nearest_substation"
    return {
        "id": f"synthetic:generator-connection:{generator['id']}",
        "source": {"generator_id": generator["id"], "source_bus_id": source_bus["id"], "assigned_bus_id": assigned_bus["id"]},
        "name": f"{generator['id']} synthetic generator connection",
        "power": "synthetic_generator_connection",
        "from_bus_id": source_bus["id"],
        "to_bus_id": assigned_bus["id"],
        "voltage_kv": float(voltage_kv),
        "voltage_band": voltage_band(float(voltage_kv)),
        "length_km": round(length_km, 6),
        "location": "synthetic",
        "circuits": None,
        "cables": None,
        "circuit_candidates": [{"voltage_kv": float(voltage_kv), "circuit_count": 1, "count_source": "synthetic_generator_connection"}],
        "circuit_count": 1,
        "circuit_count_source": "synthetic_generator_connection",
        "circuit_class": "tap",
        "parameter_defaults": defaults,
        "endpoint_quality": [{"snap": "generator_site"}, {"snap": "assigned_solver_bus"}],
        "provenance": "synthetic_connection_to_nearest_substation",
        "retention_policy": "demo_full_osm",
        "solver_retention_reason": "promoted_osm_generator_connection",
        "confidence": 0.45,
    }


def _infer_missing_bus_voltages(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
) -> dict[str, Any]:
    incident_voltages: dict[str, list[float]] = {bus["id"]: [] for bus in buses}
    tagged_voltage_by_bus = {
        bus["id"]: float(bus["base_kv"])
        for bus in buses
        if bus.get("base_kv") is not None
    }
    for branch in branches:
        voltage_kv = branch.get("voltage_kv")
        if voltage_kv is None:
            endpoint_ids = [
                str(endpoint)
                for endpoint in (branch.get("from_bus_id"), branch.get("to_bus_id"))
                if endpoint in incident_voltages
            ]
            endpoint_voltages = [
                tagged_voltage_by_bus[endpoint]
                for endpoint in endpoint_ids
                if endpoint in tagged_voltage_by_bus
            ]
            if not endpoint_voltages:
                continue
            inferred_branch_voltage = _consensus_voltage(endpoint_voltages)
            for endpoint in endpoint_ids:
                if endpoint not in tagged_voltage_by_bus:
                    incident_voltages[endpoint].append(inferred_branch_voltage)
            continue
        for endpoint in (branch.get("from_bus_id"), branch.get("to_bus_id")):
            if endpoint in incident_voltages:
                incident_voltages[str(endpoint)].append(float(voltage_kv))

    tagged_count = 0
    inferred_count = 0
    unresolved_count = 0
    by_voltage: dict[str, int] = {}
    for bus in buses:
        if bus.get("base_kv") is not None:
            tagged_count += 1
            continue

        candidates = incident_voltages.get(bus["id"], [])
        if not candidates:
            unresolved_count += 1
            continue

        inferred_voltage = _consensus_voltage(candidates)
        bus["base_kv"] = inferred_voltage
        bus["voltage_band"] = voltage_band(inferred_voltage)
        bus["voltage_inference"] = {
            "method": "incident_branch_voltage_consensus",
            "candidate_voltages_kv": sorted(set(candidates)),
            "sample_count": len(candidates),
        }
        bus["confidence"] = max(float(bus.get("confidence") or 0.0), 0.5 if len(set(candidates)) > 1 else 0.6)
        inferred_count += 1
        key = str(round(inferred_voltage, 3))
        by_voltage[key] = by_voltage.get(key, 0) + 1

    return {
        "tagged": tagged_count,
        "inferred": inferred_count,
        "unresolved": unresolved_count,
        "inferred_by_voltage_kv": dict(sorted(by_voltage.items(), key=lambda item: float(item[0]))),
    }


def _consensus_voltage(values: list[float]) -> float:
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(sorted(counts), key=lambda value: (counts[value], value))


def validate_powermodels_case(case: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    buses = case.get("bus") or {}
    branches = case.get("branch") or {}
    generators = case.get("gen") or {}
    loads = case.get("load") or {}

    if not buses:
        errors.append({"code": "no_buses", "message": "Case has no buses."})
    if not generators:
        errors.append({"code": "no_generators", "message": "Case has no active generators or equivalent imports."})
    if not branches:
        warnings.append({"code": "no_branches", "message": "Case has no branches; solver handoff will be a single-bus equivalent at best."})

    bus_ids = {int(bus["bus_i"]) for bus in buses.values() if "bus_i" in bus}
    for bus_id, bus in buses.items():
        missing_fields = []
        for field in ("index", "bus_i", "bus_type", "base_kv", "vmin", "vmax", "vm", "va"):
            if field not in bus:
                errors.append({"code": "bus_missing_field", "message": "Bus is missing a required PowerModels field.", "bus_id": bus_id, "field": field})
                missing_fields.append(field)
        if missing_fields:
            continue
        if "bus_type" in bus and int(bus["bus_type"]) not in {1, 2, 3, 4}:
            errors.append({"code": "bus_invalid_type", "message": "Bus has an invalid PowerModels bus_type.", "bus_id": bus_id})

    for branch_id, branch in branches.items():
        missing_fields = []
        for field in ("f_bus", "t_bus", "br_r", "br_x", "g_fr", "g_to", "b_fr", "b_to", "rate_a", "angmin", "angmax", "br_status"):
            if field not in branch:
                errors.append({"code": "branch_missing_field", "message": "Branch is missing a required PowerModels field.", "branch_id": branch_id, "field": field})
                missing_fields.append(field)
        if missing_fields:
            continue
        if branch["f_bus"] not in bus_ids or branch["t_bus"] not in bus_ids:
            errors.append({"code": "branch_missing_bus", "message": "Branch references an unknown bus.", "branch_id": branch_id})
        if branch["br_r"] <= 0 or branch["br_x"] <= 0:
            errors.append({"code": "branch_nonpositive_impedance", "message": "Branch has nonpositive impedance.", "branch_id": branch_id})
        if branch["rate_a"] <= 0:
            errors.append({"code": "branch_nonpositive_rating", "message": "Branch has nonpositive thermal rating.", "branch_id": branch_id})

    for load_id, load in loads.items():
        if not load.get("provenance"):
            errors.append({"code": "load_missing_provenance", "message": "Load is missing provenance metadata.", "load_id": load_id})
        missing_fields = []
        for field in ("load_bus", "pd", "qd", "status"):
            if field not in load:
                errors.append({"code": "load_missing_field", "message": "Load is missing a required PowerModels field.", "load_id": load_id, "field": field})
                missing_fields.append(field)
        if missing_fields:
            continue
        if load["load_bus"] not in bus_ids:
            errors.append({"code": "load_missing_bus", "message": "Load references an unknown bus.", "load_id": load_id})
        if load["pd"] < 0 or load["qd"] < 0:
            errors.append({"code": "load_negative_demand", "message": "Load has negative demand.", "load_id": load_id})

    for gen_id, generator in generators.items():
        missing_fields = []
        for field in ("gen_bus", "pg", "qg", "pmin", "pmax", "qmin", "qmax", "vg", "mbase", "gen_status", "model", "ncost", "cost"):
            if field not in generator:
                errors.append({"code": "gen_missing_field", "message": "Generator is missing a required PowerModels field.", "gen_id": gen_id, "field": field})
                missing_fields.append(field)
        if missing_fields:
            continue
        if generator["gen_bus"] not in bus_ids:
            errors.append({"code": "gen_missing_bus", "message": "Generator references an unknown bus.", "gen_id": gen_id})
        if generator["pmax"] <= 0 or generator["pmax"] < generator["pmin"]:
            errors.append({"code": "gen_invalid_capacity", "message": "Generator has invalid active-power limits.", "gen_id": gen_id})
        if generator["model"] != 2 or generator["ncost"] != 3 or len(generator["cost"]) != 3:
            errors.append({"code": "gen_invalid_polynomial_cost", "message": "Generator must use a quadratic polynomial cost for GridSFM export.", "gen_id": gen_id})

    total_pd = sum(load["pd"] for load in loads.values())
    total_pmax = sum(generator["pmax"] for generator in generators.values())
    if total_pd > 0 and total_pmax < total_pd * 1.05:
        errors.append(
            {
                "code": "generation_capacity_shortfall",
                "message": "Generator capacity is below demand plus a 5 percent reserve margin.",
                "total_pd_pu": round(total_pd, 6),
                "total_pmax_pu": round(total_pmax, 6),
            }
        )

    island_report = _case_island_report(buses, branches, loads, generators)
    component_metadata = _solver_component_metadata(buses, branches, loads, generators)
    quality_metrics = _case_quality_metrics(buses, branches, loads, generators)
    calibration_metrics = _calibration_validation_metrics(case, loads)
    warnings.extend(calibration_metrics["warnings"])
    errors.extend(calibration_metrics["errors"])
    warnings.extend(_demo_inference_validation_warnings(case, branches, generators))
    voltage_mismatches = _branch_voltage_mismatches(buses, branches)
    severe_voltage_mismatches = [
        mismatch
        for mismatch in voltage_mismatches
        if any(endpoint["relative_difference"] >= 0.5 for endpoint in mismatch["endpoints"])
    ]
    if severe_voltage_mismatches:
        warnings.append(
            {
                "code": "severe_branch_voltage_mismatch",
                "message": "One or more branches connect to buses with voltage classes far from the inferred branch voltage.",
                "count": len(severe_voltage_mismatches),
            }
        )
    for island in island_report["islands"]:
        if island["gen_count"] > 0 and island["reference_bus_count"] == 0:
            errors.append(
                {
                    "code": "island_missing_reference_bus",
                    "message": "A connected component with generation has no slack/reference bus.",
                    "bus_ids": island["bus_ids"],
                    "gen_count": island["gen_count"],
                }
            )
        if island["reference_bus_count"] > 1:
            errors.append(
                {
                    "code": "island_multiple_reference_buses",
                    "message": "A connected component has more than one slack/reference bus.",
                    "bus_ids": island["bus_ids"],
                    "reference_bus_count": island["reference_bus_count"],
                }
            )
        if island["load_count"] > 0 and island["gen_count"] == 0:
            errors.append(
                {
                    "code": "load_island_without_generation",
                    "message": "A connected component has load but no generator or equivalent import.",
                    "bus_ids": island["bus_ids"],
                    "load_count": island["load_count"],
                }
            )
        elif island["load_count"] == 0 and island["gen_count"] == 0:
            warnings.append(
                {
                    "code": "passive_island",
                    "message": "A connected component has neither load nor generation.",
                    "bus_ids": island["bus_ids"],
                }
            )

    status = "error" if errors else "warning" if warnings else "ok"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "bus_count": len(buses),
            "branch_count": len(branches),
            "load_count": len(loads),
            "gen_count": len(generators),
            "total_pd_mw": round(total_pd * BASE_MVA, 3),
            "total_pmax_mw": round(total_pmax * BASE_MVA, 3),
            "island_count": island_report["island_count"],
            "load_bearing_component_count": component_metadata["load_bearing_component_count"],
            "largest_component_bus_count": component_metadata["largest_component_bus_count"],
            "largest_component_bus_share": component_metadata["largest_component_bus_share"],
            "largest_component_load_mw": component_metadata["largest_component_load_mw"],
            "largest_component_load_share": component_metadata["largest_component_load_share"],
            "largest_component_pmax_mw": component_metadata["largest_component_pmax_mw"],
            "largest_component_pmax_share": component_metadata["largest_component_pmax_share"],
            "low_confidence_counts": quality_metrics["low_confidence_counts"],
            "provenance_summary": quality_metrics["provenance_summary"],
            "calibration": calibration_metrics["metrics"],
            "branch_voltage_mismatch_count": len(voltage_mismatches),
            "severe_branch_voltage_mismatch_count": len(severe_voltage_mismatches),
            "demo_inference": _demo_inference_metrics(case, branches, generators),
        },
        "islands": island_report["islands"],
        "voltage_mismatches": voltage_mismatches,
    }


def build_topology_diagnostics(case: Mapping[str, Any]) -> dict[str, Any]:
    buses = case.get("bus") or {}
    branches = case.get("branch") or {}
    validation = validate_powermodels_case(case)
    voltage_mismatches = _diagnostic_voltage_mismatches(buses, branches, validation["voltage_mismatches"])
    synthetic_branches = _diagnostic_synthetic_branches(buses, branches)
    severe_count = sum(1 for mismatch in voltage_mismatches if mismatch["severe"])
    missing_provenance = [
        item
        for item in [*synthetic_branches, *voltage_mismatches]
        if not item.get("provenance")
    ]
    summary = {
        "solver_bus_count": len(buses),
        "solver_branch_count": len(branches),
        "synthetic_branch_count": len(synthetic_branches),
        "synthetic_branch_share": round(len(synthetic_branches) / len(branches), 6) if branches else 0.0,
        "voltage_mismatch_count": len(voltage_mismatches),
        "severe_voltage_mismatch_count": severe_count,
        "missing_provenance_count": len(missing_provenance),
    }
    return {
        "summary": summary,
        "synthetic_branches": synthetic_branches,
        "voltage_mismatches": voltage_mismatches,
        "recommended_next_fixes": _recommended_next_fixes(synthetic_branches, voltage_mismatches),
        "validation_status": validation["status"],
    }


def build_asset_reconciliation(
    rows: Iterable[Any],
    topology: Mapping[str, Any],
    case: Mapping[str, Any],
) -> dict[str, Any]:
    records = [_row_to_record(row) for row in rows]
    raw_by_power = _count_by(records, "power")
    linear_assets = _reconcile_linear_assets(records, topology, case)
    generation_assets = _reconcile_generation_assets(records, topology, case)
    dropped_or_aggregated_assets = [
        asset
        for asset in [*linear_assets, *generation_assets]
        if asset["status"]
        not in {
            "retained_solver_branch",
            "retained_solver_branch_demo_policy",
            "retained_with_inferred_voltage",
            "retained_with_synthetic_endpoint",
            "retained_solver_generator",
            "retained_solver_generator_via_synthetic_connection",
            "reconstructed_preview_only",
            "preview_generation_candidate",
        }
    ]
    return {
        "summary": {
            "raw_asset_count": len(records),
            "raw_by_power": dict(sorted(raw_by_power.items())),
            "raw_linear_count": sum(1 for record in records if record.get("power") in BRANCH_POWER_VALUES),
            "raw_generation_count": sum(1 for record in records if record.get("power") in {"plant", "generator"}),
            "preview_bus_count": len(topology.get("buses") or []),
            "preview_branch_count": len(topology.get("branches") or []),
            "preview_generator_count": len(topology.get("generators") or []),
            "solver_bus_count": len(case.get("bus") or {}),
            "solver_branch_count": len(case.get("branch") or {}),
            "solver_generator_count": len(case.get("gen") or {}),
            "linear_status_counts": _count_by(linear_assets, "status"),
            "generation_status_counts": _count_by(generation_assets, "status"),
        },
        "linear_assets": linear_assets,
        "generation_assets": generation_assets,
        "dropped_or_aggregated_assets": dropped_or_aggregated_assets,
    }


def _reconcile_linear_assets(
    records: list[dict[str, Any]],
    topology: Mapping[str, Any],
    case: Mapping[str, Any],
) -> list[dict[str, Any]]:
    preview_branches = list(topology.get("branches") or [])
    preview_by_id = {str(branch.get("id")): branch for branch in preview_branches}
    merged_by_source: dict[str, Mapping[str, Any]] = {}
    for branch in preview_branches:
        for source_id in branch.get("merged_source_ids") or []:
            merged_by_source[str(source_id)] = branch

    solver_branch_by_source = {
        str(branch.get("source_id")): (str(branch_id), branch)
        for branch_id, branch in (case.get("branch") or {}).items()
        if branch.get("source_id")
    }

    assets = []
    for record in records:
        if record.get("power") not in BRANCH_POWER_VALUES:
            continue
        raw_id = f"osm:{record['osm_type']}:{record['osm_id']}"
        preview_branch = preview_by_id.get(raw_id)
        merged_branch = merged_by_source.get(raw_id)
        linked_branch = preview_branch or merged_branch
        linked_branch_id = str(linked_branch.get("id")) if linked_branch else None
        solver_branch_match = solver_branch_by_source.get(linked_branch_id or raw_id)
        solver_branch_id = solver_branch_match[0] if solver_branch_match else None
        solver_branch = solver_branch_match[1] if solver_branch_match else None
        status, reason = _linear_reconciliation_status(
            record=record,
            raw_id=raw_id,
            preview_branch=preview_branch,
            merged_branch=merged_branch,
            solver_branch_id=solver_branch_id,
            solver_branch=solver_branch,
        )
        assets.append(
            {
                "osm_type": record["osm_type"],
                "osm_id": record["osm_id"],
                "raw_id": raw_id,
                "name": record.get("name"),
                "voltage": record.get("voltage"),
                "voltage_kv": record.get("voltage_kv"),
                "power": record.get("power"),
                "operator": record.get("operator"),
                "geometry_length_km": _geometry_length_km(record.get("geometry") or []),
                "reconstructed_branch_id": linked_branch_id,
                "solver_branch_id": solver_branch_id,
                "status": status,
                "reason": reason,
            }
        )
    return assets


def _linear_reconciliation_status(
    *,
    record: Mapping[str, Any],
    raw_id: str,
    preview_branch: Mapping[str, Any] | None,
    merged_branch: Mapping[str, Any] | None,
    solver_branch_id: str | None,
    solver_branch: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if solver_branch_id is not None:
        if solver_branch and solver_branch.get("retention_policy") == "demo_full_osm":
            circuit_class = str(solver_branch.get("circuit_class") or "")
            if circuit_class in {"tap", "isolated"}:
                return "retained_with_synthetic_endpoint", "Raw line or cable is retained by demo_full_osm with synthetic endpoint handling."
            if solver_branch.get("matched_voltage_kv") is not None and not record.get("voltage_kv"):
                return "retained_with_inferred_voltage", "Raw line or cable is retained by demo_full_osm with inferred voltage parameters."
            return "retained_solver_branch_demo_policy", "Raw line or cable is retained by the demo_full_osm solver policy."
        return "retained_solver_branch", "Raw line or cable is represented by a solver-retained branch."
    if merged_branch is not None:
        return "merged_into_reconstructed_circuit", "Raw segment was merged with adjacent OSM segments into one reconstructed circuit."
    if preview_branch is not None:
        circuit_class = str(preview_branch.get("circuit_class") or "unknown")
        if circuit_class == "self_loop":
            return "still_dropped_self_loop", "Reconstructed branch connects a facility to itself and is removed before solver export."
        if circuit_class == "tap":
            return "dropped_tap", "Reconstructed branch terminates at a synthetic endpoint and is not exported as an inter-facility solver branch."
        if circuit_class == "isolated":
            return "dropped_isolated", "Reconstructed branch is isolated from retained load-bearing topology."
        if circuit_class == "inter_facility":
            return "reconstructed_preview_only", "Reconstructed inter-facility branch is visible in preview but not retained in the solver island."
        return "reconstructed_preview_only", f"Reconstructed preview branch class is {circuit_class}."
    if record.get("voltage_kv"):
        return "filtered_low_voltage", "Raw line or cable is absent from the filtered reconstructed view, commonly because of the minimum voltage threshold."
    if len(record.get("geometry") or []) < 2:
        return "still_dropped_invalid_geometry", "Raw line or cable does not have enough geometry to reconstruct endpoints."
    return "unknown", "No reconstructed branch could be linked to this raw line or cable."


def _reconcile_generation_assets(
    records: list[dict[str, Any]],
    topology: Mapping[str, Any],
    case: Mapping[str, Any],
) -> list[dict[str, Any]]:
    topology_generators = {
        str(generator.get("id")): generator
        for generator in topology.get("generators") or []
    }
    topology_bus_ids = {str(bus.get("id")) for bus in topology.get("buses") or []}
    solver_bus_source_ids = {str(bus.get("source_id")) for bus in (case.get("bus") or {}).values() if bus.get("source_id")}
    solver_gen_by_source = {
        str(generator.get("source_id")): (str(generator_id), generator)
        for generator_id, generator in (case.get("gen") or {}).items()
        if generator.get("source_id")
    }
    equivalent_gen_count = sum(
        1
        for generator in (case.get("gen") or {}).values()
        if "equivalent" in str(generator.get("resource_type") or "")
    )

    assets = []
    for record in records:
        if record.get("power") not in {"plant", "generator"}:
            continue
        generator_id = f"gen:{record['osm_type']}:{record['osm_id']}"
        topology_generator = topology_generators.get(generator_id)
        mapped_bus_id = str(topology_generator.get("bus_id")) if topology_generator else None
        solver_generator_match = solver_gen_by_source.get(generator_id)
        solver_generator_id = solver_generator_match[0] if solver_generator_match else None
        solver_generator = solver_generator_match[1] if solver_generator_match else None
        parsed_pmax_mw, capacity_tag = _generator_capacity(record.get("tags") or {})
        status, reason = _generation_reconciliation_status(
            record=record,
            topology_generator=topology_generator,
            mapped_bus_id=mapped_bus_id,
            topology_bus_ids=topology_bus_ids,
            solver_bus_source_ids=solver_bus_source_ids,
            solver_generator_id=solver_generator_id,
            solver_generator=solver_generator,
            equivalent_gen_count=equivalent_gen_count,
            min_solver_generator_mw=float((case.get("_metadata") or {}).get("min_solver_generator_mw") or DEFAULT_MIN_SOLVER_GENERATOR_MW),
        )
        assets.append(
            {
                "osm_type": record["osm_type"],
                "osm_id": record["osm_id"],
                "raw_id": f"osm:{record['osm_type']}:{record['osm_id']}",
                "generator_id": generator_id,
                "name": record.get("name"),
                "power": record.get("power"),
                "operator": record.get("operator"),
                "voltage": record.get("voltage"),
                "voltage_kv": record.get("voltage_kv"),
                "source": (record.get("tags") or {}).get("generator:source"),
                "fuel": (record.get("tags") or {}).get("generator:source"),
                "output_tag": capacity_tag,
                "output_raw": (record.get("tags") or {}).get(capacity_tag) if capacity_tag else None,
                "parsed_pmax_mw": parsed_pmax_mw,
                "mapped_bus_id": mapped_bus_id,
                "appears_in_topology_generators": topology_generator is not None,
                "appears_in_solver_gen": solver_generator_id is not None,
                "solver_generator_id": solver_generator_id,
                "status": status,
                "reason": reason,
            }
        )
    return assets


def _generation_reconciliation_status(
    *,
    record: Mapping[str, Any],
    topology_generator: Mapping[str, Any] | None,
    mapped_bus_id: str | None,
    topology_bus_ids: set[str],
    solver_bus_source_ids: set[str],
    solver_generator_id: str | None,
    solver_generator: Mapping[str, Any] | None,
    equivalent_gen_count: int,
    min_solver_generator_mw: float,
) -> tuple[str, str]:
    if solver_generator_id is not None:
        if solver_generator and solver_generator.get("connection_method") == "synthetic_connection_to_nearest_substation":
            return "retained_solver_generator_via_synthetic_connection", "Raw plant or generator is exported as a solver generator via a documented synthetic connection."
        return "retained_solver_generator", "Raw plant or generator has a capacity tag and is exported as a solver generator."
    if topology_generator is None:
        if record.get("voltage_kv"):
            return "filtered_low_voltage", "Raw generation asset is absent from the filtered reconstructed view, commonly because of the minimum voltage threshold."
        return "missing_voltage_or_bus_mapping", "Raw generation asset did not produce a reconstructed bus or generator candidate."
    if topology_generator.get("pmax_mw") is None:
        return "missing_capacity_tag", "Raw generation asset is visible as a candidate but lacks a parsable capacity tag for solver export."
    if float(topology_generator.get("pmax_mw") or 0.0) < min_solver_generator_mw:
        return "below_solver_generator_threshold", "Generator candidate has parsable capacity below the configured solver promotion threshold."
    if not mapped_bus_id or mapped_bus_id not in topology_bus_ids:
        return "missing_voltage_or_bus_mapping", "Generator candidate does not map to an available reconstructed bus."
    if mapped_bus_id not in solver_bus_source_ids:
        return "not_solver_connected", "Generator candidate is on a preview bus that is not retained in the load-bearing solver case."
    if equivalent_gen_count:
        return "aggregated_into_equivalent_capacity", "Solver uses territory-level equivalent capacity for this load-bearing island instead of this raw generator candidate."
    return "preview_generation_candidate", "Generation candidate is visible in the reconstructed layer but not exported as a solver generator."


def _diagnostic_synthetic_branches(
    buses: Mapping[str, Any],
    branches: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        _diagnostic_branch_record(
            branch_id=branch_id,
            branch=branch,
            buses=buses,
            category=_synthetic_branch_category(branch),
            recommended_action=_synthetic_branch_recommended_action(branch),
        )
        for branch_id, branch in sorted(branches.items(), key=lambda item: int(item[0]))
        if _is_synthetic_solver_branch(branch)
    ]


def _diagnostic_voltage_mismatches(
    buses: Mapping[str, Any],
    branches: Mapping[str, Any],
    mismatches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for mismatch in mismatches:
        branch_id = str(mismatch["branch_id"])
        branch = branches.get(branch_id)
        if branch is None:
            continue
        endpoint_records = []
        for endpoint in mismatch["endpoints"]:
            endpoint_field = str(endpoint["endpoint"])
            bus_number = endpoint.get("bus_i")
            bus = buses.get(str(bus_number))
            endpoint_records.append(
                {
                    **endpoint,
                    "bus_source_id": bus.get("source_id") if bus else None,
                    "bus_name": bus.get("name") if bus else None,
                    "bus_lat": bus.get("lat") if bus else None,
                    "bus_lon": bus.get("lon") if bus else None,
                    "role": "from" if endpoint_field == "f_bus" else "to",
                }
            )
        severe = any(float(endpoint["relative_difference"]) >= 0.5 for endpoint in endpoint_records)
        category = _voltage_mismatch_category(branch, endpoint_records)
        record = _diagnostic_branch_record(
            branch_id=branch_id,
            branch=branch,
            buses=buses,
            category=category,
            recommended_action=_voltage_mismatch_recommended_action(branch, endpoint_records),
        )
        record.update(
            {
                "branch_voltage_kv": mismatch.get("branch_voltage_kv"),
                "matched_voltage_kv": branch.get("matched_voltage_kv"),
                "endpoints": endpoint_records,
                "severe": severe,
                "transformer": bool(branch.get("transformer")),
                "transformer_inference": branch.get("transformer_inference"),
            }
        )
        records.append(record)
    return records


def _diagnostic_branch_record(
    *,
    branch_id: str,
    branch: Mapping[str, Any],
    buses: Mapping[str, Any],
    category: str,
    recommended_action: str,
) -> dict[str, Any]:
    from_bus = buses.get(str(branch.get("f_bus")))
    to_bus = buses.get(str(branch.get("t_bus")))
    return {
        "solver_branch_id": branch_id,
        "source_id": branch.get("source_id"),
        "provenance": branch.get("provenance"),
        "source_power": branch.get("source_power"),
        "from_bus": _diagnostic_bus_endpoint(from_bus),
        "to_bus": _diagnostic_bus_endpoint(to_bus),
        "from_bus_id": from_bus.get("source_id") if from_bus else None,
        "to_bus_id": to_bus.get("source_id") if to_bus else None,
        "from_bus_name": from_bus.get("name") if from_bus else None,
        "to_bus_name": to_bus.get("name") if to_bus else None,
        "from_base_kv": from_bus.get("base_kv") if from_bus else None,
        "to_base_kv": to_bus.get("base_kv") if to_bus else None,
        "branch_matched_voltage_kv": branch.get("matched_voltage_kv"),
        "rate_mva": branch.get("rate_a"),
        "length_km": branch.get("length_km"),
        "circuit_class": branch.get("circuit_class"),
        "category": category,
        "recommended_action": recommended_action,
    }


def _diagnostic_bus_endpoint(bus: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if bus is None:
        return None
    return {
        "bus_i": bus.get("bus_i"),
        "source_id": bus.get("source_id"),
        "name": bus.get("name"),
        "base_kv": bus.get("base_kv"),
        "lat": bus.get("lat"),
        "lon": bus.get("lon"),
        "provenance": bus.get("provenance"),
    }


def _is_synthetic_solver_branch(branch: Mapping[str, Any]) -> bool:
    provenance = str(branch.get("provenance") or "")
    source_id = str(branch.get("source_id") or "")
    return source_id.startswith("synthetic:") or "synthetic" in provenance or "public_interconnection" in provenance


def _synthetic_branch_category(branch: Mapping[str, Any]) -> str:
    provenance = str(branch.get("provenance") or "")
    source_id = str(branch.get("source_id") or "")
    if provenance == "synthetic_connection_to_nearest_substation" or source_id.startswith("synthetic:generator-connection:"):
        return "synthetic_generator_connection"
    if provenance == "synthetic_service_territory_backbone" or "service-backbone" in source_id:
        return "synthetic_service_territory_backbone"
    if provenance == "public_interconnection_capacity_equivalent":
        return "public_interconnection_capacity_equivalent"
    if source_id.startswith("synthetic:"):
        return "synthetic_endpoint_bridge"
    return "unknown_synthetic"


def _synthetic_branch_recommended_action(branch: Mapping[str, Any]) -> str:
    category = _synthetic_branch_category(branch)
    if category == "synthetic_service_territory_backbone":
        return "replace with OSM cable/line if available"
    if category == "synthetic_generator_connection":
        return "replace with traced OSM generator interconnection if available"
    if category == "public_interconnection_capacity_equivalent":
        return "keep as documented equivalent"
    if category == "synthetic_endpoint_bridge":
        return "improve endpoint snapping"
    return "review manually"


def _voltage_mismatch_category(branch: Mapping[str, Any], endpoints: list[Mapping[str, Any]]) -> str:
    if branch.get("transformer"):
        return "inferred_transformer"
    if str(branch.get("circuit_class") or "") != "inter_facility":
        return "non_interfacility_branch"
    if len(endpoints) == 1:
        return "endpoint_branch_voltage_disagreement"
    endpoint_voltages = {float(endpoint["bus_base_kv"]) for endpoint in endpoints if endpoint.get("bus_base_kv") is not None}
    if len(endpoint_voltages) == 1:
        return "branch_voltage_from_endpoint_consensus"
    return "manual_voltage_tag_review"


def _voltage_mismatch_recommended_action(branch: Mapping[str, Any], endpoints: list[Mapping[str, Any]]) -> str:
    category = _voltage_mismatch_category(branch, endpoints)
    if category == "inferred_transformer":
        return "infer transformer"
    if category == "branch_voltage_from_endpoint_consensus":
        return "correct branch voltage from endpoint consensus"
    if category == "non_interfacility_branch":
        return "drop non-interfacility branch"
    return "review OSM tags manually"


def _recommended_next_fixes(
    synthetic_branches: list[Mapping[str, Any]],
    voltage_mismatches: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for item in [*synthetic_branches, *voltage_mismatches]:
        key = (str(item.get("category") or "unknown"), str(item.get("recommended_action") or "review manually"))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"category": category, "recommended_action": action, "count": count}
        for (category, action), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][0]))
    ]


def _calibration_validation_metrics(
    case: Mapping[str, Any],
    loads: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    metadata = case.get("_metadata") or {}
    calibration = metadata.get("calibration") or {}
    total_pd_mw = sum(float(load.get("pd", 0.0)) * BASE_MVA for load in loads.values())
    class_mw = {"observed": 0.0, "inferred": 0.0, "synthetic": 0.0, "unknown": 0.0}
    for load in loads.values():
        provenance = str(load.get("provenance") or "")
        pd_mw = float(load.get("pd", 0.0)) * BASE_MVA
        if provenance.startswith("observed"):
            class_mw["observed"] += pd_mw
        elif provenance.startswith("inferred"):
            class_mw["inferred"] += pd_mw
        elif provenance.startswith("synthetic"):
            class_mw["synthetic"] += pd_mw
        else:
            class_mw["unknown"] += pd_mw

    class_share = {
        key: round(value / total_pd_mw, 6) if total_pd_mw else 0.0
        for key, value in class_mw.items()
    }
    if class_share["synthetic"] > 0.5:
        warnings.append(
            {
                "code": "synthetic_load_share_high",
                "message": "More than 50 percent of modeled load is synthetic.",
                "synthetic_load_share": class_share["synthetic"],
            }
        )
    if class_mw["synthetic"] > 0.0:
        warnings.append(
            {
                "code": "clp_inference_missing_public_total",
                "message": "Synthetic CLP fallback load is active because public territory totals were unavailable.",
            }
        )

    hk_loads = [
        load
        for load in loads.values()
        if load.get("service_territory") == "hk-electric"
        and str(load.get("provenance") or "").startswith("observed")
    ]
    modeled_hk_gwh = round(sum(float(load.get("source_energy_gwh") or 0.0) for load in hk_loads), 3)
    observed_hk_gwh = float(calibration.get("observed_hk_electric_total_gwh") or 0.0)
    territory_error_pct = _percent_error(modeled_hk_gwh, observed_hk_gwh)
    if observed_hk_gwh and territory_error_pct > 1.0:
        warnings.append(
            {
                "code": "hk_electric_observed_total_mismatch",
                "message": "Modeled HK Electric source energy differs from observed HK Electric total by more than 1 percent.",
                "error_pct": territory_error_pct,
            }
        )

    sector_metrics: dict[str, Any] = {}
    observed_sector_gwh = calibration.get("sector_gwh") or {}
    for sector, observed_gwh in observed_sector_gwh.items():
        modeled_sector_gwh = sum(
            float(load.get("source_energy_gwh") or 0.0)
            for load in hk_loads
            if load.get("sector") == sector
        )
        error_pct = _percent_error(modeled_sector_gwh, float(observed_gwh))
        sector_metrics[sector] = {
            "modeled_gwh": round(modeled_sector_gwh, 3),
            "observed_gwh": round(float(observed_gwh), 3),
            "error_pct": error_pct,
            "status": "pass" if error_pct <= 5.0 else "warn",
        }
        if error_pct > 5.0:
            warnings.append(
                {
                    "code": "hk_electric_sector_total_mismatch",
                    "message": "Modeled HK Electric sector energy differs from observed sector total by more than 5 percent.",
                    "sector": sector,
                    "error_pct": error_pct,
                }
            )

    clp_loads = [
        load
        for load in loads.values()
        if load.get("service_territory") == "clp"
        and str(load.get("provenance") or "").startswith("inferred_clp")
    ]
    clp_sector_metrics: dict[str, Any] = {}
    inferred_clp_sector_gwh = calibration.get("inferred_clp_sector_gwh") or {}
    for sector, expected_gwh in inferred_clp_sector_gwh.items():
        modeled_sector_gwh = sum(
            float(load.get("source_energy_gwh") or 0.0)
            for load in clp_loads
            if load.get("sector") == sector
        )
        error_pct = _percent_error(modeled_sector_gwh, float(expected_gwh))
        clp_sector_metrics[sector] = {
            "modeled_gwh": round(modeled_sector_gwh, 3),
            "expected_gwh": round(float(expected_gwh), 3),
            "error_pct": error_pct,
            "status": "pass" if error_pct <= 0.01 else "warn",
        }
        if error_pct > 0.01:
            warnings.append(
                {
                    "code": "clp_inferred_sector_total_mismatch",
                    "message": "Modeled CLP inferred sector energy differs from Hong Kong total minus HK Electric by more than rounding tolerance.",
                    "sector": sector,
                    "error_pct": error_pct,
                }
            )

    territory_total_validation = calibration.get("territory_total_validation") or {}
    modeled_source_energy_gwh = round(
        sum(float(load.get("source_energy_gwh") or 0.0) for load in loads.values()),
        3,
    )
    official_total_gwh = float(territory_total_validation.get("emsd_total_gwh") or 0.0)
    official_total_error_pct = _percent_error(modeled_source_energy_gwh, official_total_gwh)
    if official_total_gwh and official_total_error_pct > 3.0:
        warnings.append(
            {
                "code": "official_total_source_energy_mismatch",
                "message": "Modeled annual source energy differs from official Hong Kong total by more than 3 percent.",
                "error_pct": official_total_error_pct,
            }
        )

    notes = list(metadata.get("calibration_warnings") or [])
    if clp_loads:
        warnings.append(
            {
                "code": "clp_inferred_from_territory_total",
                "severity": "info",
                "message": "CLP demand inferred from official Hong Kong totals minus observed HK Electric demand; spatial placement remains inferred.",
            }
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "load_provenance_class_mw": {key: round(value, 3) for key, value in class_mw.items()},
            "load_provenance_class_share": class_share,
            "hk_electric_territory": {
                "modeled_gwh": modeled_hk_gwh,
                "observed_gwh": round(observed_hk_gwh, 3),
                "error_pct": territory_error_pct,
                "status": "pass" if territory_error_pct <= 1.0 else "warn",
            },
            "hk_electric_sector": sector_metrics,
            "clp_inferred_sector": clp_sector_metrics,
            "official_total_source_energy": {
                "modeled_gwh": modeled_source_energy_gwh,
                "official_gwh": round(official_total_gwh, 3),
                "error_pct": official_total_error_pct,
                "status": "pass" if official_total_error_pct <= 3.0 else "warn",
            },
            "territory_total_validation": territory_total_validation,
            "monthly_total_validation": calibration.get("monthly_total_validation"),
            "warnings": notes,
        },
    }


def _percent_error(modeled: float, observed: float) -> float:
    if observed == 0.0:
        return 0.0 if modeled == 0.0 else 100.0
    return round(abs(modeled - observed) / observed * 100.0, 6)


def _case_island_report(
    buses: Mapping[str, Any],
    branches: Mapping[str, Any],
    loads: Mapping[str, Any],
    generators: Mapping[str, Any],
) -> dict[str, Any]:
    adjacency: dict[int, set[int]] = {int(bus["bus_i"]): set() for bus in buses.values()}
    for branch in branches.values():
        f_bus = int(branch["f_bus"])
        t_bus = int(branch["t_bus"])
        if f_bus in adjacency and t_bus in adjacency:
            adjacency[f_bus].add(t_bus)
            adjacency[t_bus].add(f_bus)

    load_buses: dict[int, int] = {}
    load_pd_by_bus: dict[int, float] = {}
    for load in loads.values():
        load_buses[load["load_bus"]] = load_buses.get(load["load_bus"], 0) + 1
        load_pd_by_bus[load["load_bus"]] = load_pd_by_bus.get(load["load_bus"], 0.0) + float(load.get("pd") or 0.0) * BASE_MVA

    gen_buses: dict[int, int] = {}
    gen_pmax_by_bus: dict[int, float] = {}
    for generator in generators.values():
        gen_buses[generator["gen_bus"]] = gen_buses.get(generator["gen_bus"], 0) + 1
        gen_pmax_by_bus[generator["gen_bus"]] = gen_pmax_by_bus.get(generator["gen_bus"], 0.0) + float(generator.get("pmax") or 0.0) * BASE_MVA

    reference_buses = {
        int(bus["bus_i"])
        for bus in buses.values()
        if int(bus.get("bus_type", bus.get("type", 1))) == 3
    }

    seen: set[int] = set()
    islands = []
    for bus_id in sorted(adjacency):
        if bus_id in seen:
            continue
        stack = [bus_id]
        component: set[int] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        seen.update(component)
        islands.append(
            {
                "bus_ids": sorted(component),
                "bus_count": len(component),
                "load_count": sum(load_buses.get(bus, 0) for bus in component),
                "gen_count": sum(gen_buses.get(bus, 0) for bus in component),
                "pd_mw": round(sum(load_pd_by_bus.get(bus, 0.0) for bus in component), 3),
                "pmax_mw": round(sum(gen_pmax_by_bus.get(bus, 0.0) for bus in component), 3),
                "reference_bus_count": sum(1 for bus in component if bus in reference_buses),
            }
        )

    return {"island_count": len(islands), "islands": islands}


def _case_quality_metrics(
    buses: Mapping[str, Any],
    branches: Mapping[str, Any],
    loads: Mapping[str, Any],
    generators: Mapping[str, Any],
) -> dict[str, Any]:
    collections = {
        "bus": buses.values(),
        "branch": branches.values(),
        "load": loads.values(),
        "gen": generators.values(),
    }
    return {
        "low_confidence_counts": {
            name: sum(1 for item in items if _confidence(item) < 0.5)
            for name, items in collections.items()
        },
        "provenance_summary": {
            name: _count_by(items, "provenance")
            for name, items in collections.items()
        },
    }


def _demo_inference_metrics(
    case: Mapping[str, Any],
    branches: Mapping[str, Any],
    generators: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = case.get("_metadata") or {}
    synthetic_branch_count = sum(1 for branch in branches.values() if _is_synthetic_solver_branch(branch))
    synthetic_generator_connection_count = sum(
        1
        for generator in generators.values()
        if generator.get("connection_method") == "synthetic_connection_to_nearest_substation"
    )
    inferred_voltage_count = int((metadata.get("voltage_inference") or {}).get("inferred") or 0)
    default_capacity_generator_count = sum(
        1
        for generator in generators.values()
        if generator.get("provenance") == "osm_without_capacity_inferred_default"
    )
    return {
        "solver_include_policy": metadata.get("solver_include_policy"),
        "synthetic_branch_count": synthetic_branch_count,
        "synthetic_branch_share": round(synthetic_branch_count / len(branches), 6) if branches else 0.0,
        "synthetic_generator_connection_count": synthetic_generator_connection_count,
        "inferred_voltage_count": inferred_voltage_count,
        "default_capacity_generator_count": default_capacity_generator_count,
    }


def _demo_inference_validation_warnings(
    case: Mapping[str, Any],
    branches: Mapping[str, Any],
    generators: Mapping[str, Any],
) -> list[dict[str, Any]]:
    metrics = _demo_inference_metrics(case, branches, generators)
    if metrics["solver_include_policy"] != "demo_full_osm":
        return []
    warnings = []
    if metrics["synthetic_branch_share"] > 0.25:
        warnings.append(
            {
                "code": "demo_synthetic_branch_share_high",
                "severity": "warning",
                "message": "Demo solver case retains a high share of inferred or synthetic branches.",
                "synthetic_branch_share": metrics["synthetic_branch_share"],
                "synthetic_branch_count": metrics["synthetic_branch_count"],
            }
        )
    if metrics["synthetic_generator_connection_count"]:
        warnings.append(
            {
                "code": "generator_connected_via_synthetic_branch",
                "severity": "info",
                "message": "One or more OSM generators are connected to the solver case through documented synthetic branches.",
                "count": metrics["synthetic_generator_connection_count"],
            }
        )
    if metrics["inferred_voltage_count"]:
        warnings.append(
            {
                "code": "unknown_voltage_inferred",
                "severity": "info",
                "message": "One or more buses or branches use inferred voltage in the solver case.",
                "count": metrics["inferred_voltage_count"],
            }
        )
    if metrics["default_capacity_generator_count"]:
        warnings.append(
            {
                "code": "generator_default_capacity",
                "severity": "info",
                "message": "One or more promoted generators use default inferred capacity rather than an OSM capacity tag.",
                "count": metrics["default_capacity_generator_count"],
            }
        )
    return warnings


def _branch_voltage_mismatches(
    buses: Mapping[str, Any],
    branches: Mapping[str, Any],
    *,
    tolerance: float = 0.15,
) -> list[dict[str, Any]]:
    bus_by_i = {
        int(bus["bus_i"]): bus
        for bus in buses.values()
        if "bus_i" in bus
    }
    mismatches = []
    for branch_id, branch in branches.items():
        if branch.get("transformer"):
            continue
        branch_voltage = branch.get("matched_voltage_kv")
        if branch_voltage is None:
            continue
        mismatched_endpoints = []
        for endpoint_field in ("f_bus", "t_bus"):
            if endpoint_field not in branch:
                continue
            bus = bus_by_i.get(int(branch[endpoint_field]))
            if not bus:
                continue
            bus_voltage = bus.get("base_kv")
            if bus_voltage is None:
                continue
            if abs(float(bus_voltage) - float(branch_voltage)) / float(branch_voltage) > tolerance:
                mismatched_endpoints.append(
                    {
                        "endpoint": endpoint_field,
                        "bus_i": bus["bus_i"],
                        "bus_base_kv": bus_voltage,
                        "relative_difference": round(abs(float(bus_voltage) - float(branch_voltage)) / float(branch_voltage), 6),
                    }
                )
        if mismatched_endpoints:
            mismatches.append(
                {
                    "branch_id": branch_id,
                    "source_id": branch.get("source_id"),
                    "branch_voltage_kv": branch_voltage,
                    "endpoints": mismatched_endpoints,
                }
            )
    return mismatches


def _confidence(item: Mapping[str, Any]) -> float:
    value = item.get("confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _powermodels_bus_type(
    bus_id: str,
    reference_bus_ids: set[str],
    gen_bus_ids: set[str],
    load_bus_ids: set[str],
) -> int:
    if bus_id in reference_bus_ids:
        return 3
    if bus_id in gen_bus_ids:
        return 2
    if bus_id in load_bus_ids:
        return 1
    return 1


def _reference_bus_ids_by_island(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
    gen_bus_ids: set[str],
) -> set[str]:
    bus_by_id = {bus["id"]: bus for bus in buses}
    adjacency: dict[str, set[str]] = {bus["id"]: set() for bus in buses}
    for branch in branches:
        from_bus_id = branch.get("from_bus_id")
        to_bus_id = branch.get("to_bus_id")
        if from_bus_id in adjacency and to_bus_id in adjacency:
            adjacency[str(from_bus_id)].add(str(to_bus_id))
            adjacency[str(to_bus_id)].add(str(from_bus_id))

    reference_bus_ids: set[str] = set()
    seen: set[str] = set()
    for bus_id in sorted(adjacency):
        if bus_id in seen:
            continue
        stack = [bus_id]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        seen.update(component)

        candidates = [bus_by_id[candidate] for candidate in component if candidate in gen_bus_ids]
        if not candidates:
            candidates = [bus_by_id[candidate] for candidate in component]
        if candidates:
            reference_bus_ids.add(max(candidates, key=lambda bus: bus.get("base_kv") or 0.0)["id"])
    return reference_bus_ids


def _powermodels_branch(
    index: int,
    branch: Mapping[str, Any],
    bus_id_map: Mapping[str, str],
    bus_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    voltage_kv = branch.get("voltage_kv") or _branch_endpoint_voltage(branch, bus_by_id) or 132.0
    length_km = branch.get("length_km") or 1.0
    defaults = dict(branch.get("parameter_defaults") or {})
    if defaults.get("rate_mva") is None and voltage_kv is not None:
        defaults.update(_branch_defaults(str(branch.get("power") or "line"), float(voltage_kv)))
    transformer_info = _inferred_transformer_info(branch, bus_by_id)
    if transformer_info is None:
        r_ohm = (defaults.get("r_ohm_per_km") or 0.08) * length_km
        x_ohm = (defaults.get("x_ohm_per_km") or 0.42) * length_km
        z_base_ohm = (voltage_kv * voltage_kv) / BASE_MVA
        br_r = round(max(r_ohm / z_base_ohm, 0.00001), 8)
        br_x = round(max(x_ohm / z_base_ohm, 0.00001), 8)
        charging_pu = _branch_charging_pu(defaults, length_km, z_base_ohm)
        transformer = False
        parameter_source = branch.get("provenance")
        transformer_parameter_table = None
        tap = 1.0
    else:
        transformer_defaults = _transformer_defaults(transformer_info["high_kv"], transformer_info["low_kv"])
        br_r = transformer_defaults["br_r"]
        br_x = transformer_defaults["br_x"]
        charging_pu = 0.0
        transformer = True
        parameter_source = transformer_defaults["parameter_source"]
        transformer_parameter_table = transformer_defaults["parameter_table"]
        tap = 1.0

    return {
        "index": index,
        "f_bus": int(bus_id_map[str(branch["from_bus_id"])]),
        "t_bus": int(bus_id_map[str(branch["to_bus_id"])]),
        "br_r": br_r,
        "br_x": br_x,
        "g_fr": 0.0,
        "g_to": 0.0,
        "b_fr": charging_pu,
        "b_to": charging_pu,
        "rate_a": defaults.get("rate_mva") or 100.0,
        "rate_b": defaults.get("rate_mva") or 100.0,
        "rate_c": defaults.get("rate_mva") or 100.0,
        "tap": tap,
        "shift": 0.0,
        "br_status": 1,
        "angmin": -0.523599,
        "angmax": 0.523599,
        "transformer": transformer,
        "source_id": branch["id"],
        "source_power": branch.get("power"),
        "circuit_class": branch.get("circuit_class"),
        "circuit_count": branch.get("circuit_count"),
        "merged_segment_count": branch.get("merged_segment_count"),
        "provenance": branch.get("provenance"),
        "retention_policy": branch.get("retention_policy"),
        "solver_retention_reason": branch.get("solver_retention_reason"),
        "confidence": branch.get("confidence"),
        "parameter_source": parameter_source,
        "parameter_table": transformer_parameter_table if transformer else defaults.get("parameter_table"),
        "matched_voltage_kv": defaults.get("matched_voltage_kv"),
        "b_us_per_km": defaults.get("b_us_per_km"),
        "length_km": length_km,
        **({"transformer_inference": transformer_info} if transformer_info is not None else {}),
}


def _branch_endpoint_voltage(
    branch: Mapping[str, Any],
    bus_by_id: Mapping[str, Mapping[str, Any]],
) -> float | None:
    voltages = []
    for endpoint in (branch.get("from_bus_id"), branch.get("to_bus_id")):
        bus = bus_by_id.get(str(endpoint))
        base_kv = bus.get("base_kv") if bus is not None else None
        if base_kv is not None:
            voltages.append(float(base_kv))
    return max(voltages) if voltages else None


def _inferred_transformer_info(
    branch: Mapping[str, Any],
    bus_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    from_bus = bus_by_id.get(str(branch.get("from_bus_id")))
    to_bus = bus_by_id.get(str(branch.get("to_bus_id")))
    if from_bus is None or to_bus is None:
        return None
    if branch.get("power") == "intertie" or branch.get("provenance") == "public_interconnection_capacity_equivalent":
        return None
    from_kv = from_bus.get("base_kv")
    to_kv = to_bus.get("base_kv")
    branch_kv = branch.get("voltage_kv")
    if from_kv is None or to_kv is None:
        return None
    from_kv = float(from_kv)
    to_kv = float(to_kv)
    if min(from_kv, to_kv) <= 0:
        return None

    endpoint_ratio = max(from_kv, to_kv) / min(from_kv, to_kv)
    if branch_kv is None:
        if endpoint_ratio < 1.5:
            return None
        return {
            "method": "missing_branch_voltage_endpoint_pair_conversion",
            "from_bus_base_kv": from_kv,
            "to_bus_base_kv": to_kv,
            "branch_voltage_kv": max(from_kv, to_kv),
            "high_kv": max(from_kv, to_kv),
            "low_kv": min(from_kv, to_kv),
            "confidence": 0.5,
        }

    branch_kv = float(branch_kv)
    if branch_kv <= 0:
        return None
    from_branch_delta = abs(from_kv - branch_kv) / branch_kv
    to_branch_delta = abs(to_kv - branch_kv) / branch_kv
    severe_branch_mismatch = max(from_branch_delta, to_branch_delta) >= 0.5
    if endpoint_ratio < 1.5 or not severe_branch_mismatch:
        return None

    return {
        "method": "clear_voltage_mismatch_branch_conversion",
        "from_bus_base_kv": from_kv,
        "to_bus_base_kv": to_kv,
        "branch_voltage_kv": branch_kv,
        "high_kv": max(from_kv, to_kv),
        "low_kv": min(from_kv, to_kv),
        "confidence": 0.55,
    }


def _transformer_defaults(high_kv: float, low_kv: float) -> dict[str, Any]:
    ratio = high_kv / low_kv if low_kv else 1.0
    table_name = "autotransformer" if ratio < 3.0 else "two_winding"
    defaults = TRANSFORMER_DEFAULTS[table_name]
    return {
        "br_r": defaults["br_r"],
        "br_x": defaults["br_x"],
        "parameter_source": "inferred_transformer_voltage_pair_default",
        "parameter_table": f"transformer_{table_name}_defaults",
    }


def _is_synthetic_branch(branch: Mapping[str, Any]) -> bool:
    provenance = str(branch.get("provenance") or "")
    return str(branch.get("id") or "").startswith("synthetic:") or "synthetic" in provenance or "public_interconnection" in provenance


def _branch_charging_pu(defaults: Mapping[str, Any], length_km: float, z_base_ohm: float) -> float:
    b_us_per_km = defaults.get("b_us_per_km")
    if b_us_per_km is None:
        return 0.0
    total_b_siemens = float(b_us_per_km) * 1e-6 * length_km
    return round(max(total_b_siemens * z_base_ohm / 2.0, 0.0), 8)


def _validate_derate(derate: float) -> None:
    if derate <= 0 or derate > 1:
        raise ValueError("Derate factor must be greater than 0 and less than or equal to 1.")


def _validate_min_voltage(min_voltage_kv: float | None) -> None:
    if min_voltage_kv is not None and min_voltage_kv <= 0:
        raise ValueError("Minimum voltage must be greater than 0 kV.")


def _validate_solver_include_policy(solver_include_policy: str) -> None:
    if solver_include_policy not in SOLVER_INCLUDE_POLICIES:
        known = ", ".join(sorted(SOLVER_INCLUDE_POLICIES))
        raise ValueError(f"Unknown solver include policy '{solver_include_policy}'. Known policies: {known}")


def _validate_min_solver_generator_mw(min_solver_generator_mw: float) -> None:
    if min_solver_generator_mw < 0:
        raise ValueError("Minimum solver generator MW must be nonnegative.")


def _below_min_voltage(voltage_kv: float | None, min_voltage_kv: float | None) -> bool:
    return voltage_kv is not None and min_voltage_kv is not None and voltage_kv < min_voltage_kv


def _hk_intertie_branches(
    buses: list[dict[str, Any]],
    *,
    derate: float,
) -> list[dict[str, Any]]:
    clp_bus = _best_intertie_bus(buses, "clp")
    hke_bus = _best_intertie_bus(buses, "hk-electric")
    if clp_bus is None or hke_bus is None:
        return []

    voltage_kv = min(
        clp_bus.get("base_kv") or 132.0,
        hke_bus.get("base_kv") or 132.0,
    )
    length_km = None
    if clp_bus.get("lat") is not None and clp_bus.get("lon") is not None and hke_bus.get("lat") is not None and hke_bus.get("lon") is not None:
        length_km = _haversine_km(
            (clp_bus["lat"], clp_bus["lon"]),
            (hke_bus["lat"], hke_bus["lon"]),
        )

    return [
        {
            "id": "synthetic:intertie:clp-hk-electric",
            "source": {"kind": "public_hk_cross_harbour_interconnection"},
            "name": "CLP-HK Electric emergency interconnection",
            "power": "intertie",
            "from_bus_id": clp_bus["id"],
            "to_bus_id": hke_bus["id"],
            "voltage_kv": voltage_kv,
            "voltage_band": voltage_band(voltage_kv),
            "length_km": length_km,
            "location": "submarine_or_underground_equivalent",
            "circuits": None,
            "cables": None,
            "circuit_candidates": [{"voltage_kv": voltage_kv, "circuit_count": 1, "count_source": "public_intertie"}],
            "circuit_count": 1,
            "circuit_count_source": "public_intertie",
            "circuit_class": "inter_facility",
            "parameter_defaults": {
                "r_ohm_per_km": 0.055,
                "x_ohm_per_km": 0.16,
                "b_us_per_km": 18.0,
                "rate_mva": round(HK_INTERTIE_RATE_MVA * derate, 3),
                "matched_voltage_kv": voltage_kv,
                "parameter_table": "underground_cable_defaults",
                "parameter_source": "lookup_table",
            },
            "endpoint_quality": [
                {"snap": "synthetic_public_intertie", "bus_id": clp_bus["id"]},
                {"snap": "synthetic_public_intertie", "bus_id": hke_bus["id"]},
            ],
            "provenance": "public_interconnection_capacity_equivalent",
            "derate_factor": derate,
            "nominal_rate_mva": HK_INTERTIE_RATE_MVA,
            "confidence": 0.5,
        }
    ]


def _synthetic_service_territory_backbone(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
    loads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    load_totals_by_bus: dict[str, float] = {}
    territory_by_bus: dict[str, str] = {}
    for load in loads:
        bus_id = load["bus_id"]
        load_totals_by_bus[bus_id] = load_totals_by_bus.get(bus_id, 0.0) + float(load["pd_mw"])
        territory_by_bus[bus_id] = load["service_territory"]

    if not load_totals_by_bus:
        return []

    bus_by_id = {bus["id"]: bus for bus in buses}
    components = _preview_components(buses, branches)
    component_by_bus = {
        bus_id: index
        for index, component in enumerate(components)
        for bus_id in component
    }
    load_components_by_territory: dict[str, dict[int, float]] = {}
    for bus_id, total_mw in load_totals_by_bus.items():
        territory = territory_by_bus.get(bus_id)
        component_index = component_by_bus.get(bus_id)
        if territory is None or component_index is None:
            continue
        component_loads = load_components_by_territory.setdefault(territory, {})
        component_loads[component_index] = component_loads.get(component_index, 0.0) + total_mw

    synthetic_branches = []
    for territory, component_loads in sorted(load_components_by_territory.items()):
        if len(component_loads) < 2:
            continue
        hub_component_index = max(
            sorted(component_loads),
            key=lambda index: (component_loads[index], _component_max_voltage(components[index], bus_by_id)),
        )
        hub_bus = _best_backbone_bus(components[hub_component_index], bus_by_id, territory=territory)
        if hub_bus is None:
            continue

        for component_index in sorted(component_loads):
            if component_index == hub_component_index:
                continue
            target_bus = _best_backbone_bus(
                components[component_index],
                bus_by_id,
                territory=territory,
                preferred_voltage_kv=hub_bus.get("base_kv"),
            )
            if target_bus is None:
                continue
            voltage_kv = _backbone_voltage_kv(hub_bus, target_bus)
            length_km = _branch_length_between_buses(hub_bus, target_bus)
            defaults = _branch_defaults("cable", voltage_kv)
            if defaults.get("rate_mva") is not None:
                defaults["rate_mva"] = max(float(defaults["rate_mva"]), component_loads[component_index] * 1.25)
            synthetic_branches.append(
                {
                    "id": f"synthetic:service-backbone:{territory}:{len(synthetic_branches) + 1}",
                    "source": {
                        "kind": "synthetic_service_territory_backbone",
                        "territory": territory,
                        "hub_component_index": hub_component_index,
                        "target_component_index": component_index,
                    },
                    "name": f"{territory} synthetic service-territory backbone",
                    "power": "cable",
                    "from_bus_id": hub_bus["id"],
                    "to_bus_id": target_bus["id"],
                    "voltage_kv": voltage_kv,
                    "voltage_band": voltage_band(voltage_kv),
                    "length_km": length_km,
                    "location": "underground_equivalent",
                    "circuits": None,
                    "cables": None,
                    "circuit_candidates": [{"voltage_kv": voltage_kv, "circuit_count": 1, "count_source": "synthetic_backbone"}],
                    "circuit_count": 1,
                    "circuit_count_source": "synthetic_backbone",
                    "circuit_class": "inter_facility",
                    "parameter_defaults": defaults,
                    "endpoint_quality": [
                        {"snap": "synthetic_backbone_hub", "bus_id": hub_bus["id"]},
                        {"snap": "synthetic_backbone_target", "bus_id": target_bus["id"]},
                    ],
                    "provenance": "synthetic_service_territory_backbone",
                    "service_territory": territory,
                    "connected_load_mw": round(component_loads[component_index], 3),
                    "confidence": 0.3,
                }
            )

    return synthetic_branches


def _component_max_voltage(component: set[str], bus_by_id: Mapping[str, Mapping[str, Any]]) -> float:
    return max((float(bus_by_id[bus_id].get("base_kv") or 0.0) for bus_id in component if bus_id in bus_by_id), default=0.0)


def _best_backbone_bus(
    component: set[str],
    bus_by_id: Mapping[str, Mapping[str, Any]],
    *,
    territory: str,
    preferred_voltage_kv: float | None = None,
) -> dict[str, Any] | None:
    candidates = [bus_by_id[bus_id] for bus_id in component if bus_id in bus_by_id]
    if not candidates:
        return None
    territory_candidates = [bus for bus in candidates if bus.get("service_territory") == territory]
    if territory_candidates:
        candidates = territory_candidates

    def score(bus: Mapping[str, Any]) -> tuple[float, float, float]:
        voltage = float(bus.get("base_kv") or 0.0)
        if preferred_voltage_kv is None or voltage <= 0:
            voltage_match = 0.0
        else:
            voltage_match = -abs(voltage - float(preferred_voltage_kv))
        has_coordinates = 1.0 if bus.get("lat") is not None and bus.get("lon") is not None else 0.0
        return (voltage_match, voltage, has_coordinates)

    return dict(max(candidates, key=score))


def _backbone_voltage_kv(from_bus: Mapping[str, Any], to_bus: Mapping[str, Any]) -> float:
    from_kv = float(from_bus.get("base_kv") or 132.0)
    to_kv = float(to_bus.get("base_kv") or from_kv)
    if from_kv == to_kv:
        return from_kv
    return min(from_kv, to_kv)


def _branch_length_between_buses(from_bus: Mapping[str, Any], to_bus: Mapping[str, Any]) -> float:
    if from_bus.get("lat") is None or from_bus.get("lon") is None or to_bus.get("lat") is None or to_bus.get("lon") is None:
        return 1.0
    return max(
        _haversine_km(
            (float(from_bus["lat"]), float(from_bus["lon"])),
            (float(to_bus["lat"]), float(to_bus["lon"])),
        ),
        0.1,
    )


def _best_intertie_bus(
    buses: list[dict[str, Any]],
    territory: str,
) -> dict[str, Any] | None:
    candidates = [
        bus
        for bus in buses
        if bus.get("service_territory") == territory
        and bus.get("voltage_band") in {"extra_high_voltage", "high_voltage"}
    ]
    if not candidates:
        candidates = [
            bus
            for bus in buses
            if bus.get("service_territory") == territory
            and bus.get("voltage_band") == "subtransmission"
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda bus: bus.get("base_kv") or 0.0)


def _tagged_generators(
    generators: Iterable[Mapping[str, Any]],
    *,
    min_solver_generator_mw: float,
) -> list[dict[str, Any]]:
    tagged = []
    for generator in generators:
        pmax_mw = generator.get("pmax_mw")
        if pmax_mw is None:
            continue
        if float(pmax_mw) < min_solver_generator_mw:
            continue
        fuel_defaults = GENERATOR_FUEL_DEFAULTS[_normal_generator_source(generator.get("source"))]
        tagged.append(
            {
                "id": generator["id"],
                "source_osm_type": generator.get("source_osm_type"),
                "source_osm_id": generator.get("source_osm_id"),
                "bus_id": generator["bus_id"],
                "name": generator.get("name"),
                "operator": generator.get("operator"),
                "service_territory": None,
                "pmax_mw": float(pmax_mw),
                "energy_source": _normal_generator_source(generator.get("source")),
                "resource_type": "local_osm_generator",
                "cost_class": fuel_defaults["cost_class"],
                "cost": list(fuel_defaults["cost"]),
                "pmin_fraction": fuel_defaults["pmin_fraction"],
                "power_factor": fuel_defaults["power_factor"],
                "provenance": generator.get("provenance"),
                "provenance_chain": generator.get("provenance_chain"),
                "confidence": generator.get("confidence"),
                "capacity_tag": generator.get("capacity_tag"),
                "capacity_raw": generator.get("capacity_raw"),
                "connection_method": "preview_bus",
            }
        )
    return tagged


def _generator_cost(source: Any) -> list[float]:
    return list(GENERATOR_FUEL_DEFAULTS[_normal_generator_source(source)]["cost"])


def _normal_generator_source(source: Any) -> str:
    source_text = str(source or "").lower()
    for known in ("coal", "gas", "nuclear", "solar", "wind", "waste"):
        if known in source_text:
            return known
    return "unknown"


def _generator_cost_class(source: Any) -> str:
    return str(GENERATOR_FUEL_DEFAULTS[_normal_generator_source(source)]["cost_class"])


def _equivalent_generator_cost_class(territory: str) -> str:
    return str(_equivalent_generator_defaults(territory)["cost_class"])


def _equivalent_generator_defaults(territory: str) -> Mapping[str, Any]:
    return EQUIVALENT_GENERATOR_DEFAULTS.get(territory, EQUIVALENT_GENERATOR_DEFAULTS["default"])


def _equivalent_generators(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
    loads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    load_by_bus_id: dict[str, list[dict[str, Any]]] = {}
    for load in loads:
        load_by_bus_id.setdefault(load["bus_id"], []).append(load)

    components = _preview_components(buses, branches)
    generators = []
    for index, component in enumerate(components, start=1):
        component_loads = [
            load
            for bus_id in component
            for load in load_by_bus_id.get(bus_id, [])
        ]
        if not component_loads:
            continue

        peak_equivalent_pd_mw = sum(
            load.get("peak_pd_mw", load["pd_mw"] / (load.get("load_factor") or 1.0))
            for load in component_loads
        )
        territory = _dominant_load_territory(component_loads)
        component_buses = [bus for bus in buses if bus["id"] in component]
        bus = _best_generator_bus(component_buses, territory)
        if bus is None:
            continue
        pmax_mw = max(peak_equivalent_pd_mw * 1.25, 100.0)
        defaults = _equivalent_generator_defaults(territory)
        generators.append(
            {
                "id": f"equivalent_gen:{territory}:island:{index}",
                "bus_id": bus["id"],
                "service_territory": territory,
                "pmax_mw": pmax_mw,
                "energy_source": "equivalent_import_or_local_supply",
                "resource_type": "territory_capacity_equivalent",
                "cost_class": defaults["cost_class"],
                "cost": list(defaults["cost"]),
                "pmin_fraction": defaults["pmin_fraction"],
                "power_factor": defaults["power_factor"],
                "provenance": "public_peak_demand_capacity_equivalent",
                "confidence": 0.35,
            }
        )

    if not generators and buses:
        bus = max(buses, key=lambda candidate: candidate.get("base_kv") or 0.0)
        defaults = EQUIVALENT_GENERATOR_DEFAULTS["default"]
        generators.append(
            {
                "id": "equivalent_gen:unassigned",
                "bus_id": bus["id"],
                "service_territory": "unassigned",
                "pmax_mw": 100.0,
                "energy_source": "fallback_equivalent",
                "resource_type": "fallback_capacity_equivalent",
                "cost_class": defaults["cost_class"],
                "cost": list(defaults["cost"]),
                "pmin_fraction": defaults["pmin_fraction"],
                "power_factor": defaults["power_factor"],
                "provenance": "fallback_capacity_equivalent",
                "confidence": 0.2,
            }
        )
    return generators


def _preview_components(
    buses: list[dict[str, Any]],
    branches: list[Mapping[str, Any]],
) -> list[set[str]]:
    adjacency: dict[str, set[str]] = {bus["id"]: set() for bus in buses}
    for branch in branches:
        from_bus_id = branch.get("from_bus_id")
        to_bus_id = branch.get("to_bus_id")
        if from_bus_id in adjacency and to_bus_id in adjacency:
            adjacency[str(from_bus_id)].add(str(to_bus_id))
            adjacency[str(to_bus_id)].add(str(from_bus_id))

    components = []
    seen: set[str] = set()
    for bus_id in sorted(adjacency):
        if bus_id in seen:
            continue
        stack = [bus_id]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        seen.update(component)
        components.append(component)
    return components


def _dominant_load_territory(loads: list[dict[str, Any]]) -> str:
    totals: dict[str, float] = {}
    for load in loads:
        territory = load["service_territory"]
        totals[territory] = totals.get(territory, 0.0) + load["pd_mw"]
    return max(sorted(totals), key=lambda territory: totals[territory])


def _count_by(items: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _best_generator_bus(
    buses: list[dict[str, Any]],
    territory: str,
) -> dict[str, Any] | None:
    candidates = [
        bus
        for bus in buses
        if bus.get("service_territory") == territory
        and bus.get("voltage_band") in {"extra_high_voltage", "high_voltage", "subtransmission"}
    ]
    if not candidates:
        candidates = [
            bus
            for bus in buses
            if bus.get("voltage_band") in {"extra_high_voltage", "high_voltage", "subtransmission"}
        ]
    if not candidates:
        candidates = buses
    if not candidates:
        return None
    return max(candidates, key=lambda bus: bus.get("base_kv") or 0.0)


def _load_calibration_bundle() -> CalibrationBundle | None:
    try:
        return load_calibration_bundle(RAW_DATA_DIR)
    except (FileNotFoundError, ValueError):
        return None


def _demand_snapshot(demand_snapshot: str, calibration: CalibrationBundle | None = None) -> dict[str, Any]:
    try:
        snapshot = dict(DEMAND_SNAPSHOTS[demand_snapshot])
    except KeyError as exc:
        known = ", ".join(sorted(DEMAND_SNAPSHOTS))
        raise ValueError(f"Unknown demand snapshot '{demand_snapshot}'. Known snapshots: {known}") from exc
    if calibration is not None:
        hke_peak = calibration.snapshot_total_mw.get("peak_16h") or 0.0
        clp_peak = calibration.clp_snapshot_total_mw.get("peak_16h") or 0.0
        hke_snapshot = calibration.snapshot_total_mw.get(demand_snapshot) or 0.0
        clp_snapshot = calibration.clp_snapshot_total_mw.get(demand_snapshot) or 0.0
        peak_total = hke_peak + clp_peak
        snapshot_total = hke_snapshot + clp_snapshot
        snapshot["hk_electric_observed_mw"] = hke_snapshot
        snapshot["clp_inferred_mw"] = clp_snapshot
        snapshot["official_total_modeled_mw"] = snapshot_total
        snapshot["load_factor"] = round(snapshot_total / peak_total, 6) if peak_total else snapshot["load_factor"]
    return snapshot


def _allocate_loads(
    buses: list[dict[str, Any]],
    *,
    demand_snapshot: str,
    calibration: CalibrationBundle | None = None,
    consumer_proxies: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    snapshot = _demand_snapshot(demand_snapshot, calibration)
    proxies = list(consumer_proxies or [])
    proxy_assignments = _prepare_proxy_assignment_buckets(buses, proxies)
    loads = _allocate_hk_electric_observed_loads(
        buses,
        demand_snapshot=demand_snapshot,
        calibration=calibration,
        consumer_proxies=proxies,
        proxy_assignments=proxy_assignments,
    )
    if calibration is not None and calibration.clp_inference_method:
        loads.extend(
            _allocate_inferred_clp_loads(
                buses,
                demand_snapshot=demand_snapshot,
                calibration=calibration,
                consumer_proxies=proxies,
                proxy_assignments=proxy_assignments,
            )
        )
    else:
        loads.extend(_allocate_synthetic_clp_loads(buses, demand_snapshot=demand_snapshot))
    if loads:
        return loads
    load_factor = snapshot["load_factor"]
    fallback_peak_mw = SYNTHETIC_CLP_PEAK_DEMAND_MW
    for territory, peak_mw in {"clp": fallback_peak_mw}.items():
        eligible = [
            bus
            for bus in buses
            if bus.get("service_territory") == territory
            and bus.get("power") in {"substation", "sub_station"}
            and bus.get("voltage_band") in {"extra_high_voltage", "high_voltage", "subtransmission"}
        ]
        if not eligible:
            fallback = _fallback_load_bus(buses, territory)
            eligible = [fallback] if fallback is not None else []
        if not eligible:
            continue
        weights = {bus["id"]: _load_allocation_weight(bus) for bus in eligible}
        total_weight = sum(weights.values())
        for bus in eligible:
            weight = weights[bus["id"]]
            pd_mw = peak_mw * load_factor * weight / total_weight
            loads.append(
                {
                    "id": f"load:{territory}:{bus['id']}",
                    "bus_id": bus["id"],
                    "service_territory": territory,
                    "pd_mw": round(pd_mw, 3),
                    "qd_mvar": round(_reactive_mvar(pd_mw), 3),
                    "snapshot": demand_snapshot,
                    "provenance": "synthetic_missing_clp_data",
                    "allocation_method": "voltage_weighted_substation_split",
                    "load_factor": load_factor,
                    "peak_pd_mw": round(peak_mw * weight / total_weight, 3),
                    "allocation_weight": round(weight, 6),
                    "confidence": 0.2,
                }
            )
    return loads


def _proxy_allocated_sector_loads(
    buses: list[dict[str, Any]],
    proxies: list[Mapping[str, Any]],
    *,
    territory: str,
    sector: str,
    sector_gwh: float,
    sector_snapshot_mw: float,
    sector_peak_mw: float,
    demand_snapshot: str,
    provenance: str,
    source_file: str | None = None,
    source_files: list[str] | None = None,
    source_year: int | None = None,
    source_period: str | None = None,
    source_periods: list[str] | None = None,
    inference_method: str | None = None,
    confidence: float = 0.65,
    proxy_assignments: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    eligible = _eligible_load_buses(buses, territory)
    if not eligible:
        fallback = _fallback_load_bus(buses, territory)
        eligible = [fallback] if fallback is not None else []
    if not eligible:
        return []
    if proxy_assignments is None:
        proxy_assignments = _prepare_proxy_assignment_buckets(buses, proxies, default_confidence=confidence)

    assignments = {
        bus_id: bucket
        for bucket_key, bucket in proxy_assignments.items()
        for bucket_territory, bucket_sector, bus_id in [bucket_key]
        if bucket_territory == territory and bucket_sector == sector
    }
    if not assignments:
        return []
    total_weight = sum(bucket["proxy_total_weight"] for bucket in assignments.values())
    if total_weight <= 0.0:
        return []

    loads = []
    for bus_id, bucket in sorted(assignments.items()):
        share = bucket["proxy_total_weight"] / total_weight
        pd_mw = sector_snapshot_mw * share
        peak_pd_mw = sector_peak_mw * share
        source_energy_gwh = sector_gwh * share
        distances = sorted(bucket["distances"])
        median_distance = distances[len(distances) // 2] if distances else None
        avg_distance = bucket["weighted_distance_km"] / bucket["proxy_total_weight"]
        loads.append(
            {
                "id": f"load:{territory}:{sector}:proxy:{bus_id}",
                "bus_id": bus_id,
                "service_territory": territory,
                "sector": sector,
                "pd_mw": round(pd_mw, 3),
                "qd_mvar": round(_reactive_mvar(pd_mw), 3),
                "snapshot": demand_snapshot,
                "provenance": provenance,
                "allocation_method": provenance,
                "allocation_rule": provenance,
                "allocation_weight": round(share, 6),
                "load_factor": round(pd_mw / peak_pd_mw, 6) if peak_pd_mw else None,
                "peak_pd_mw": round(peak_pd_mw, 3),
                "source_file": source_file,
                "source_files": source_files,
                "source_year": source_year,
                "source_period": source_period,
                "source_periods": source_periods,
                "source_energy_gwh": round(source_energy_gwh, 3),
                "inference_method": inference_method,
                "geometry_provenance": "osm_consumer_proxy",
                "proxy_count": bucket["proxy_count"],
                "proxy_total_weight": round(bucket["proxy_total_weight"], 3),
                "proxy_assignment_distance_avg_km": round(avg_distance, 3),
                "proxy_assignment_distance_median_km": round(median_distance, 3) if median_distance is not None else None,
                "confidence": round(bucket["confidence_weight"] / bucket["proxy_total_weight"], 3),
            }
        )
    return loads


def _prepare_proxy_assignment_buckets(
    buses: list[dict[str, Any]],
    proxies: list[Mapping[str, Any]],
    *,
    default_confidence: float = 0.65,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    eligible_by_territory: dict[str, list[dict[str, Any]]] = {}
    for territory in ("clp", "hk-electric"):
        eligible = _eligible_load_buses(buses, territory)
        if not eligible:
            fallback = _fallback_load_bus(buses, territory)
            eligible = [fallback] if fallback is not None else []
        eligible_by_territory[territory] = [
            bus
            for bus in eligible
            if bus is not None and bus.get("lat") is not None and bus.get("lon") is not None
        ]

    candidates = [
        (territory, bus)
        for territory, eligible in eligible_by_territory.items()
        for bus in eligible
    ]
    if not candidates:
        return {}

    assignments: dict[tuple[str, str, str], dict[str, Any]] = {}
    for proxy in proxies:
        sector = proxy.get("sector")
        if not sector or proxy.get("lat") is None or proxy.get("lon") is None:
            continue
        weight = float(proxy.get("weight") or 0.0)
        if weight <= 0.0:
            continue
        point = (float(proxy["lat"]), float(proxy["lon"]))
        territory, bus, distance_km = min(
            (
                (
                    territory,
                    bus,
                    _haversine_km(point, (float(bus["lat"]), float(bus["lon"]))),
                )
                for territory, bus in candidates
            ),
            key=lambda item: (item[2], -_load_allocation_weight(item[1])),
        )
        bucket = assignments.setdefault(
            (territory, str(sector), bus["id"]),
            {
                "bus": bus,
                "proxy_count": 0,
                "proxy_total_weight": 0.0,
                "weighted_distance_km": 0.0,
                "distances": [],
                "confidence_weight": 0.0,
            },
        )
        proxy_confidence = float(proxy.get("confidence") or default_confidence)
        bucket["proxy_count"] += 1
        bucket["proxy_total_weight"] += weight
        bucket["weighted_distance_km"] += distance_km * weight
        bucket["distances"].append(distance_km)
        bucket["confidence_weight"] += proxy_confidence * weight
    return assignments


def _nearest_load_bus(eligible: list[dict[str, Any]], point: tuple[float, float]) -> tuple[dict[str, Any] | None, float | None]:
    candidates = [
        (bus, _haversine_km(point, (float(bus["lat"]), float(bus["lon"]))))
        for bus in eligible
        if bus.get("lat") is not None and bus.get("lon") is not None
    ]
    if not candidates:
        bus = max(eligible, key=_load_allocation_weight, default=None)
        return bus, None
    return min(candidates, key=lambda item: (item[1], -_load_allocation_weight(item[0])))


def _nearest_proxy_service_territory(buses: list[dict[str, Any]], point: tuple[float, float]) -> str | None:
    candidates = []
    for territory in ("clp", "hk-electric"):
        eligible = _eligible_load_buses(buses, territory)
        fallback = _fallback_load_bus(buses, territory)
        if fallback is not None:
            eligible = [*eligible, fallback]
        bus, distance = _nearest_load_bus(eligible, point)
        if bus is not None and distance is not None:
            candidates.append((territory, distance, -_load_allocation_weight(bus)))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[1], item[2]))[0]


def _allocate_hk_electric_observed_loads(
    buses: list[dict[str, Any]],
    *,
    demand_snapshot: str,
    calibration: CalibrationBundle | None,
    consumer_proxies: list[Mapping[str, Any]] | None = None,
    proxy_assignments: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if calibration is None:
        return []
    eligible = _eligible_load_buses(buses, "hk-electric")
    if not eligible:
        fallback = _fallback_load_bus(buses, "hk-electric")
        eligible = [fallback] if fallback is not None else []
    if not eligible:
        return []

    loads: list[dict[str, Any]] = []
    source_file = calibration.metadata.get("district_source_file")
    proxies = list(consumer_proxies or [])
    for sector, sector_gwh in calibration.sector_gwh.items():
        proxy_loads = _proxy_allocated_sector_loads(
            buses,
            proxies,
            territory="hk-electric",
            sector=sector,
            sector_gwh=sector_gwh,
            sector_snapshot_mw=calibration.snapshot_mw_by_sector.get(sector, {}).get(demand_snapshot, 0.0),
            sector_peak_mw=calibration.peak_mw_by_sector.get(sector, 0.0),
            demand_snapshot=demand_snapshot,
            provenance="observed_hk_electric_proxy_allocated",
            source_file=source_file,
            source_year=calibration.source_year,
            source_period="annual" if not calibration.is_partial_year else "partial_year",
            source_periods=calibration.source_periods,
            confidence=0.68,
            proxy_assignments=proxy_assignments,
        )
        if proxy_loads:
            loads.extend(proxy_loads)
    proxied_sectors = {load["sector"] for load in loads}
    for district, sectors in calibration.district_sector_gwh.items():
        bus = _nearest_district_load_bus(eligible, district)
        if bus is None:
            continue
        for sector, district_gwh in sectors.items():
            if sector in proxied_sectors:
                continue
            sector_gwh = calibration.sector_gwh.get(sector, 0.0)
            sector_snapshot_mw = calibration.snapshot_mw_by_sector.get(sector, {}).get(demand_snapshot, 0.0)
            sector_peak_mw = calibration.peak_mw_by_sector.get(sector, 0.0)
            if district_gwh <= 0 or sector_gwh <= 0 or sector_snapshot_mw <= 0:
                continue
            share = district_gwh / sector_gwh
            pd_mw = sector_snapshot_mw * share
            peak_pd_mw = sector_peak_mw * share
            allocation_method = _hk_electric_allocation_method(bus)
            loads.append(
                {
                    "id": f"load:hk-electric:{district}:{sector}:{bus['id']}",
                    "bus_id": bus["id"],
                    "service_territory": "hk-electric",
                    "district": district,
                    "sector": sector,
                    "pd_mw": round(pd_mw, 3),
                    "qd_mvar": round(_reactive_mvar(pd_mw), 3),
                    "snapshot": demand_snapshot,
                    "provenance": "observed_hk_electric_substation_allocated",
                    "allocation_method": "observed_hk_electric_substation_allocated",
                    "allocation_rule": allocation_method,
                    "allocation_weight": round(share, 6),
                    "load_factor": round(pd_mw / peak_pd_mw, 6) if peak_pd_mw else None,
                    "peak_pd_mw": round(peak_pd_mw, 3),
                    "source_file": source_file,
                    "source_year": calibration.source_year,
                    "source_period": "annual" if not calibration.is_partial_year else "partial_year",
                    "source_periods": calibration.source_periods,
                    "source_energy_gwh": round(district_gwh, 3),
                    "geometry_provenance": "synthetic_geometry",
                    "confidence": 0.7,
                }
            )
    return loads


def _allocate_synthetic_clp_loads(
    buses: list[dict[str, Any]],
    *,
    demand_snapshot: str,
) -> list[dict[str, Any]]:
    load_factor = SYNTHETIC_CLP_SNAPSHOT_FACTORS[demand_snapshot]
    territory = "clp"
    eligible = _eligible_load_buses(buses, territory)
    if not eligible:
        fallback = _fallback_load_bus(buses, territory)
        eligible = [fallback] if fallback is not None else []
    if not eligible:
        return []
    weights = {bus["id"]: _load_allocation_weight(bus) for bus in eligible}
    total_weight = sum(weights.values())
    loads = []
    for bus in eligible:
        weight = weights[bus["id"]]
        peak_pd_mw = SYNTHETIC_CLP_PEAK_DEMAND_MW * weight / total_weight
        pd_mw = peak_pd_mw * load_factor
        loads.append(
            {
                "id": f"load:{territory}:{bus['id']}",
                "bus_id": bus["id"],
                "service_territory": territory,
                "pd_mw": round(pd_mw, 3),
                "qd_mvar": round(_reactive_mvar(pd_mw), 3),
                "snapshot": demand_snapshot,
                "provenance": "synthetic_missing_clp_data",
                "allocation_method": "synthetic_missing_clp_voltage_weighted_substation_split",
                "allocation_rule": "synthetic_missing_clp_voltage_weighted_substation_split",
                "load_factor": load_factor,
                "peak_pd_mw": round(peak_pd_mw, 3),
                "allocation_weight": round(weight, 6),
                "source_file": None,
                "source_year": None,
                "source_period": None,
                "confidence": 0.2,
            }
        )
    return loads


def _allocate_inferred_clp_loads(
    buses: list[dict[str, Any]],
    *,
    demand_snapshot: str,
    calibration: CalibrationBundle,
    consumer_proxies: list[Mapping[str, Any]] | None = None,
    proxy_assignments: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    territory = "clp"
    eligible = _eligible_load_buses(buses, territory)
    if not eligible:
        fallback = _fallback_load_bus(buses, territory)
        eligible = [fallback] if fallback is not None else []
    if not eligible:
        return []
    weights = {bus["id"]: _load_allocation_weight(bus) for bus in eligible}
    total_weight = sum(weights.values())
    source_file = calibration.metadata.get("hk_total_sector_source_file")
    source_files = [
        calibration.metadata.get("hk_total_sector_source_file"),
        calibration.metadata.get("customer_type_source_file"),
        calibration.metadata.get("census_validation_source_file"),
    ]
    source_files = [str(path) for path in source_files if path]
    loads: list[dict[str, Any]] = []
    proxies = list(consumer_proxies or [])
    for sector, sector_gwh in calibration.inferred_clp_sector_gwh.items():
        sector_snapshot_mw = calibration.clp_snapshot_mw_by_sector.get(sector, {}).get(demand_snapshot, 0.0)
        sector_peak_mw = calibration.clp_peak_mw_by_sector.get(sector, 0.0)
        if sector_gwh <= 0 or sector_snapshot_mw <= 0:
            continue
        proxy_loads = _proxy_allocated_sector_loads(
            buses,
            proxies,
            territory=territory,
            sector=sector,
            sector_gwh=sector_gwh,
            sector_snapshot_mw=sector_snapshot_mw,
            sector_peak_mw=sector_peak_mw,
            demand_snapshot=demand_snapshot,
            provenance="inferred_clp_proxy_allocated",
            source_file=source_file,
            source_files=source_files,
            source_year=calibration.source_year,
            source_period="annual",
            source_periods=calibration.source_periods,
            inference_method=calibration.clp_inference_method,
            confidence=0.58,
            proxy_assignments=proxy_assignments,
        )
        if proxy_loads:
            loads.extend(proxy_loads)
            continue
        for bus in eligible:
            weight = weights[bus["id"]]
            share = weight / total_weight
            pd_mw = sector_snapshot_mw * share
            peak_pd_mw = sector_peak_mw * share
            loads.append(
                {
                    "id": f"load:{territory}:{sector}:{bus['id']}",
                    "bus_id": bus["id"],
                    "service_territory": territory,
                    "sector": sector,
                    "pd_mw": round(pd_mw, 3),
                    "qd_mvar": round(_reactive_mvar(pd_mw), 3),
                    "snapshot": demand_snapshot,
                    "provenance": "inferred_clp_substation_allocated",
                    "allocation_method": "inferred_clp_substation_allocated",
                    "allocation_rule": "inferred_clp_voltage_weighted_substation_split",
                    "allocation_weight": round(weight, 6),
                    "load_factor": round(pd_mw / peak_pd_mw, 6) if peak_pd_mw else None,
                    "peak_pd_mw": round(peak_pd_mw, 3),
                    "source_file": source_file,
                    "source_files": source_files,
                    "source_year": calibration.source_year,
                    "source_period": "annual",
                    "source_periods": calibration.source_periods,
                    "source_energy_gwh": round(sector_gwh * share, 3),
                    "inference_method": calibration.clp_inference_method,
                    "confidence": 0.5,
                }
            )
    return loads


def _load_allocation_validation(loads: list[Mapping[str, Any]]) -> dict[str, Any]:
    total_mw = sum(float(load.get("pd_mw") or 0.0) for load in loads)
    proxy_mw = sum(float(load.get("pd_mw") or 0.0) for load in loads if "proxy_allocated" in str(load.get("provenance") or ""))
    fallback_mw = max(total_mw - proxy_mw, 0.0)
    proxy_share = round(proxy_mw / total_mw, 6) if total_mw else 0.0
    distances: list[float] = []
    proxy_count_by_sector: dict[str, int] = {}
    sector_totals: dict[str, float] = {}
    sector_pd_totals: dict[str, float] = {}
    bus_totals: dict[str, float] = {}
    proxy_distance_sum = 0.0
    proxy_distance_count = 0
    for load in loads:
        sector = str(load.get("sector") or "aggregate")
        sector_totals[sector] = sector_totals.get(sector, 0.0) + float(load.get("source_energy_gwh") or 0.0)
        sector_pd_totals[sector] = sector_pd_totals.get(sector, 0.0) + float(load.get("pd_mw") or 0.0)
        bus_id = str(load.get("bus_id") or "unknown")
        bus_totals[bus_id] = bus_totals.get(bus_id, 0.0) + float(load.get("pd_mw") or 0.0)
        proxy_count = int(load.get("proxy_count") or 0)
        if proxy_count:
            proxy_count_by_sector[sector] = proxy_count_by_sector.get(sector, 0) + proxy_count
            avg_distance = load.get("proxy_assignment_distance_avg_km")
            if avg_distance is not None:
                proxy_distance_sum += float(avg_distance) * proxy_count
                proxy_distance_count += proxy_count
        distance = load.get("proxy_assignment_distance_median_km")
        if distance is not None and proxy_count:
            distances.extend([float(distance)] * proxy_count)
    distances.sort()
    median_distance = distances[len(distances) // 2] if distances else None
    warnings = []
    if total_mw and proxy_share < 0.5:
        warnings.append({"code": "proxy_allocation_share_low", "message": "Less than 50 percent of modeled demand is allocated with consumer proxies."})
    if median_distance is not None and median_distance > 3.0:
        warnings.append({"code": "proxy_assignment_distance_high", "message": "Median proxy-to-bus assignment distance exceeds 3 km.", "median_distance_km": round(median_distance, 3)})
    sectors = sorted({str(load.get("sector")) for load in loads if load.get("sector")})
    for sector in sectors:
        if proxy_count_by_sector.get(sector, 0) == 0:
            warnings.append({"code": "sector_proxy_fallback", "message": "Sector has no proxy allocation and falls back to substations.", "sector": sector})
    method = "proxy_weighted_bus_sector_allocation" if proxy_mw > 0 else "voltage_weighted_substation_split"
    return {
        "method": method,
        "total_pd_mw": round(total_mw, 3),
        "proxy_allocated_pd_mw": round(proxy_mw, 3),
        "fallback_allocated_pd_mw": round(fallback_mw, 3),
        "proxy_allocation_share": proxy_share,
        "fallback_allocation_share": round(fallback_mw / total_mw, 6) if total_mw else 0.0,
        "proxy_count_by_sector": dict(sorted(proxy_count_by_sector.items())),
        "source_energy_gwh_by_sector": {key: round(value, 3) for key, value in sorted(sector_totals.items())},
        "average_proxy_to_bus_distance_km": round(proxy_distance_sum / proxy_distance_count, 3) if proxy_distance_count else None,
        "median_proxy_to_bus_distance_km": round(median_distance, 3) if median_distance is not None else None,
        "top_buses_by_allocated_demand": [
            {"bus_id": bus_id, "pd_mw": round(pd_mw, 3)}
            for bus_id, pd_mw in sorted(bus_totals.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "top_sectors_by_allocated_demand": [
            {"sector": sector, "pd_mw": round(pd_mw, 3)}
            for sector, pd_mw in sorted(sector_pd_totals.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "warnings": warnings,
    }


def _eligible_load_buses(buses: list[dict[str, Any]], territory: str) -> list[dict[str, Any]]:
    voltage_bands = (
        {"extra_high_voltage", "high_voltage", "subtransmission", "distribution"}
        if territory == "hk-electric"
        else {"extra_high_voltage", "high_voltage", "subtransmission"}
    )
    return [
        bus
        for bus in buses
        if bus.get("service_territory") == territory
        and bus.get("power") in {"substation", "sub_station"}
        and bus.get("voltage_band") in voltage_bands
    ]


def _nearest_district_load_bus(eligible: list[dict[str, Any]], district: str) -> dict[str, Any] | None:
    centroid = HK_ELECTRIC_DISTRICT_CENTROIDS.get(district)
    if centroid is None:
        return max(eligible, key=_load_allocation_weight, default=None)
    with_coordinates = [
        bus
        for bus in eligible
        if bus.get("lat") is not None and bus.get("lon") is not None
    ]
    if not with_coordinates:
        return max(eligible, key=_load_allocation_weight, default=None)
    return min(
        with_coordinates,
        key=lambda bus: (
            _haversine_km(centroid, (float(bus["lat"]), float(bus["lon"]))),
            -_load_allocation_weight(bus),
        ),
    )


def _hk_electric_allocation_method(bus: Mapping[str, Any]) -> str:
    if bus.get("voltage_band") in {"extra_high_voltage", "high_voltage"}:
        return "synthetic_geometry_nearest_hv_aggregate"
    return "synthetic_geometry_nearest_distribution_or_subtransmission"


def _topology_calibration_metadata(calibration: CalibrationBundle | None) -> dict[str, Any] | None:
    if calibration is None:
        return None
    return {
        "source_year": calibration.source_year,
        "source_periods": calibration.source_periods,
        "is_partial_year": calibration.is_partial_year,
        "territory": calibration.metadata["territory"],
        "provenance": calibration.metadata["provenance"],
        "observed_hk_electric_total_gwh": round(sum(calibration.sector_gwh.values()), 3),
        "sector_gwh": calibration.sector_gwh,
        "sector_shares": calibration.sector_shares,
        "end_use_year": calibration.end_use_year,
        "end_use_shares": calibration.end_use_shares,
        "snapshot_total_mw": calibration.snapshot_total_mw,
        "hk_total_sector_gwh": calibration.hk_total_sector_gwh,
        "hk_total_sector_source": calibration.hk_total_sector_source,
        "inferred_clp_sector_gwh": calibration.inferred_clp_sector_gwh,
        "inferred_clp_total_gwh": calibration.inferred_clp_total_gwh,
        "clp_inference_method": calibration.clp_inference_method,
        "clp_snapshot_total_mw": calibration.clp_snapshot_total_mw,
        "territory_total_validation": calibration.territory_total_validation,
        "monthly_total_validation": calibration.monthly_total_validation,
        "observed_inferred_synthetic_note": "HK Electric demand is observed from public CSVs; CLP demand is inferred from official Hong Kong totals minus observed HK Electric demand when EMSD Table 08 is available.",
    }


def _fallback_load_bus(buses: list[dict[str, Any]], territory: str) -> dict[str, Any] | None:
    candidates = [
        bus
        for bus in buses
        if bus.get("service_territory") == territory
        and bus.get("power") == "inferred_terminal"
        and bus.get("voltage_band") in {"extra_high_voltage", "high_voltage", "subtransmission"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda bus: (bus.get("base_kv") or 0.0, bus.get("confidence") or 0.0))


def _load_allocation_weight(bus: Mapping[str, Any]) -> float:
    base_kv = bus.get("base_kv")
    if base_kv is None:
        return 1.0
    if base_kv >= 220:
        return 3.0
    if base_kv >= 100:
        return 2.0
    if base_kv >= 33:
        return 1.0
    return 0.5


def _reactive_mvar(pd_mw: float, *, power_factor: float = LOAD_DEFAULTS["power_factor"]) -> float:
    return pd_mw * math.tan(math.acos(power_factor))


def _parameter_lookup_metadata() -> dict[str, Any]:
    return {
        "overhead_line_voltage_kv": sorted(OVERHEAD_LINE_DEFAULTS),
        "underground_cable_voltage_kv": sorted(UNDERGROUND_CABLE_DEFAULTS),
        "transformer_defaults": sorted(TRANSFORMER_DEFAULTS),
        "generator_fuel_defaults": sorted(GENERATOR_FUEL_DEFAULTS),
        "equivalent_generator_defaults": sorted(EQUIVALENT_GENERATOR_DEFAULTS),
        "load_power_factor": LOAD_DEFAULTS["power_factor"],
        "baseMVA": BASE_MVA,
    }


def _quality_summary(
    records: list[dict[str, Any]],
    buses: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    *,
    min_voltage_kv: float | None,
) -> dict[str, Any]:
    branches_without_voltage = sum(1 for branch in branches if branch["voltage_kv"] is None)
    synthetic_bus_count = sum(1 for bus in buses if bus["id"].startswith("synthetic:"))
    facility_footprint_count = sum(1 for bus in buses if bus.get("facility_match_method") == "geometry_footprint")
    buffered_point_facility_count = sum(1 for bus in buses if bus.get("facility_match_method") == "buffered_point_facility")
    support_count = sum(1 for record in records if record["asset_kind"] == "support")
    filtered_low_voltage_count = sum(
        1
        for record in records
        if record["asset_kind"] in {"bus_candidate", "branch"}
        and record["voltage_kv"]
        and _below_min_voltage(max(record["voltage_kv"]), min_voltage_kv)
    )
    return {
        "osm_record_count": len(records),
        "support_record_count": support_count,
        "branches_without_voltage": branches_without_voltage,
        "synthetic_bus_count": synthetic_bus_count,
        "facility_footprint_count": facility_footprint_count,
        "buffered_point_facility_count": buffered_point_facility_count,
        "filtered_low_voltage_count": filtered_low_voltage_count,
        "notes": [
            "Synthetic buses indicate line or cable endpoints that did not snap to a known substation or terminal.",
            "Loads are only allocated when service territory can be inferred from OSM operator/name tags.",
            "Electrical parameters are voltage-class defaults and must be relaxed and verified before optimization.",
        ],
    }
