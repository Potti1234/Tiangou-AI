from app.load_proxies import classify_proxy, normalize_consumer_proxy_element, polygon_area_m2, proxy_weight


def test_proxy_sector_classification() -> None:
    assert classify_proxy({"building": "apartments"})["sector"] == "residential"
    assert classify_proxy({"landuse": "industrial"})["sector"] == "industrial"
    assert classify_proxy({"office": "company"})["sector"] == "commercial"
    assert classify_proxy({"railway": "station"})["sector"] == "transport_or_public_services"
    assert classify_proxy({"amenity": "cafe"}) is None


def test_proxy_weight_uses_building_floor_area() -> None:
    geometry = [
        {"lat": 22.3000, "lon": 114.1000},
        {"lat": 22.3000, "lon": 114.1010},
        {"lat": 22.3010, "lon": 114.1010},
        {"lat": 22.3010, "lon": 114.1000},
    ]
    area = polygon_area_m2(geometry)
    weight = proxy_weight({"building": "residential", "building:levels": "20"}, geometry)

    assert area is not None
    assert weight["weight_method"] == "building_floor_area_proxy"
    assert weight["weight"] > area * 19


def test_proxy_ingest_row_normalization_without_network() -> None:
    element = {
        "type": "node",
        "id": 99,
        "lat": 22.31,
        "lon": 114.11,
        "tags": {"amenity": "charging_station", "capacity": "8", "name": "Mock Chargers"},
    }

    proxy = normalize_consumer_proxy_element(element, region_key="hong-kong")

    assert proxy["sector"] == "transport_or_public_services"
    assert proxy["proxy_type"] == "charging_station"
    assert proxy["weight"] == 48.0
    assert proxy["name"] == "Mock Chargers"
