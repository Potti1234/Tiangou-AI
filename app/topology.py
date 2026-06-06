import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any


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

HK_PEAK_DEMAND_MW = {
    "clp": 7336.0,
    "hk-electric": 2255.0,
}
BASE_MVA = 100.0

VOLTAGE_DEFAULTS = {
    "line": {
        400.0: {"r_ohm_per_km": 0.028, "x_ohm_per_km": 0.32, "rate_mva": 1800.0},
        275.0: {"r_ohm_per_km": 0.035, "x_ohm_per_km": 0.34, "rate_mva": 1200.0},
        220.0: {"r_ohm_per_km": 0.045, "x_ohm_per_km": 0.38, "rate_mva": 900.0},
        132.0: {"r_ohm_per_km": 0.08, "x_ohm_per_km": 0.42, "rate_mva": 450.0},
        110.0: {"r_ohm_per_km": 0.10, "x_ohm_per_km": 0.45, "rate_mva": 350.0},
        33.0: {"r_ohm_per_km": 0.25, "x_ohm_per_km": 0.35, "rate_mva": 90.0},
    },
    "cable": {
        400.0: {"r_ohm_per_km": 0.018, "x_ohm_per_km": 0.12, "rate_mva": 1400.0},
        275.0: {"r_ohm_per_km": 0.023, "x_ohm_per_km": 0.13, "rate_mva": 900.0},
        220.0: {"r_ohm_per_km": 0.03, "x_ohm_per_km": 0.14, "rate_mva": 700.0},
        132.0: {"r_ohm_per_km": 0.055, "x_ohm_per_km": 0.16, "rate_mva": 300.0},
        110.0: {"r_ohm_per_km": 0.07, "x_ohm_per_km": 0.18, "rate_mva": 250.0},
        33.0: {"r_ohm_per_km": 0.20, "x_ohm_per_km": 0.20, "rate_mva": 75.0},
    },
}


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
) -> tuple[str | None, float | None]:
    best_id = None
    best_distance = None
    for bus in buses:
        if bus["lat"] is None or bus["lon"] is None:
            continue
        distance = _haversine_km(point, (bus["lat"], bus["lon"]))
        if best_distance is None or distance < best_distance:
            best_id = bus["id"]
            best_distance = distance
    if best_distance is None or best_distance > snap_tolerance_km:
        return None, best_distance
    return best_id, best_distance


def _branch_defaults(power: str, voltage_kv: float | None) -> dict[str, Any]:
    if voltage_kv is None:
        return {"r_ohm_per_km": None, "x_ohm_per_km": None, "rate_mva": None}
    table = VOLTAGE_DEFAULTS["cable" if power == "cable" else "line"]
    nearest = min(table, key=lambda candidate: abs(candidate - voltage_kv))
    defaults = dict(table[nearest])
    defaults["matched_voltage_kv"] = nearest
    return defaults


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


def build_topology_preview(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
) -> dict[str, Any]:
    records = [_row_to_record(row) for row in rows]
    buses: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    generators: list[dict[str, Any]] = []

    for record in records:
        if record["asset_kind"] != "bus_candidate":
            continue
        bus_id = f"osm:{record['osm_type']}:{record['osm_id']}"
        base_kv = max(record["voltage_kv"]) if record["voltage_kv"] else None
        buses.append(
            {
                "id": bus_id,
                "source": {"osm_type": record["osm_type"], "osm_id": record["osm_id"]},
                "name": record.get("name"),
                "power": record["power"],
                "lat": record.get("lat"),
                "lon": record.get("lon"),
                "base_kv": base_kv,
                "voltage_band": voltage_band(base_kv),
                "service_territory": record["service_territory"],
                "provenance": "osm",
                "confidence": 0.85 if base_kv else 0.55,
            }
        )
        if record["power"] in {"plant", "generator"}:
            generators.append(
                {
                    "id": f"gen:{record['osm_type']}:{record['osm_id']}",
                    "bus_id": bus_id,
                    "name": record.get("name"),
                    "source": record["tags"].get("generator:source"),
                    "method": record["tags"].get("generator:method"),
                    "pmax_mw": None,
                    "provenance": "osm_without_capacity",
                    "confidence": 0.45,
                }
            )

    synthetic_buses: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["asset_kind"] != "branch":
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
            bus_id, distance = _nearest_bus(buses, point, snap_tolerance_km)
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
                        "base_kv": max(record["voltage_kv"]) if record["voltage_kv"] else None,
                        "voltage_band": voltage_band(max(record["voltage_kv"]) if record["voltage_kv"] else None),
                        "service_territory": record["service_territory"],
                        "provenance": "osm_branch_endpoint",
                        "confidence": 0.35,
                    }
                endpoint_bus_ids.append(synthetic_id)
                endpoint_quality.append({"snap": "synthetic", "nearest_bus_km": distance})
            else:
                endpoint_bus_ids.append(bus_id)
                endpoint_quality.append({"snap": "matched", "distance_km": distance})

        voltage_kv = max(record["voltage_kv"]) if record["voltage_kv"] else None
        defaults = _branch_defaults(record["power"], voltage_kv)
        length_km = _geometry_length_km(geometry)
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
                "parameter_defaults": defaults,
                "endpoint_quality": endpoint_quality,
                "provenance": "osm_with_inferred_parameters",
                "confidence": 0.65 if voltage_kv and length_km else 0.4,
            }
        )

    buses.extend(synthetic_buses.values())
    load_allocations = _allocate_peak_loads(buses)
    return {
        "metadata": {
            "schema": "tiangou.topology_preview.v1",
            "snap_tolerance_km": snap_tolerance_km,
            "bus_count": len(buses),
            "branch_count": len(branches),
            "generator_count": len(generators),
            "load_count": len(load_allocations),
        },
        "buses": buses,
        "branches": branches,
        "generators": generators,
        "loads": load_allocations,
        "quality": _quality_summary(records, buses, branches),
    }


def build_powermodels_preview(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
) -> dict[str, Any]:
    topology = build_topology_preview(rows, snap_tolerance_km=snap_tolerance_km)
    return topology_preview_to_powermodels(topology)


def topology_preview_to_powermodels(topology: Mapping[str, Any]) -> dict[str, Any]:
    buses = list(topology["buses"])
    branches = [
        branch
        for branch in topology["branches"]
        if branch.get("from_bus_id") and branch.get("to_bus_id") and branch.get("from_bus_id") != branch.get("to_bus_id")
    ]
    loads = list(topology["loads"])

    bus_id_map = {bus["id"]: str(index) for index, bus in enumerate(buses, start=1)}
    gen_bus_ids = set(_equivalent_generator_buses(buses, loads))
    load_bus_ids = {load["bus_id"] for load in loads}
    reference_bus_id = _reference_bus_id(buses, gen_bus_ids)

    bus_dict = {}
    for bus in buses:
        bus_number = bus_id_map[bus["id"]]
        bus_dict[bus_number] = {
            "bus_i": int(bus_number),
            "type": _powermodels_bus_type(bus["id"], reference_bus_id, gen_bus_ids, load_bus_ids),
            "base_kv": bus.get("base_kv") or 132.0,
            "vmin": 0.9,
            "vmax": 1.1,
            "vm": 1.0,
            "va": 0.0,
            "zone": 1,
            "source_id": bus["id"],
        }

    branch_dict = {}
    for index, branch in enumerate(branches, start=1):
        branch_dict[str(index)] = _powermodels_branch(index, branch, bus_id_map)

    load_dict = {}
    for index, load in enumerate(loads, start=1):
        load_dict[str(index)] = {
            "index": index,
            "load_bus": int(bus_id_map[load["bus_id"]]),
            "pd": round(load["pd_mw"] / BASE_MVA, 6),
            "qd": round(load["qd_mvar"] / BASE_MVA, 6),
            "status": 1,
            "source_id": load["id"],
        }

    gen_dict = {}
    for index, generator in enumerate(_equivalent_generators(buses, loads), start=1):
        gen_dict[str(index)] = {
            "index": index,
            "gen_bus": int(bus_id_map[generator["bus_id"]]),
            "pg": 0.0,
            "qg": 0.0,
            "pmax": round(generator["pmax_mw"] / BASE_MVA, 6),
            "pmin": 0.0,
            "qmax": round(generator["pmax_mw"] * 0.6 / BASE_MVA, 6),
            "qmin": round(-generator["pmax_mw"] * 0.6 / BASE_MVA, 6),
            "vg": 1.0,
            "mbase": BASE_MVA,
            "gen_status": 1,
            "model": 2,
            "ncost": 3,
            "cost": generator["cost"],
            "source_id": generator["id"],
        }

    return {
        "name": "hong_kong_osm_preview",
        "source_version": "tiangou.powermodels_preview.v1",
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
            "bus_count": len(bus_dict),
            "branch_count": len(branch_dict),
            "load_count": len(load_dict),
            "gen_count": len(gen_dict),
            "total_pd_mw": round(sum(load["pd_mw"] for load in loads), 3),
            "total_equivalent_pmax_mw": round(sum(gen["pmax_mw"] for gen in _equivalent_generators(buses, loads)), 3),
            "notes": [
                "This is a PowerModels handoff preview built from public OSM topology and inferred parameters.",
                "Equivalent generators represent territory-level local supply or imports; run relaxation and validation before optimization.",
            ],
        },
    }


def _powermodels_bus_type(
    bus_id: str,
    reference_bus_id: str | None,
    gen_bus_ids: set[str],
    load_bus_ids: set[str],
) -> int:
    if bus_id == reference_bus_id:
        return 3
    if bus_id in gen_bus_ids:
        return 2
    if bus_id in load_bus_ids:
        return 1
    return 1


def _reference_bus_id(buses: list[dict[str, Any]], gen_bus_ids: set[str]) -> str | None:
    candidates = [bus for bus in buses if bus["id"] in gen_bus_ids]
    if not candidates:
        candidates = buses
    if not candidates:
        return None
    return max(candidates, key=lambda bus: bus.get("base_kv") or 0.0)["id"]


def _powermodels_branch(
    index: int,
    branch: Mapping[str, Any],
    bus_id_map: Mapping[str, str],
) -> dict[str, Any]:
    voltage_kv = branch.get("voltage_kv") or 132.0
    length_km = branch.get("length_km") or 1.0
    defaults = branch.get("parameter_defaults") or {}
    r_ohm = (defaults.get("r_ohm_per_km") or 0.08) * length_km
    x_ohm = (defaults.get("x_ohm_per_km") or 0.42) * length_km
    z_base_ohm = (voltage_kv * voltage_kv) / BASE_MVA

    return {
        "index": index,
        "f_bus": int(bus_id_map[str(branch["from_bus_id"])]),
        "t_bus": int(bus_id_map[str(branch["to_bus_id"])]),
        "br_r": round(max(r_ohm / z_base_ohm, 0.00001), 8),
        "br_x": round(max(x_ohm / z_base_ohm, 0.00001), 8),
        "b_fr": 0.0,
        "b_to": 0.0,
        "rate_a": defaults.get("rate_mva") or 100.0,
        "rate_b": defaults.get("rate_mva") or 100.0,
        "rate_c": defaults.get("rate_mva") or 100.0,
        "tap": 1.0,
        "shift": 0.0,
        "br_status": 1,
        "angmin": -0.523599,
        "angmax": 0.523599,
        "transformer": False,
        "source_id": branch["id"],
    }


def _equivalent_generator_buses(
    buses: list[dict[str, Any]],
    loads: list[dict[str, Any]],
) -> list[str]:
    return [generator["bus_id"] for generator in _equivalent_generators(buses, loads)]


def _equivalent_generators(
    buses: list[dict[str, Any]],
    loads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    loads_by_territory: dict[str, float] = {}
    for load in loads:
        territory = load["service_territory"]
        loads_by_territory[territory] = loads_by_territory.get(territory, 0.0) + load["pd_mw"]

    generators = []
    for territory, pd_mw in sorted(loads_by_territory.items()):
        bus = _best_generator_bus(buses, territory)
        if bus is None:
            continue
        pmax_mw = max(pd_mw * 1.25, 100.0)
        generators.append(
            {
                "id": f"equivalent_gen:{territory}",
                "bus_id": bus["id"],
                "service_territory": territory,
                "pmax_mw": pmax_mw,
                "cost": [0.01, 20.0 if territory == "clp" else 24.0, 0.0],
            }
        )

    if not generators and buses:
        bus = max(buses, key=lambda candidate: candidate.get("base_kv") or 0.0)
        generators.append(
            {
                "id": "equivalent_gen:unassigned",
                "bus_id": bus["id"],
                "service_territory": "unassigned",
                "pmax_mw": 100.0,
                "cost": [0.01, 30.0, 0.0],
            }
        )
    return generators


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


def _allocate_peak_loads(buses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    loads = []
    for territory, peak_mw in HK_PEAK_DEMAND_MW.items():
        eligible = [
            bus
            for bus in buses
            if bus.get("service_territory") == territory
            and bus.get("power") in {"substation", "sub_station", "inferred_terminal"}
            and bus.get("voltage_band") in {"extra_high_voltage", "high_voltage", "subtransmission"}
        ]
        if not eligible:
            continue
        pd_mw = peak_mw / len(eligible)
        for bus in eligible:
            loads.append(
                {
                    "id": f"load:{territory}:{bus['id']}",
                    "bus_id": bus["id"],
                    "service_territory": territory,
                    "pd_mw": round(pd_mw, 3),
                    "qd_mvar": round(pd_mw * 0.329, 3),
                    "snapshot": "peak_2024",
                    "provenance": "public_peak_demand_equal_substation_split",
                    "confidence": 0.35,
                }
            )
    return loads


def _quality_summary(
    records: list[dict[str, Any]],
    buses: list[dict[str, Any]],
    branches: list[dict[str, Any]],
) -> dict[str, Any]:
    branches_without_voltage = sum(1 for branch in branches if branch["voltage_kv"] is None)
    synthetic_bus_count = sum(1 for bus in buses if bus["id"].startswith("synthetic:"))
    support_count = sum(1 for record in records if record["asset_kind"] == "support")
    return {
        "osm_record_count": len(records),
        "support_record_count": support_count,
        "branches_without_voltage": branches_without_voltage,
        "synthetic_bus_count": synthetic_bus_count,
        "notes": [
            "Synthetic buses indicate line or cable endpoints that did not snap to a known substation or terminal.",
            "Loads are only allocated when service territory can be inferred from OSM operator/name tags.",
            "Electrical parameters are voltage-class defaults and must be relaxed and verified before optimization.",
        ],
    }
