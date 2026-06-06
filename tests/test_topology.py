from pathlib import Path
import shutil

import app.topology as topology_module
from app.topology import (
    _classify_preview_branch,
    build_powermodels_preview,
    build_topology_diagnostics,
    build_topology_preview,
    normalize_voltage,
    parse_circuit_count,
    parse_power_mw,
    split_voltage_circuits,
    validate_powermodels_case,
)


RAW_DIR = Path("data/raw")


def test_normalize_voltage_accepts_common_osm_formats() -> None:
    assert normalize_voltage("400000;132000") == [400.0, 132.0]
    assert normalize_voltage("275 kV / 132 kV") == [275.0, 132.0]
    assert normalize_voltage("110000;110000;bad") == [110.0]


def test_parse_power_mw_accepts_common_capacity_units() -> None:
    assert parse_power_mw("800 MW") == 800.0
    assert parse_power_mw("1.2 GW") == 1200.0
    assert parse_power_mw("750000 kW") == 750.0
    assert parse_power_mw("bad") is None


def test_parse_circuit_count_accepts_paper_osm_sources() -> None:
    assert parse_circuit_count({"circuits": "2"}) == (2, "circuits")
    assert parse_circuit_count({"cables": "6"}) == (2, "cables_div_3")
    assert parse_circuit_count({"voltage": "400000;132000"}) == (2, "multi_voltage")
    assert parse_circuit_count({}) == (1, "default_single_circuit")


def test_split_voltage_circuits_splits_multi_voltage_corridors() -> None:
    assert split_voltage_circuits({"voltage": "400000;132000", "circuits": "2"}) == [
        {"voltage_kv": 400.0, "circuit_count": 1, "count_source": "multi_voltage_split"},
        {"voltage_kv": 132.0, "circuit_count": 1, "count_source": "multi_voltage_split"},
    ]
    assert split_voltage_circuits({"voltage": "132000", "cables": "6"}) == [
        {"voltage_kv": 132.0, "circuit_count": 2, "count_source": "cables_div_3"},
    ]


def test_classify_preview_branch_detects_same_facility_loops() -> None:
    bus_by_id = {
        "hub:400": {"facility_id": "hub"},
        "hub:132": {"facility_id": "hub"},
        "remote:132": {"facility_id": "remote"},
    }

    assert _classify_preview_branch("hub:400", "hub:132", bus_by_id) == "loop"
    assert _classify_preview_branch("hub:132", "remote:132", bus_by_id) == "inter_facility"
    assert _classify_preview_branch("hub:132", "synthetic:way:1:0", bus_by_id) == "tap"


def test_topology_preview_snaps_branches_and_allocates_loads() -> None:
    rows = _sample_rows()

    preview = build_topology_preview(rows, snap_tolerance_km=0.2)

    assert preview["metadata"]["bus_count"] == 4
    assert preview["metadata"]["branch_count"] == 2
    assert preview["metadata"]["load_count"] == 23
    assert preview["metadata"]["demand_allocation_method"] == "voltage_weighted_substation_split"
    assert preview["metadata"]["calibration"]["observed_hk_electric_total_gwh"] == 10047.0
    assert preview["metadata"]["calibration"]["inferred_clp_total_gwh"] == 35480.223
    assert "CLP demand inferred from official Hong Kong totals" in preview["metadata"]["calibration_warnings"][0]
    assert preview["metadata"]["circuit_class_counts"] == {"inter_facility": 1, "isolated": 1}
    assert preview["metadata"]["circuit_candidate_count"] == 2
    assert preview["metadata"]["circuit_count_total"] == 3
    assert preview["quality"]["synthetic_bus_count"] == 2

    snapped_branch = next(branch for branch in preview["branches"] if branch["id"] == "osm:way:10")
    assert snapped_branch["from_bus_id"] == "osm:node:1"
    assert snapped_branch["to_bus_id"] == "osm:node:2"
    assert snapped_branch["endpoint_quality"][0]["snap"] == "matched"
    assert snapped_branch["parameter_defaults"]["matched_voltage_kv"] == 400.0
    assert snapped_branch["circuit_class"] == "inter_facility"
    assert snapped_branch["circuit_count"] == 2
    assert snapped_branch["circuit_count_source"] == "circuits"

    synthetic_branch = next(branch for branch in preview["branches"] if branch["id"] == "osm:way:11")
    assert synthetic_branch["endpoint_quality"][0]["snap"] == "synthetic"
    assert synthetic_branch["parameter_defaults"]["matched_voltage_kv"] == 132.0
    assert synthetic_branch["circuit_class"] == "isolated"
    assert synthetic_branch["circuit_count"] == 1
    assert synthetic_branch["circuit_count_source"] == "circuits"

    territories = {load["service_territory"] for load in preview["loads"]}
    assert territories == {"clp", "hk-electric"}
    clp_loads = [load for load in preview["loads"] if load["service_territory"] == "clp"]
    assert {load["sector"] for load in clp_loads} == {
        "residential",
        "commercial",
        "industrial",
        "transport_or_public_services",
    }
    assert {load["provenance"] for load in clp_loads} == {"inferred_clp_from_hk_total_minus_hk_electric"}
    assert {load["allocation_method"] for load in clp_loads} == {"inferred_clp_voltage_weighted_substation_split"}
    clp_by_bus_sector = {(load["bus_id"], load["sector"]): load for load in clp_loads}
    assert clp_by_bus_sector[("osm:node:1", "residential")]["source_energy_gwh"] == 5947.234
    assert clp_by_bus_sector[("osm:node:1", "residential")]["pd_mw"] == 1327.642


def test_topology_uses_synthetic_clp_only_when_public_total_is_missing(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    (raw_dir / "hk_electric").mkdir(parents=True)
    (raw_dir / "emsd").mkdir()
    shutil.copyfile(
        RAW_DIR / "hk_electric/consumption_by_district_and_customer_type.csv",
        raw_dir / "hk_electric/consumption_by_district_and_customer_type.csv",
    )
    shutil.copyfile(
        RAW_DIR / "hk_electric/consumption_by_customer_type.csv",
        raw_dir / "hk_electric/consumption_by_customer_type.csv",
    )
    shutil.copyfile(
        RAW_DIR / "emsd/energy_end_use_table12.csv",
        raw_dir / "emsd/energy_end_use_table12.csv",
    )
    monkeypatch.setattr(topology_module, "RAW_DATA_DIR", raw_dir)

    preview = build_topology_preview(_sample_rows(), snap_tolerance_km=0.2)

    clp_loads = [load for load in preview["loads"] if load["service_territory"] == "clp"]
    assert clp_loads
    assert {load["provenance"] for load in clp_loads} == {"synthetic_missing_clp_data"}
    assert {load["allocation_method"] for load in clp_loads} == {"synthetic_missing_clp_voltage_weighted_substation_split"}


def test_topology_preview_snaps_to_facility_footprint_buffer() -> None:
    rows = [
        {
            "osm_type": "way",
            "osm_id": 140,
            "power": "substation",
            "name": "Footprint Substation",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.30,
            "lon": 114.10,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": '[{"lat": 22.3000, "lon": 114.1000}, {"lat": 22.3010, "lon": 114.1000}]',
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 141,
            "power": "substation",
            "name": "Remote Substation",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.31,
            "lon": 114.11,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 142,
            "power": "line",
            "name": "Footprint Tie",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.305,
            "lon": 114.105,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": '[{"lat": 22.3010, "lon": 114.1000}, {"lat": 22.3100, "lon": 114.1100}]',
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    topology = build_topology_preview(rows, snap_tolerance_km=0.01)

    branch = topology["branches"][0]
    footprint_bus = next(bus for bus in topology["buses"] if bus["id"] == "osm:way:140")
    assert branch["from_bus_id"] == "osm:way:140"
    assert branch["endpoint_quality"][0]["snap"] == "matched"
    assert footprint_bus["facility_match_method"] == "geometry_footprint"
    assert footprint_bus["facility_radius_km"] > 0.1
    assert topology["quality"]["facility_footprint_count"] == 1
    assert topology["quality"]["buffered_point_facility_count"] == 1


def test_topology_preview_merges_fragmented_same_voltage_circuits() -> None:
    rows = [
        {
            "osm_type": "node",
            "osm_id": 100,
            "power": "substation",
            "name": "Alpha",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.30,
            "lon": 114.10,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 101,
            "power": "substation",
            "name": "Beta",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.32,
            "lon": 114.12,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 102,
            "power": "line",
            "name": "Alpha midpoint",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.305,
            "lon": 114.105,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": '[{"lat": 22.3001, "lon": 114.1001}, {"lat": 22.31, "lon": 114.11}]',
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 103,
            "power": "line",
            "name": "Midpoint Beta",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.315,
            "lon": 114.115,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": '[{"lat": 22.31, "lon": 114.11}, {"lat": 22.3199, "lon": 114.1199}]',
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    topology = build_topology_preview(rows, snap_tolerance_km=0.2)
    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)

    assert topology["metadata"]["bus_count"] == 2
    assert topology["metadata"]["branch_count"] == 1
    assert topology["metadata"]["merged_circuit_count"] == 1
    assert topology["metadata"]["merged_segment_count"] == 2
    merged = topology["branches"][0]
    assert merged["id"] == "merged:osm:way:102|osm:way:103"
    assert merged["from_bus_id"] == "osm:node:100"
    assert merged["to_bus_id"] == "osm:node:101"
    assert merged["circuit_class"] == "inter_facility"
    assert merged["merged_source_ids"] == ["osm:way:102", "osm:way:103"]
    assert case["_metadata"]["branch_count"] == 1
    assert all(not bus["source_id"].startswith("synthetic:") for bus in case["bus"].values())


def test_topology_preview_splits_multi_voltage_facilities_with_transformers() -> None:
    rows = [
        {
            "osm_type": "node",
            "osm_id": 120,
            "power": "substation",
            "name": "Multi Voltage Hub",
            "voltage": "400000;132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.30,
            "lon": 114.10,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000;132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 121,
            "power": "substation",
            "name": "High Voltage Neighbor",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.31,
            "lon": 114.11,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 122,
            "power": "substation",
            "name": "Low Voltage Neighbor",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.29,
            "lon": 114.09,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 123,
            "power": "line",
            "name": "400 kV tie",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.305,
            "lon": 114.105,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000"}',
            "geometry_json": '[{"lat": 22.3000, "lon": 114.1000}, {"lat": 22.3100, "lon": 114.1100}]',
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 124,
            "power": "line",
            "name": "132 kV tie",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.295,
            "lon": 114.095,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": '[{"lat": 22.3000, "lon": 114.1000}, {"lat": 22.2900, "lon": 114.0900}]',
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    topology = build_topology_preview(rows, snap_tolerance_km=0.2)
    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)

    assert topology["metadata"]["bus_count"] == 4
    assert topology["metadata"]["branch_count"] == 3
    assert topology["metadata"]["inferred_facility_transformer_count"] == 1
    high_bus = "osm:node:120:voltage:400"
    low_bus = "osm:node:120:voltage:132"
    assert {bus["id"] for bus in topology["buses"]} >= {high_bus, low_bus}
    assert next(branch for branch in topology["branches"] if branch["id"] == "osm:way:123")["from_bus_id"] == high_bus
    assert next(branch for branch in topology["branches"] if branch["id"] == "osm:way:124")["from_bus_id"] == low_bus
    inferred = next(
        branch
        for branch in case["branch"].values()
        if branch["provenance"] == "inferred_multi_voltage_facility_transformer"
    )
    assert inferred["transformer"] is True
    assert inferred["transformer_inference"]["method"] == "clear_voltage_mismatch_branch_conversion"
    assert case["_metadata"]["inferred_transformer_branch_count"] == 1


def test_powermodels_preview_exports_solver_handoff_shape() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)

    assert case["baseMVA"] == 100.0
    assert set(case) >= {"bus", "branch", "gen", "load", "shunt"}
    assert case["_metadata"]["total_pd_mw"] == 9492.178
    assert case["_metadata"]["gen_count"] == 2
    assert case["_metadata"]["reference_bus_count"] == 2
    assert case["_metadata"]["demand_allocation_method"] == "voltage_weighted_substation_split"
    assert case["_metadata"]["load_power_factor"] == 0.95
    assert case["_metadata"]["component_count"] == 2
    assert case["_metadata"]["load_bearing_component_count"] == 2
    assert case["_metadata"]["largest_component_bus_count"] == 2
    assert case["_metadata"]["largest_component_bus_share"] == 0.666667
    assert case["_metadata"]["largest_component_load_share"] > 0.75
    assert case["_metadata"]["cleanup_summary"]["component_count"] == 2
    assert case["_metadata"]["cleanup_summary"]["largest_component_load_mw"] == case["_metadata"]["largest_component_load_mw"]
    assert case["_metadata"]["dropped_non_interfacility_branch_count"] == 1
    assert case["_metadata"]["raw_solver_candidate_branch_count"] == 1

    assert sorted(case["bus"]) == ["1", "2", "3"]
    assert all(bus["index"] == bus["bus_i"] for bus in case["bus"].values())
    assert sum(1 for bus in case["bus"].values() if bus["bus_type"] == 3) == 2
    assert all(bus["type"] == bus["bus_type"] for bus in case["bus"].values())
    assert all(branch["br_r"] > 0 for branch in case["branch"].values())
    assert all(branch["br_x"] > 0 for branch in case["branch"].values())
    assert all(branch["g_fr"] == 0.0 for branch in case["branch"].values())
    assert all(branch["g_to"] == 0.0 for branch in case["branch"].values())
    assert all(branch["b_fr"] >= 0 for branch in case["branch"].values())
    assert all(branch["b_to"] >= 0 for branch in case["branch"].values())
    assert all(branch["b_us_per_km"] > 0 for branch in case["branch"].values())
    inferred_transformer = next(branch for branch in case["branch"].values() if branch["source_id"] == "osm:way:10")
    assert inferred_transformer["transformer"] is True
    assert inferred_transformer["parameter_source"] == "inferred_transformer_voltage_pair_default"
    assert inferred_transformer["parameter_table"] == "transformer_two_winding_defaults"
    assert inferred_transformer["transformer_inference"]["method"] == "clear_voltage_mismatch_branch_conversion"
    assert case["_metadata"]["inferred_transformer_branch_count"] == 1
    assert case["_metadata"]["synthetic_branch_count"] == 0
    assert case["_metadata"]["solver_circuit_class_counts"] == {"inter_facility": 1}
    assert case["_metadata"]["voltage_inference"] == {
        "tagged": 3,
        "inferred": 0,
        "unresolved": 0,
        "inferred_by_voltage_kv": {},
    }
    assert all(generator["model"] == 2 for generator in case["gen"].values())
    assert all(generator["ncost"] == 3 for generator in case["gen"].values())
    assert all(len(generator["cost"]) == 3 for generator in case["gen"].values())
    assert all(generator["resource_type"] == "territory_capacity_equivalent" for generator in case["gen"].values())
    assert {generator["cost_class"] for generator in case["gen"].values()} == {
        "territory_equivalent_import_or_local_supply",
        "island_local_supply_equivalent",
    }
    assert all(bus["provenance"] in {"osm", "osm_branch_endpoint"} for bus in case["bus"].values())
    assert {
        branch["parameter_source"]
        for branch in case["branch"].values()
    } == {"inferred_transformer_voltage_pair_default"}
    assert {
        branch["parameter_table"]
        for branch in case["branch"].values()
    } == {"transformer_two_winding_defaults"}
    assert {branch["circuit_class"] for branch in case["branch"].values()} == {"inter_facility"}
    assert all(branch["circuit_count"] >= 1 for branch in case["branch"].values())
    assert case["_metadata"]["parameter_lookup_tables"]["overhead_line_voltage_kv"] == [33.0, 110.0, 132.0, 220.0, 275.0, 400.0]
    assert case["_metadata"]["parameter_lookup_tables"]["underground_cable_voltage_kv"] == [33.0, 110.0, 132.0, 220.0, 275.0, 400.0]
    assert case["_metadata"]["parameter_lookup_tables"]["load_power_factor"] == 0.95
    assert case["_metadata"]["calibration"]["snapshot_total_mw"]["peak_16h"] == 2106.448
    assert case["_metadata"]["calibration"]["clp_snapshot_total_mw"]["peak_16h"] == 7385.731
    assert {load["provenance"] for load in case["load"].values()} == {
        "observed_hk_electric_public_consumption",
        "inferred_clp_from_hk_total_minus_hk_electric",
    }
    assert all(load["allocation_method"] for load in case["load"].values())
    assert case["_metadata"]["provenance_summary"]["branch"] == {"osm_with_inferred_parameters": 1}
    assert case["_metadata"]["provenance_summary"]["gen"] == {"public_peak_demand_capacity_equivalent": 2}
    assert case["_metadata"]["provenance_summary"]["load"] == {
        "observed_hk_electric_public_consumption": 15,
        "inferred_clp_from_hk_total_minus_hk_electric": 8,
    }
    assert sum(load["pd"] for load in case["load"].values()) == 94.92178
    assert sum(gen["pmax"] for gen in case["gen"].values()) > 94.92178


def test_powermodels_preview_exports_overnight_snapshot() -> None:
    peak_case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)
    overnight_case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        demand_snapshot="overnight_04h",
    )

    assert overnight_case["demand_snapshot"] == "overnight_04h"
    assert overnight_case["_metadata"]["load_factor"] == 0.435237
    assert overnight_case["_metadata"]["total_pd_mw"] == 4131.35
    assert sum(load["pd"] for load in overnight_case["load"].values()) == 41.3135
    assert sum(gen["pmax"] for gen in overnight_case["gen"].values()) == sum(
        gen["pmax"] for gen in peak_case["gen"].values()
    )


def test_powermodels_preview_exports_shoulder_and_cooling_snapshots() -> None:
    shoulder_case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        demand_snapshot="shoulder_10h",
    )
    cooling_case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        demand_snapshot="cooling_peak_18h",
    )

    assert shoulder_case["demand_snapshot"] == "shoulder_10h"
    assert shoulder_case["_metadata"]["load_factor"] == 0.792305
    assert shoulder_case["_metadata"]["total_pd_mw"] == 7520.705
    assert cooling_case["demand_snapshot"] == "cooling_peak_18h"
    assert cooling_case["_metadata"]["load_factor"] == 1.188839
    assert cooling_case["_metadata"]["total_pd_mw"] == 11284.668


def test_topology_preview_can_filter_known_low_voltage_assets() -> None:
    rows = [
        *_sample_rows(),
        {
            "osm_type": "node",
            "osm_id": 60,
            "power": "substation",
            "name": "CLP Low Voltage",
            "voltage": "11000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.35,
            "lon": 114.15,
            "tags_json": '{"operator": "CLP Power", "voltage": "11000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 61,
            "power": "minor_line",
            "name": "CLP Low Voltage Spur",
            "voltage": "11000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.355,
            "lon": 114.155,
            "tags_json": '{"operator": "CLP Power", "voltage": "11000"}',
            "geometry_json": '[{"lat": 22.35, "lon": 114.15}, {"lat": 22.36, "lon": 114.16}]',
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    unfiltered = build_topology_preview(rows, snap_tolerance_km=0.2)
    filtered = build_topology_preview(rows, snap_tolerance_km=0.2, min_voltage_kv=100.0)
    case = build_powermodels_preview(rows, snap_tolerance_km=0.2, min_voltage_kv=100.0)

    assert unfiltered["metadata"]["bus_count"] == 6
    assert unfiltered["metadata"]["branch_count"] == 3
    assert filtered["metadata"]["bus_count"] == 4
    assert filtered["metadata"]["branch_count"] == 2
    assert filtered["metadata"]["min_voltage_kv"] == 100.0
    assert filtered["quality"]["filtered_low_voltage_count"] == 2
    assert case["_metadata"]["min_voltage_kv"] == 100.0
    assert all(bus["base_kv"] >= 100.0 for bus in case["bus"].values())


def test_powermodels_preview_infers_missing_bus_voltage_from_incident_branches() -> None:
    rows = [
        {
            "osm_type": "node",
            "osm_id": 90,
            "power": "substation",
            "name": "Untyped Alpha",
            "voltage": None,
            "operator": None,
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.52,
            "lon": 114.30,
            "tags_json": "{}",
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 91,
            "power": "substation",
            "name": "Untyped Beta",
            "voltage": None,
            "operator": None,
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.53,
            "lon": 114.31,
            "tags_json": "{}",
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 92,
            "power": "line",
            "name": "Untyped 400kV Corridor",
            "voltage": "400000",
            "operator": None,
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.525,
            "lon": 114.305,
            "tags_json": '{"voltage": "400000"}',
            "geometry_json": '[{"lat": 22.52, "lon": 114.30}, {"lat": 22.53, "lon": 114.31}]',
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)

    assert case["_metadata"]["voltage_inference"] == {
        "tagged": 0,
        "inferred": 2,
        "unresolved": 0,
        "inferred_by_voltage_kv": {"400.0": 2},
    }
    assert {bus["base_kv"] for bus in case["bus"].values()} == {400.0}


def test_powermodels_preview_uses_endpoint_voltage_for_untagged_branch_parameters() -> None:
    rows = [
        {
            "osm_type": "node",
            "osm_id": 130,
            "power": "substation",
            "name": "Alpha",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.30,
            "lon": 114.10,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "node",
            "osm_id": 131,
            "power": "substation",
            "name": "Beta",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.31,
            "lon": 114.11,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
        {
            "osm_type": "way",
            "osm_id": 132,
            "power": "line",
            "name": "Untagged voltage tie",
            "voltage": None,
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.305,
            "lon": 114.105,
            "tags_json": '{"operator": "CLP Power"}',
            "geometry_json": '[{"lat": 22.3000, "lon": 114.1000}, {"lat": 22.3100, "lon": 114.1100}]',
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)

    branch = next(iter(case["branch"].values()))
    assert branch["rate_a"] == 1800.0
    assert branch["matched_voltage_kv"] == 400.0
    assert branch["parameter_table"] == "overhead_line_defaults"


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
        {
            "osm_type": "way",
            "osm_id": 51,
            "power": "line",
            "name": "Tagged Plant Interconnect",
            "voltage": "400000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": "1",
            "location": None,
            "lat": 22.31,
            "lon": 114.11,
            "tags_json": '{"operator": "CLP Power", "voltage": "400000"}',
            "geometry_json": '[{"lat": 22.32, "lon": 114.12}, {"lat": 22.30, "lon": 114.10}]',
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
    tagged_export = next(generator for generator in case["gen"].values() if generator["source_id"] == "gen:node:50")
    assert tagged_export["provenance"] == "osm_capacity_tag"
    assert tagged_export["confidence"] == 0.7
    assert tagged_export["energy_source"] == "gas"
    assert tagged_export["resource_type"] == "local_osm_generator"
    assert tagged_export["cost_class"] == "thermal_gas"
    assert tagged_export["pmin"] == 0.0


def test_powermodels_preview_prunes_disconnected_no_load_generation_island() -> None:
    rows = [
        *_sample_rows(),
        {
            "osm_type": "node",
            "osm_id": 55,
            "power": "plant",
            "name": "Disconnected Plant",
            "voltage": "132000",
            "operator": None,
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.60,
            "lon": 114.40,
            "tags_json": '{"generator:source": "gas", "generator:output:electricity": "50 MW"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)
    validation = validate_powermodels_case(case)

    assert case["_metadata"]["dropped_no_load_generation_island_count"] == 1
    assert case["_metadata"]["dropped_no_load_generation_bus_count"] == 1
    assert case["_metadata"]["dropped_no_load_generation_pmax_mw"] == 50.0
    assert case["_metadata"]["tagged_gen_count"] == 0
    assert all(generator["source_id"] != "gen:node:55" for generator in case["gen"].values())
    assert validation["metrics"]["island_count"] == 2


def test_powermodels_preview_connects_load_islands_with_synthetic_backbone() -> None:
    rows = [
        *_sample_rows(),
        {
            "osm_type": "node",
            "osm_id": 70,
            "power": "substation",
            "name": "CLP Remote Island",
            "voltage": "132000",
            "operator": "CLP Power",
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.45,
            "lon": 114.25,
            "tags_json": '{"operator": "CLP Power", "voltage": "132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    topology = build_topology_preview(rows, snap_tolerance_km=0.2)
    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)
    validation = validate_powermodels_case(case)

    backbone = [
        branch
        for branch in topology["branches"]
        if branch["provenance"] == "synthetic_service_territory_backbone"
    ]
    equivalent_gens = [
        generator
        for generator in case["gen"].values()
        if generator["resource_type"] == "territory_capacity_equivalent"
    ]
    assert topology["metadata"]["synthetic_service_territory_backbone_count"] == 1
    assert len(backbone) == 1
    assert backbone[0]["service_territory"] == "clp"
    assert backbone[0]["provenance"] == "synthetic_service_territory_backbone"
    assert backbone[0]["parameter_defaults"]["parameter_table"] == "underground_cable_defaults"
    assert case["_metadata"]["synthetic_branch_count"] == 1
    assert case["_metadata"]["provenance_summary"]["branch"]["synthetic_service_territory_backbone"] == 1
    assert len(equivalent_gens) == 2
    assert validation["metrics"]["island_count"] == 2
    assert "load_island_without_generation" not in {error["code"] for error in validation["errors"]}


def test_powermodels_preview_drops_passive_components_from_solver_case() -> None:
    rows = [
        *_sample_rows(),
        {
            "osm_type": "node",
            "osm_id": 80,
            "power": "terminal",
            "name": "Passive Terminal",
            "voltage": "132000",
            "operator": None,
            "frequency": "50",
            "cables": None,
            "circuits": None,
            "location": None,
            "lat": 22.50,
            "lon": 114.30,
            "tags_json": '{"voltage": "132000"}',
            "geometry_json": None,
            "updated_at": "2026-01-01 00:00:00",
        },
    ]

    topology = build_topology_preview(rows, snap_tolerance_km=0.2)
    case = build_powermodels_preview(rows, snap_tolerance_km=0.2)

    assert topology["metadata"]["bus_count"] == 5
    assert case["_metadata"]["bus_count"] == 3
    assert case["_metadata"]["raw_bus_count"] == 5
    assert case["_metadata"]["retained_bus_count"] == 3
    assert case["_metadata"]["dropped_passive_bus_count"] == 2
    assert case["_metadata"]["cleanup_summary"]["dropped_passive_bus_count"] == 2
    assert case["_metadata"]["voltage_inference"]["unresolved"] == 0
    assert all(bus["source_id"] != "osm:node:80" for bus in case["bus"].values())


def test_powermodels_preview_can_include_hk_intertie() -> None:
    topology = build_topology_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        include_hk_interties=True,
    )
    case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        include_hk_interties=True,
    )
    validation = validate_powermodels_case(case)

    intertie = next(branch for branch in topology["branches"] if branch["id"] == "synthetic:intertie:clp-hk-electric")
    exported_intertie = next(branch for branch in case["branch"].values() if branch["source_id"] == intertie["id"])
    assert topology["metadata"]["include_hk_interties"] is True
    assert case["_metadata"]["include_hk_interties"] is True
    assert case["_metadata"]["reference_bus_count"] == 1
    assert topology["metadata"]["branch_count"] == 3
    assert intertie["provenance"] == "public_interconnection_capacity_equivalent"
    assert exported_intertie["rate_a"] == 720.0
    assert exported_intertie["b_fr"] > 0
    assert exported_intertie["b_to"] > 0
    assert exported_intertie["b_us_per_km"] == 18.0
    assert exported_intertie["parameter_source"] == "public_interconnection_capacity_equivalent"
    assert exported_intertie["confidence"] == 0.5
    assert case["_metadata"]["provenance_summary"]["branch"]["public_interconnection_capacity_equivalent"] == 1
    assert validation["status"] == "warning"
    assert "severe_branch_voltage_mismatch" in {warning["code"] for warning in validation["warnings"]}
    assert validation["metrics"]["island_count"] == 1


def test_topology_diagnostics_reports_synthetic_branches_and_voltage_mismatches() -> None:
    case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        include_hk_interties=True,
    )
    validation = validate_powermodels_case(case)

    diagnostics = build_topology_diagnostics(case)

    assert diagnostics["summary"]["solver_branch_count"] == case["_metadata"]["branch_count"]
    assert diagnostics["summary"]["synthetic_branch_count"] == 1
    assert diagnostics["summary"]["synthetic_branch_share"] == 0.5
    assert diagnostics["summary"]["voltage_mismatch_count"] == validation["metrics"]["branch_voltage_mismatch_count"]
    assert diagnostics["summary"]["severe_voltage_mismatch_count"] == validation["metrics"]["severe_branch_voltage_mismatch_count"]
    assert diagnostics["summary"]["missing_provenance_count"] == 0
    synthetic = diagnostics["synthetic_branches"][0]
    assert synthetic["source_id"] == "synthetic:intertie:clp-hk-electric"
    assert synthetic["provenance"] == "public_interconnection_capacity_equivalent"
    assert synthetic["category"] == "public_interconnection_capacity_equivalent"
    assert synthetic["recommended_action"] == "keep as documented equivalent"
    assert synthetic["from_bus"]["source_id"]
    assert synthetic["to_bus"]["base_kv"] is not None
    assert synthetic["rate_mva"] == 720.0
    mismatch = diagnostics["voltage_mismatches"][0]
    assert mismatch["source_id"] == "synthetic:intertie:clp-hk-electric"
    assert mismatch["severe"] is True
    assert mismatch["provenance"] == "public_interconnection_capacity_equivalent"
    assert mismatch["recommended_action"] in {
        "correct branch voltage from endpoint consensus",
        "review OSM tags manually",
    }
    assert mismatch["endpoints"][0]["bus_source_id"]
    assert mismatch["endpoints"][0]["relative_difference"] >= 0.5
    assert diagnostics["recommended_next_fixes"]


def test_powermodels_preview_can_derate_hk_intertie() -> None:
    topology = build_topology_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        include_hk_interties=True,
        hk_intertie_derate=0.5,
    )
    case = build_powermodels_preview(
        _sample_rows(),
        snap_tolerance_km=0.2,
        include_hk_interties=True,
        hk_intertie_derate=0.5,
    )

    intertie = next(branch for branch in topology["branches"] if branch["id"] == "synthetic:intertie:clp-hk-electric")
    exported_intertie = next(branch for branch in case["branch"].values() if branch["source_id"] == intertie["id"])
    assert intertie["derate_factor"] == 0.5
    assert intertie["parameter_defaults"]["rate_mva"] == 360.0
    assert case["_metadata"]["hk_intertie_derate"] == 0.5
    assert exported_intertie["rate_a"] == 360.0


def test_topology_preview_rejects_invalid_derate() -> None:
    try:
        build_topology_preview(_sample_rows(), hk_intertie_derate=0.0)
    except ValueError as exc:
        assert "Derate factor" in str(exc)
    else:
        raise AssertionError("Expected invalid derate to raise ValueError")


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

    assert validation["status"] == "warning"
    assert validation["metrics"]["island_count"] == 2
    assert validation["metrics"]["total_pd_mw"] == 9492.178
    assert validation["metrics"]["low_confidence_counts"] == {"branch": 0, "bus": 1, "gen": 2, "load": 0}
    assert validation["metrics"]["branch_voltage_mismatch_count"] == 0
    assert validation["metrics"]["severe_branch_voltage_mismatch_count"] == 0
    assert validation["metrics"]["provenance_summary"]["load"] == {
        "observed_hk_electric_public_consumption": 15,
        "inferred_clp_from_hk_total_minus_hk_electric": 8,
    }
    assert validation["metrics"]["calibration"]["hk_electric_territory"]["status"] == "pass"
    assert validation["metrics"]["calibration"]["clp_inferred_sector"]["commercial"]["status"] == "pass"
    assert validation["metrics"]["calibration"]["official_total_source_energy"]["status"] == "pass"
    assert validation["metrics"]["calibration"]["load_provenance_class_share"]["synthetic"] == 0.0
    assert validation["metrics"]["calibration"]["load_provenance_class_share"]["inferred"] == 0.778086
    assert validation["voltage_mismatches"] == []
    assert validation["errors"] == []
    assert validation["warnings"] == [
        {
            "code": "clp_inferred_from_territory_total",
            "severity": "info",
            "message": "CLP demand inferred from official Hong Kong totals minus observed HK Electric demand; spatial placement remains inferred.",
        }
    ]
    assert all(island["reference_bus_count"] == 1 for island in validation["islands"])


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


def test_powermodels_validation_requires_reference_per_generator_island() -> None:
    case = build_powermodels_preview(_sample_rows(), snap_tolerance_km=0.2)
    for bus in case["bus"].values():
        if bus["bus_type"] == 3:
            bus["bus_type"] = 2
            bus["type"] = 2

    validation = validate_powermodels_case(case)

    assert validation["status"] == "error"
    assert "island_missing_reference_bus" in {error["code"] for error in validation["errors"]}


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
