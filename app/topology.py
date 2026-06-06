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


def build_topology_preview(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
) -> dict[str, Any]:
    _validate_derate(hk_intertie_derate)
    snapshot = _demand_snapshot(demand_snapshot)
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
            pmax_mw, capacity_tag = _generator_capacity(record["tags"])
            generators.append(
                {
                    "id": f"gen:{record['osm_type']}:{record['osm_id']}",
                    "bus_id": bus_id,
                    "name": record.get("name"),
                    "source": record["tags"].get("generator:source"),
                    "method": record["tags"].get("generator:method"),
                    "pmax_mw": pmax_mw,
                    "capacity_tag": capacity_tag,
                    "provenance": "osm_capacity_tag" if pmax_mw is not None else "osm_without_capacity",
                    "confidence": 0.7 if pmax_mw is not None else 0.45,
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
    if include_hk_interties:
        branches.extend(_hk_intertie_branches(buses, derate=hk_intertie_derate))
    load_allocations = _allocate_loads(buses, demand_snapshot=demand_snapshot)
    return {
        "metadata": {
            "schema": "tiangou.topology_preview.v1",
            "snap_tolerance_km": snap_tolerance_km,
            "demand_snapshot": demand_snapshot,
            "demand_snapshot_label": snapshot["label"],
            "load_factor": snapshot["load_factor"],
            "include_hk_interties": include_hk_interties,
            "hk_intertie_derate": hk_intertie_derate,
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
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
) -> dict[str, Any]:
    topology = build_topology_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
    )
    return topology_preview_to_powermodels(topology)


def build_powermodels_validation(
    rows: Iterable[Any],
    *,
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
) -> dict[str, Any]:
    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
    )
    return validate_powermodels_case(case)


def topology_preview_to_powermodels(topology: Mapping[str, Any]) -> dict[str, Any]:
    buses = list(topology["buses"])
    branches = [
        branch
        for branch in topology["branches"]
        if branch.get("from_bus_id") and branch.get("to_bus_id") and branch.get("from_bus_id") != branch.get("to_bus_id")
    ]
    loads = list(topology["loads"])
    tagged_generators = _tagged_generators(topology.get("generators", []))
    equivalent_generators = _equivalent_generators(buses, loads)
    all_generators = [*tagged_generators, *equivalent_generators]

    bus_id_map = {bus["id"]: str(index) for index, bus in enumerate(buses, start=1)}
    gen_bus_ids = {generator["bus_id"] for generator in all_generators}
    load_bus_ids = {load["bus_id"] for load in loads}
    reference_bus_ids = _reference_bus_ids_by_island(buses, branches, gen_bus_ids)

    bus_dict = {}
    for bus in buses:
        bus_number = bus_id_map[bus["id"]]
        bus_type = _powermodels_bus_type(bus["id"], reference_bus_ids, gen_bus_ids, load_bus_ids)
        bus_dict[bus_number] = {
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
            "provenance": bus.get("provenance"),
            "confidence": bus.get("confidence"),
            "service_territory": bus.get("service_territory"),
            "voltage_band": bus.get("voltage_band"),
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
            "provenance": load.get("provenance"),
            "confidence": load.get("confidence"),
            "service_territory": load.get("service_territory"),
            "snapshot": load.get("snapshot"),
        }

    gen_dict = {}
    for index, generator in enumerate(all_generators, start=1):
        gen_dict[str(index)] = {
            "index": index,
            "source_id": generator["id"],
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
            "provenance": generator.get("provenance"),
            "confidence": generator.get("confidence"),
            "service_territory": generator.get("service_territory"),
        }

    return {
        "name": "hong_kong_osm_preview",
        "source_version": "tiangou.powermodels_preview.v1",
        "demand_snapshot": topology["metadata"]["demand_snapshot"],
        "include_hk_interties": topology["metadata"]["include_hk_interties"],
        "hk_intertie_derate": topology["metadata"]["hk_intertie_derate"],
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
            "include_hk_interties": topology["metadata"]["include_hk_interties"],
            "hk_intertie_derate": topology["metadata"]["hk_intertie_derate"],
            "bus_count": len(bus_dict),
            "branch_count": len(branch_dict),
            "load_count": len(load_dict),
            "gen_count": len(gen_dict),
            "tagged_gen_count": len(tagged_generators),
            "equivalent_gen_count": len(equivalent_generators),
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
        for field in ("bus_i", "bus_type", "base_kv", "vmin", "vmax", "vm", "va"):
            if field not in bus:
                errors.append({"code": "bus_missing_field", "message": "Bus is missing a required PowerModels field.", "bus_id": bus_id, "field": field})
                missing_fields.append(field)
        if missing_fields:
            continue
        if "bus_type" in bus and int(bus["bus_type"]) not in {1, 2, 3, 4}:
            errors.append({"code": "bus_invalid_type", "message": "Bus has an invalid PowerModels bus_type.", "bus_id": bus_id})

    for branch_id, branch in branches.items():
        missing_fields = []
        for field in ("f_bus", "t_bus", "br_r", "br_x", "rate_a", "angmin", "angmax", "br_status"):
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
    quality_metrics = _case_quality_metrics(buses, branches, loads, generators)
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
            "low_confidence_counts": quality_metrics["low_confidence_counts"],
            "provenance_summary": quality_metrics["provenance_summary"],
        },
        "islands": island_report["islands"],
    }


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
    for load in loads.values():
        load_buses[load["load_bus"]] = load_buses.get(load["load_bus"], 0) + 1

    gen_buses: dict[int, int] = {}
    for generator in generators.values():
        gen_buses[generator["gen_bus"]] = gen_buses.get(generator["gen_bus"], 0) + 1

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
        "provenance": branch.get("provenance"),
        "confidence": branch.get("confidence"),
        "parameter_source": branch.get("provenance"),
        "matched_voltage_kv": defaults.get("matched_voltage_kv"),
        "length_km": length_km,
    }


def _validate_derate(derate: float) -> None:
    if derate <= 0 or derate > 1:
        raise ValueError("Derate factor must be greater than 0 and less than or equal to 1.")


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
            "parameter_defaults": {
                "r_ohm_per_km": 0.055,
                "x_ohm_per_km": 0.16,
                "rate_mva": round(HK_INTERTIE_RATE_MVA * derate, 3),
                "matched_voltage_kv": 132.0,
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


def _tagged_generators(generators: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    tagged = []
    for generator in generators:
        pmax_mw = generator.get("pmax_mw")
        if pmax_mw is None:
            continue
        tagged.append(
            {
                "id": generator["id"],
                "bus_id": generator["bus_id"],
                "service_territory": None,
                "pmax_mw": float(pmax_mw),
                "cost": _generator_cost(generator.get("source")),
                "provenance": generator.get("provenance"),
                "confidence": generator.get("confidence"),
            }
        )
    return tagged


def _generator_cost(source: Any) -> list[float]:
    source_text = str(source or "").lower()
    if "coal" in source_text:
        return [0.012, 26.0, 0.0]
    if "gas" in source_text:
        return [0.01, 22.0, 0.0]
    if "nuclear" in source_text:
        return [0.004, 12.0, 0.0]
    if "solar" in source_text or "wind" in source_text:
        return [0.0, 2.0, 0.0]
    if "waste" in source_text:
        return [0.006, 18.0, 0.0]
    return [0.01, 24.0, 0.0]


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
        capacity_anchor_mw = HK_PEAK_DEMAND_MW.get(territory, pd_mw)
        pmax_mw = max(capacity_anchor_mw * 1.25, 100.0)
        generators.append(
            {
                "id": f"equivalent_gen:{territory}",
                "bus_id": bus["id"],
                "service_territory": territory,
                "pmax_mw": pmax_mw,
                "cost": [0.01, 20.0 if territory == "clp" else 24.0, 0.0],
                "provenance": "public_peak_demand_capacity_equivalent",
                "confidence": 0.35,
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
                "provenance": "fallback_capacity_equivalent",
                "confidence": 0.2,
            }
        )
    return generators


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


def _demand_snapshot(demand_snapshot: str) -> dict[str, Any]:
    try:
        return DEMAND_SNAPSHOTS[demand_snapshot]
    except KeyError as exc:
        known = ", ".join(sorted(DEMAND_SNAPSHOTS))
        raise ValueError(f"Unknown demand snapshot '{demand_snapshot}'. Known snapshots: {known}") from exc


def _allocate_loads(
    buses: list[dict[str, Any]],
    *,
    demand_snapshot: str,
) -> list[dict[str, Any]]:
    snapshot = _demand_snapshot(demand_snapshot)
    load_factor = snapshot["load_factor"]
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
        pd_mw = peak_mw * load_factor / len(eligible)
        for bus in eligible:
            loads.append(
                {
                    "id": f"load:{territory}:{bus['id']}",
                    "bus_id": bus["id"],
                    "service_territory": territory,
                    "pd_mw": round(pd_mw, 3),
                    "qd_mvar": round(pd_mw * 0.329, 3),
                    "snapshot": demand_snapshot,
                    "provenance": "public_peak_demand_scaled_equal_substation_split",
                    "load_factor": load_factor,
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
