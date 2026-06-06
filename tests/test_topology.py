from app.topology import build_topology_preview, normalize_voltage


def test_normalize_voltage_accepts_common_osm_formats() -> None:
    assert normalize_voltage("400000;132000") == [400.0, 132.0]
    assert normalize_voltage("275 kV / 132 kV") == [275.0, 132.0]
    assert normalize_voltage("110000;110000;bad") == [110.0]


def test_topology_preview_snaps_branches_and_allocates_loads() -> None:
    rows = [
        {
            "osm_type": "node",
            "osm_id": 1,
            "power": "substation",
            "name": "CLP Alpha",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": None,
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.30,
            "lon": 114.10,
            "tags_json": '{"operator": "CLP Power"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 2,
            "power": "substation",
            "name": "CLP Beta",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": None,
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.31,
            "lon": 114.11,
            "tags_json": '{"operator": "CLP Power"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 10,
            "power": "line",
            "name": "Alpha Beta",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "2",
            "location": None,
            "lat": 22.305,
            "lon": 114.105,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000"}',
            "geometry_json": (
                '[{"lat": 22.3001, "lon": 114.1001},'
                ' {"lat": 22.3101, "lon": 114.1101}]'
            ),
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 11,
            "power": "cable",
            "name": "Unsnapped Cable",
            "voltage": "132000",
            "operator": "HK Electric",
            "frequency": "50",
            "cables": "3",
            "circuits": "1",
            "location": "underground",
            "lat": 22.20,
            "lon": 114.20,
            "tags_json": '{"operator": "HK Electric", "voltage": "132000"}',
            "geometry_json": (
                '[{"lat": 22.2000, "lon": 114.2000},'
                ' {"lat": 22.2100, "lon": 114.2100}]'
            ),
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    preview = build_topology_preview(rows, snap_tolerance_km=0.2)

    assert preview["metadata"]["bus_count"] == 4
    assert preview["metadata"]["branch_count"] == 2
    assert preview["metadata"]["load_count"] == 4
    assert preview["quality"]["synthetic_bus_count"] == 2

    snapped_branch = next(branch for branch in preview["branches"] if branch["id"] == "osm:way:10")
    assert snapped_branch["from_bus_id"] == "osm:node:1"
    assert snapped_branch["to_bus_id"] == "osm:node:2"
    assert snapped_branch["endpoint_quality"][0]["snap"] == "matched"
    assert snapped_branch["parameter_defaults"]["matched_voltage_kv"] == 400.0

    synthetic_branch = next(branch for branch in preview["branches"] if branch["id"] == "osm:way:11")
    assert synthetic_branch["endpoint_quality"][0]["snap"] == "synthetic"
    assert synthetic_branch["parameter_defaults"]["matched_voltage_kv"] == 132.0

    territories = {load["service_territory"] for load in preview["loads"]}
    assert territories == {"clp", "hk-electric"}
