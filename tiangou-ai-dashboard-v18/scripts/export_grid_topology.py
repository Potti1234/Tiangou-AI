#!/usr/bin/env python3
"""
Export a Python grid-topology module to JSON for the Tiangou AI React dashboard.

Usage:
    python scripts/export_grid_topology.py path/to/team_topology.py
    python scripts/export_grid_topology.py path/to/team_topology.py --output public/grid-topology.json

Accepted Python module interfaces:
    TOPOLOGY = {"assets": [...], "circuits": [...]}
    topology = {"nodes": [...], "edges": [...]}
    get_topology() -> dict
    build_topology() -> dict

Supported node aliases:
    assets | nodes | buses
    lat | latitude | y
    lon | lng | longitude | x
    voltage | kv | voltage_kv

Supported circuit aliases:
    circuits | lines | edges | links
    points | geometry | coordinates | path
    from/to | source/target | u/v
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


def load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("tiangou_team_topology", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import topology module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_payload(module: ModuleType) -> dict[str, Any]:
    for callable_name in ("get_topology", "build_topology"):
        candidate = getattr(module, callable_name, None)
        if callable(candidate):
            payload = candidate()
            if isinstance(payload, dict):
                return payload

    for attribute_name in ("TOPOLOGY", "topology"):
        payload = getattr(module, attribute_name, None)
        if isinstance(payload, dict):
            return payload

    raise RuntimeError(
        "Topology module must define TOPOLOGY, topology, get_topology(), or build_topology()."
    )


def first(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def normalise_point(point: Any) -> list[float] | None:
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return [float(point[0]), float(point[1])]
    if isinstance(point, dict):
        lon = first(point, "lon", "lng", "longitude", "x")
        lat = first(point, "lat", "latitude", "y")
        if lon is not None and lat is not None:
            return [float(lon), float(lat)]
    return None


def normalise(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_assets = first(payload, "assets", "nodes", "buses", default=[]) or []
    raw_circuits = first(payload, "circuits", "lines", "edges", "links", default=[]) or []

    assets: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_assets):
        item = dict(raw)
        node_id = str(first(item, "id", "name", default=f"node-{index + 1}"))
        lat = first(item, "lat", "latitude", "y")
        lon = first(item, "lon", "lng", "longitude", "x")
        if lat is None or lon is None:
            raise ValueError(f"Node {node_id!r} is missing latitude/longitude.")
        assets.append(
            {
                "id": node_id,
                "name": str(first(item, "name", "label", default=node_id)),
                "kind": str(first(item, "kind", "type", default="substation")),
                "owner": str(first(item, "owner", "operator", default="Unknown")),
                "voltage": first(item, "voltage", "kv", "voltage_kv"),
                "source": str(first(item, "source", "energy_source", "fuel", default="unspecified")),
                "lat": float(lat),
                "lon": float(lon),
                "note": str(first(item, "note", "description", default="")),
            }
        )

    asset_by_id = {asset["id"]: asset for asset in assets}

    circuits: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_circuits):
        item = dict(raw)
        circuit_id = str(first(item, "id", "name", default=f"circuit-{index + 1}"))
        raw_points = first(item, "points", "geometry", "coordinates", "path", default=[]) or []
        points = [normalise_point(point) for point in raw_points]
        points = [point for point in points if point is not None]

        if len(points) < 2:
            from_id = str(first(item, "from", "source", "u", default=""))
            to_id = str(first(item, "to", "target", "v", default=""))
            from_node = asset_by_id.get(from_id)
            to_node = asset_by_id.get(to_id)
            if from_node and to_node:
                points = [
                    [from_node["lon"], from_node["lat"]],
                    [to_node["lon"], to_node["lat"]],
                ]

        if len(points) < 2:
            raise ValueError(f"Circuit {circuit_id!r} has no valid geometry or endpoint references.")

        circuits.append(
            {
                "id": circuit_id,
                "name": str(first(item, "name", "label", default=circuit_id)),
                "owner": str(first(item, "owner", "operator", default="Unknown")),
                "voltage": first(item, "voltage", "kv", "voltage_kv"),
                "cableType": str(first(item, "cableType", "cable_type", "type", default="overhead / line")),
                "circuits": first(item, "circuits", "number_of_circuits"),
                "points": points,
            }
        )

    return {"assets": assets, "circuits": circuits}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("topology_file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("public/grid-topology.json"))
    args = parser.parse_args()

    module = load_module(args.topology_file.resolve())
    payload = extract_payload(module)
    exported = normalise(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(exported, indent=2), encoding="utf-8")

    print(f"Exported {len(exported['assets'])} assets and {len(exported['circuits'])} circuits")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
