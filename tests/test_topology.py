from app.topology import (
    build_powermodels_preview,
    build_topology_preview,
    normalize_voltage,
    parse_power_mw,
    validate_powermodels_case,
)


def test_normalize_voltage_accepts_common_osm_formats() -> None:
    assert normalize_voltage("400000;132000") == [400.0, 132.0]
    assert normalize_voltage("275 kV / 132 kV") == [275.0, 132.0]
    assert normalize_voltage("110000;110000;bad") == [110.0]


def test_parse_power_mw_accepts_common_capacity_units() -> None:
    assert parse_power_mw("800 MW") == 800.0
    assert parse_power_mw("1.2 GW") == 1200.0
    assert parse_power_mw("750000 kW") == 750.0
    assert parse_power_mw("bad") is None


def test_topology_preview_snaps_branches_and_allocates_loads() -> None:
    rows = _sample_rows()

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


def test_powermodels_preview_exports_solver_handoff_shape() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)

    assert case["baseMVA"] == 100.0
    assert set(case) >= {"bus", "branch", "gen", "load", "shunt"}
    assert case["_metadata"]["total_pd_mw"] == 9591.0
    assert case["_metadata"]["gen_count"] == 2

    assert sorted(case["bus"]) == ["1", "2", "3", "4"]
    assert any(bus["bus_type"] == 3 for bus in case["bus"].values())
    assert all(bus["type"] == bus["bus_type"] for bus in case["bus"].values())
    assert all(branch["br_r"] > 0 for branch in case["branch"].values())
    assert all(branch["br_x"] > 0 for branch in case["branch"].values())
    assert all(generator["model"] == 2 for generator in case["gen"].values())
    assert all(generator["ncost"] == 3 for generator in case["gen"].values())
    assert all(len(generator["cost"]) == 3 for generator in case["gen"].values())
    assert sum(load["pd"] for load in case["load"].values()) == 95.91
    assert sum(gen["pmax"] for gen in case["gen"].values()) > 95.91


def test_powermodels_preview_exports_overnight_snapshot() -> None:
    peak_case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)
    overnight_case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        demand_snapshot="overnight_04h",
    )

    assert overnight_case["demand_snapshot"] == "overnight_04h"
    assert overnight_case["_metadata"]["load_factor"] == 0.55
    assert overnight_case["_metadata"]["total_pd_mw"] == 5275.05
    assert sum(load["pd"] for load in overnight_case["load"].values()) == 52.7505
    assert sum(gen["pmax"] for gen in overnight_case["gen"].values()) == sum(
        gen["pmax"] for gen in peak_case["gen"].values()
    )


def test_powermodels_preview_exports_tagged_generator_capacity() -> None:
    rows = [
        *_sample_rows(),
        {
            "osm_type": "node",
            "osm_id": 50,
            "power": "plant",
            "name": "Tagged Gas Plant",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.32,
            "lon": 114.12,
            "tags_json": '{"operator": "CLP Power", "generator:source": "gas", "generator:output:electricity": "800 MW"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    topology = build_topology_preview(rows, snap_tolerance_km=0.2)
    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)

    tagged_preview = next(generator for generator in topology["generators"] if generator["id"] == "gen:node:50")
    assert tagged_preview["pmax_mw"] == 800.0
    assert tagged_preview["capacity_tag"] == "generator:output:electricity"
    assert case["_metadata"]["tagged_gen_count"] == 1
    assert case["_metadata"]["equivalent_gen_count"] == 2
    assert case["_metadata"]["total_tagged_pmax_mw"] == 800.0
    assert any(generator["source_id"] == "gen:node:50" for generator in case["gen"].values())


def test_topology_preview_rejects_unknown_demand_snapshot() -> None:
    try:
        build_topology_preview(_sample_rows(), demand_snapshot="lunch")
    except ValueError as exc:
        assert "Unknown demand snapshot 'lunch'" in str(exc)
    else:
        raise AssertionError("Expected unknown demand snapshot to raise ValueError")


def test_powermodels_validation_reports_islands_and_capacity() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)

    validation = validate_powermodels_case(case)

    assert validation["status"] == "ok"
    assert validation["metrics"]["island_count"] == 2
    assert validation["metrics"]["total_pd_mw"] == 9591.0
    assert validation["errors"] == []


def test_powermodels_validation_rejects_load_island_without_generation() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)
    case["gen"] = {}

    validation = validate_powermodels_case(case)

    assert validation["status"] == "error"
    error_codes = {error["code"] for error in validation["errors"]}
    assert "no_generators" in error_codes
    assert "generation_capacity_shortfall" in error_codes
    assert "load_island_without_generation" in error_codes


def test_powermodels_validation_requires_native_bus_type() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)
    del case["bus"]["1"]["bus_type"]

    validation = validate_powermodels_case(case)

    assert validation["status"] == "error"
    assert {
        "code": "bus_missing_field",
        "message": "Bus is missing a required PowerModels field.",
        "bus_id": "1",
        "field": "bus_type",
    } in validation["errors"]


def test_powermodels_validation_requires_quadratic_generator_cost() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)
    case["gen"]["1"]["model"] = 1

    validation = validate_powermodels_case(case)

    assert validation["status"] == "error"
    assert "gen_invalid_polynomial_cost" in {error["code"] for error in validation["errors"]}


def _sample_rows() -> list[dict[str, object]]:
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
    return rows
