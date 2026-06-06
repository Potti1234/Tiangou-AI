import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any


PROXY_GROUPS: dict[str, tuple[tuple[str, str | None], ...]] = {
    "buildings": (
        ("building", None),
        ("building:levels", None),
        ("height", None),
    ),
    "landuse": (
        ("landuse", "residential"),
        ("landuse", "commercial"),
        ("landuse", "retail"),
        ("landuse", "industrial"),
        ("landuse", "port"),
    ),
    "pois": (
        ("office", None),
        ("shop", "mall"),
        ("amenity", "hospital"),
        ("amenity", "school"),
        ("amenity", "university"),
        ("amenity", "college"),
    ),
    "transport": (
        ("railway", "station"),
        ("public_transport", "station"),
        ("aeroway", "aerodrome"),
        ("aeroway", "terminal"),
        ("amenity", "ferry_terminal"),
        ("amenity", "charging_station"),
    ),
    "industrial_infrastructure": (
        ("man_made", "works"),
        ("man_made", "wastewater_plant"),
        ("man_made", "water_works"),
    ),
}


DEFAULT_POI_WEIGHTS: dict[tuple[str, str], float] = {
    ("office", "*"): 25.0,
    ("shop", "mall"): 120.0,
    ("amenity", "hospital"): 160.0,
    ("amenity", "school"): 45.0,
    ("amenity", "university"): 90.0,
    ("amenity", "college"): 65.0,
    ("railway", "station"): 80.0,
    ("public_transport", "station"): 45.0,
    ("aeroway", "aerodrome"): 350.0,
    ("aeroway", "terminal"): 180.0,
    ("amenity", "ferry_terminal"): 50.0,
    ("amenity", "charging_station"): 12.0,
    ("man_made", "works"): 100.0,
    ("man_made", "wastewater_plant"): 90.0,
    ("man_made", "water_works"): 80.0,
}


def consumer_proxy_query_filters(group: str | None = None) -> tuple[tuple[str, str | None], ...]:
    if group is not None:
        try:
            return PROXY_GROUPS[group]
        except KeyError as exc:
            known = ", ".join(sorted(PROXY_GROUPS))
            raise ValueError(f"Unknown consumer proxy group '{group}'. Known groups: {known}") from exc
    filters: list[tuple[str, str | None]] = []
    for group_filters in PROXY_GROUPS.values():
        filters.extend(group_filters)
    return tuple(dict.fromkeys(filters))


def normalize_consumer_proxy_element(element: Mapping[str, Any], *, region_key: str) -> dict[str, Any] | None:
    tags = dict(element.get("tags") or {})
    classification = classify_proxy(tags)
    if classification is None:
        return None
    geometry = element.get("geometry")
    lat, lon = _point(element)
    weight_info = proxy_weight(tags, geometry)
    return {
        "osm_type": element["type"],
        "osm_id": int(element["id"]),
        "region_key": region_key,
        "proxy_type": classification["proxy_type"],
        "sector": classification["sector"],
        "weight": weight_info["weight"],
        "weight_method": weight_info["weight_method"],
        "confidence": min(float(classification["confidence"]), float(weight_info["confidence"])),
        "name": tags.get("name") or tags.get("name:en"),
        "tags": tags,
        "geometry": geometry,
        "lat": lat,
        "lon": lon,
    }


def rows_to_consumer_proxies(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    proxies = []
    for row in rows:
        data = dict(row)
        tags_json = data.pop("tags_json", None)
        geometry_json = data.pop("geometry_json", None)
        data["tags"] = json.loads(tags_json) if tags_json else {}
        data["geometry"] = json.loads(geometry_json) if geometry_json else None
        proxies.append(data)
    return proxies


def classify_proxy(tags: Mapping[str, Any]) -> dict[str, Any] | None:
    building = str(tags.get("building") or "").lower()
    landuse = str(tags.get("landuse") or "").lower()
    amenity = str(tags.get("amenity") or "").lower()
    man_made = str(tags.get("man_made") or "").lower()
    railway = str(tags.get("railway") or "").lower()
    public_transport = str(tags.get("public_transport") or "").lower()
    aeroway = str(tags.get("aeroway") or "").lower()
    office = tags.get("office")
    shop = str(tags.get("shop") or "").lower()

    if building:
        if building in {"residential", "apartments", "house", "detached", "terrace", "dormitory"}:
            return {"sector": "residential", "proxy_type": "building", "confidence": 0.85}
        if building in {"industrial", "warehouse", "factory"}:
            return {"sector": "industrial", "proxy_type": "building", "confidence": 0.75}
        if building in {"transportation", "train_station", "station"}:
            return {"sector": "transport_or_public_services", "proxy_type": "building", "confidence": 0.7}
        return {"sector": "commercial", "proxy_type": "building", "confidence": 0.55}

    if landuse in {"residential", "commercial", "retail", "industrial", "port"}:
        sector = "residential" if landuse == "residential" else "industrial" if landuse in {"industrial", "port"} else "commercial"
        return {"sector": sector, "proxy_type": "landuse", "confidence": 0.8}
    if office:
        return {"sector": "commercial", "proxy_type": "office", "confidence": 0.75}
    if shop == "mall":
        return {"sector": "commercial", "proxy_type": "mall", "confidence": 0.8}
    if amenity in {"hospital", "school", "university", "college"}:
        return {"sector": "commercial", "proxy_type": amenity, "confidence": 0.72}
    if man_made in {"works", "wastewater_plant", "water_works"}:
        return {"sector": "industrial", "proxy_type": man_made, "confidence": 0.75}
    if railway == "station" or public_transport == "station":
        return {"sector": "transport_or_public_services", "proxy_type": "station", "confidence": 0.75}
    if aeroway in {"aerodrome", "terminal"}:
        return {"sector": "transport_or_public_services", "proxy_type": aeroway, "confidence": 0.8}
    if amenity in {"ferry_terminal", "charging_station"}:
        return {"sector": "transport_or_public_services", "proxy_type": amenity, "confidence": 0.75}
    return None


def proxy_weight(tags: Mapping[str, Any], geometry: Any) -> dict[str, Any]:
    area = polygon_area_m2(geometry)
    levels = _parse_positive_float(tags.get("building:levels"))
    height = _parse_height_m(tags.get("height"))
    floor_multiplier = levels if levels is not None else max(height / 3.2, 1.0) if height is not None else 1.0

    if tags.get("building") and area:
        return {
            "weight": round(max(area * floor_multiplier, 1.0), 3),
            "weight_method": "building_floor_area_proxy",
            "confidence": 0.8 if floor_multiplier > 1.0 else 0.65,
        }
    if tags.get("landuse") and area:
        return {
            "weight": round(max(area, 1.0), 3),
            "weight_method": "landuse_polygon_area_proxy",
            "confidence": 0.72,
        }

    charging_weight = _charging_station_weight(tags)
    if charging_weight is not None:
        return {"weight": charging_weight, "weight_method": "charging_station_socket_count", "confidence": 0.65}

    default = _default_poi_weight(tags)
    return {"weight": default, "weight_method": "poi_default_weight", "confidence": 0.5}


def polygon_area_m2(geometry: Any) -> float | None:
    if not isinstance(geometry, list) or len(geometry) < 3:
        return None
    points = [(float(point["lat"]), float(point["lon"])) for point in geometry if "lat" in point and "lon" in point]
    if len(points) < 3:
        return None
    lat0 = math.radians(sum(lat for lat, _ in points) / len(points))
    xy = []
    for lat, lon in points:
        x = math.radians(lon) * math.cos(lat0) * 6_371_000.0
        y = math.radians(lat) * 6_371_000.0
        xy.append((x, y))
    area = 0.0
    for index, (x1, y1) in enumerate(xy):
        x2, y2 = xy[(index + 1) % len(xy)]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0
    return area or None


def _point(element: Mapping[str, Any]) -> tuple[float | None, float | None]:
    if element.get("lat") is not None and element.get("lon") is not None:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if isinstance(center, Mapping) and center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    geometry = element.get("geometry")
    if isinstance(geometry, list) and geometry:
        lats = [float(point["lat"]) for point in geometry if "lat" in point]
        lons = [float(point["lon"]) for point in geometry if "lon" in point]
        if lats and lons:
            return sum(lats) / len(lats), sum(lons) / len(lons)
    return None, None


def _default_poi_weight(tags: Mapping[str, Any]) -> float:
    for key in ("office", "shop", "amenity", "man_made", "railway", "public_transport", "aeroway"):
        value = tags.get(key)
        if value is None:
            continue
        return DEFAULT_POI_WEIGHTS.get((key, str(value).lower()), DEFAULT_POI_WEIGHTS.get((key, "*"), 20.0))
    return 10.0


def _charging_station_weight(tags: Mapping[str, Any]) -> float | None:
    if tags.get("amenity") != "charging_station":
        return None
    for key in ("capacity", "charging_station:capacity", "socket:count"):
        count = _parse_positive_float(tags.get(key))
        if count is not None:
            return round(max(count, 1.0) * 6.0, 3)
    socket_count = sum(
        _parse_positive_float(value) or 0.0
        for key, value in tags.items()
        if str(key).startswith("socket:")
    )
    return round(max(socket_count, 1.0) * 6.0, 3)


def _parse_positive_float(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", str(raw).replace(",", ""))
    if not match:
        return None
    value = float(match.group(0))
    return value if value > 0 else None


def _parse_height_m(raw: Any) -> float | None:
    return _parse_positive_float(raw)
