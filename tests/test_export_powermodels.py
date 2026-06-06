import json
from pathlib import Path

import pytest

from app.database import connect, init_db
from app.export_load_allocation import export_hk_electric_load_allocation
from app.export_powermodels import export_hong_kong_phase1_bundle, export_powermodels_case
from app.export_topology_diagnostics import export_topology_diagnostics
from app.repository import create_ingest_run, upsert_elements


def test_export_powermodels_case_writes_json(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "hong_kong_16h_model.json"
    _seed_grid(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
    )

    assert result["validation"]["status"] == "warning"
    assert result["validation"]["warnings"][0]["code"] == "hk_electric_observed_total_mismatch"
    assert result["validation"]["warnings"][-1]["code"] == "clp_inferred_from_territory_total"
    assert result["metadata"]["branch_count"] == 1
    assert result["metadata"]["inferred_transformer_branch_count"] == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["baseMVA"] == 100.0
    assert payload["_metadata"]["total_pd_mw"] == 7385.731
    assert payload["_metadata"]["provenance_summary"]["load"] == {
        "inferred_clp_from_hk_total_minus_hk_electric": 8
    }


def test_export_hk_electric_load_allocation_writes_provenance_artifact(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "load_allocation" / "hk_electric_loads.json"
    _seed_grid(db_path)
    _seed_hk_electric_bus(db_path)

    result = export_hk_electric_load_allocation(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
    )

    assert result["load_count"] == 23
    assert result["total_source_energy_gwh"] == 45527.223
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "tiangou.load_allocation.v2"
    assert payload["metadata"]["service_territories"] == ["clp", "hk-electric"]
    assert payload["metadata"]["calibration"]["observed_hk_electric_total_gwh"] == 10047.0
    assert payload["metadata"]["calibration"]["inferred_clp_total_gwh"] == 35480.223
    assert payload["metadata"]["total_pd_mw"] == 9492.178
    assert len(payload["loads"]) == 23
    assert {
        "bus_id",
        "district",
        "sector",
        "snapshot",
        "pd_mw",
        "qd_mvar",
        "source_file",
        "source_year",
        "source_period",
        "provenance",
        "allocation_rule",
    } <= set(payload["loads"][0])
    assert {load["provenance"] for load in payload["loads"]} == {
        "observed_hk_electric_public_consumption",
        "inferred_clp_from_hk_total_minus_hk_electric",
    }


def test_export_topology_diagnostics_writes_json_artifact(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "diagnostics" / "hong_kong_topology_diagnostics.json"
    _seed_grid(db_path)
    _seed_hk_electric_bus(db_path)

    result = export_topology_diagnostics(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
        include_hk_interties=True,
        hk_intertie_derate=0.5,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["summary"]["synthetic_branch_count"] == 1
    assert payload["summary"]["synthetic_branch_count"] == 1
    assert payload["summary"]["missing_provenance_count"] == 0
    assert payload["synthetic_branches"][0]["provenance"] == "public_interconnection_capacity_equivalent"
    assert payload["synthetic_branches"][0]["recommended_action"] == "keep as documented equivalent"
    assert payload["recommended_next_fixes"]


def test_export_powermodels_case_writes_overnight_snapshot(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "hong_kong_04h_model.json"
    _seed_grid(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
        demand_snapshot="overnight_04h",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["demand_snapshot"] == "overnight_04h"
    assert payload["demand_snapshot"] == "overnight_04h"
    assert payload["_metadata"]["total_pd_mw"] == 3286.639
    assert payload["_metadata"]["total_equivalent_pmax_mw"] == 9657.545


def test_export_powermodels_case_applies_min_voltage_filter(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "filtered.json"
    _seed_grid(db_path)
    _seed_low_voltage_asset(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
        min_voltage_kv=100.0,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["min_voltage_kv"] == 100.0
    assert payload["_metadata"]["min_voltage_kv"] == 100.0
    assert payload["_metadata"]["branch_count"] == 1


def test_export_hong_kong_phase1_bundle_writes_peak_offpeak_and_manifest(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_dir = tmp_path / "processed"
    _seed_grid(db_path)
    _seed_hk_electric_bus(db_path)

    result = export_hong_kong_phase1_bundle(
        database_path=db_path,
        output_dir=output_dir,
        snap_tolerance_km=0.2,
        include_hk_interties=True,
        hk_intertie_derate=0.5,
        n_per_mode=3,
    )

    peak_path = output_dir / "hong_kong_16h_model.json"
    overnight_path = output_dir / "hong_kong_04h_model.json"
    manifest_path = output_dir / "hong_kong_phase1_manifest.json"
    handoff_path = output_dir / "run_hong_kong_solver_pipeline.ps1"
    grids_solvable_path = output_dir / "grids_solvable.txt"
    assert peak_path.exists()
    assert overnight_path.exists()
    assert manifest_path.exists()
    assert handoff_path.exists()
    assert grids_solvable_path.exists()
    assert result["include_hk_interties"] is True
    assert result["hk_intertie_derate"] == 0.5
    assert result["intertie_derate_scenarios"] == [0.5]
    assert result["demand_snapshots"] == ["peak_16h", "overnight_04h"]
    assert result["n_per_mode"] == 3
    assert len(result["exports"]) == 2

    peak = json.loads(peak_path.read_text(encoding="utf-8"))
    overnight = json.loads(overnight_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert peak["demand_snapshot"] == "peak_16h"
    assert overnight["demand_snapshot"] == "overnight_04h"
    assert peak["_metadata"]["include_hk_interties"] is True
    assert peak["_metadata"]["hk_intertie_derate"] == 0.5
    handoff_script = handoff_path.read_text(encoding="utf-8")
    assert "Get-Command julia" in handoff_script
    assert "julia --version" in handoff_script
    assert "Julia is on PATH but is not runnable" in handoff_script
    assert "Test-Path $ScriptPath" in handoff_script
    assert "solve_topo_json.jl" in handoff_script
    assert "export_gridsfm_data.jl" in handoff_script
    assert "solve_pyg_json.jl" in handoff_script
    assert "gen_perturbed_data.jl" in handoff_script
    assert "Solver did not produce solvable file" in handoff_script
    assert "GridSFM exporter did not produce PyG file" in handoff_script
    assert "Scenario generator did not produce output directory" in handoff_script
    assert grids_solvable_path.read_text(encoding="utf-8").splitlines() == [
        f"{output_dir / 'hong_kong_16h_model.solvable.json'} 3",
        f"{output_dir / 'hong_kong_04h_model.solvable.json'} 3",
    ]
    assert manifest["solver_handoff"]["script_path"] == str(handoff_path)
    assert manifest["solver_handoff"]["default_solver_pipeline"] == "..\\GridSFM\\power_grid\\US\\topology_solver_pipeline"
    assert manifest["solver_handoff"]["required_solver_scripts"] == [
        "solve_topo_json.jl",
        "export_gridsfm_data.jl",
        "solve_pyg_json.jl",
        "gen_perturbed_data.jl",
    ]
    assert manifest["solver_handoff"]["grids_solvable_path"] == str(grids_solvable_path)
    assert manifest["solver_handoff"]["n_per_mode"] == 3
    assert manifest["exports"][0]["validation"]["status"] == "warning"
    assert manifest["exports"][0]["validation"]["warnings"][0]["code"] == "clp_inferred_from_territory_total"


def test_export_hong_kong_phase1_bundle_writes_intertie_derate_stress_cases(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_dir = tmp_path / "processed"
    _seed_grid(db_path)
    _seed_hk_electric_bus(db_path)

    result = export_hong_kong_phase1_bundle(
        database_path=db_path,
        output_dir=output_dir,
        snap_tolerance_km=0.2,
        include_hk_interties=True,
        intertie_derate_scenarios=(1.0, 0.5),
        allow_validation_errors=False,
    )

    expected_files = [
        output_dir / "hong_kong_16h_intertie_100_model.json",
        output_dir / "hong_kong_04h_intertie_100_model.json",
        output_dir / "hong_kong_16h_intertie_050_model.json",
        output_dir / "hong_kong_04h_intertie_050_model.json",
    ]
    assert [Path(export["output_path"]) for export in result["exports"]] == expected_files
    assert all(path.exists() for path in expected_files)
    assert result["intertie_derate_scenarios"] == [1.0, 0.5]

    base_case = json.loads(expected_files[0].read_text(encoding="utf-8"))
    stress_case = json.loads(expected_files[2].read_text(encoding="utf-8"))
    base_intertie = next(branch for branch in base_case["branch"].values() if branch["source_id"] == "synthetic:intertie:clp-hk-electric")
    stress_intertie = next(branch for branch in stress_case["branch"].values() if branch["source_id"] == "synthetic:intertie:clp-hk-electric")
    assert base_intertie["rate_a"] == 720.0
    assert stress_intertie["rate_a"] == 360.0
    assert (output_dir / "grids_solvable.txt").read_text(encoding="utf-8").splitlines() == [
        f"{path.with_suffix('').with_suffix('.solvable.json')} 1"
        for path in expected_files
    ]


def test_export_hong_kong_phase1_bundle_can_select_demand_snapshots(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_dir = tmp_path / "processed"
    _seed_grid(db_path)

    result = export_hong_kong_phase1_bundle(
        database_path=db_path,
        output_dir=output_dir,
        snap_tolerance_km=0.2,
        demand_snapshots=("peak_16h", "shoulder_10h", "cooling_peak_18h"),
        allow_validation_errors=False,
    )

    expected_files = [
        output_dir / "hong_kong_16h_model.json",
        output_dir / "hong_kong_10h_shoulder_model.json",
        output_dir / "hong_kong_18h_cooling_model.json",
    ]
    assert [Path(export["output_path"]) for export in result["exports"]] == expected_files
    assert result["demand_snapshots"] == ["peak_16h", "shoulder_10h", "cooling_peak_18h"]
    cooling_case = json.loads(expected_files[2].read_text(encoding="utf-8"))
    assert cooling_case["demand_snapshot"] == "cooling_peak_18h"
    assert cooling_case["_metadata"]["total_pd_mw"] == 8772.81


def test_export_hong_kong_phase1_bundle_rejects_invalid_scenario_count(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    init_db(db_path)

    with pytest.raises(ValueError, match="n_per_mode"):
        export_hong_kong_phase1_bundle(
            database_path=db_path,
            output_dir=tmp_path / "processed",
            n_per_mode=0,
            allow_validation_errors=True,
        )


def test_export_hong_kong_phase1_bundle_rejects_invalid_intertie_derate_scenario(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    init_db(db_path)

    with pytest.raises(ValueError, match="Intertie derate scenarios"):
        export_hong_kong_phase1_bundle(
            database_path=db_path,
            output_dir=tmp_path / "processed",
            intertie_derate_scenarios=(1.0, 0.0),
            allow_validation_errors=True,
        )


def test_export_hong_kong_phase1_bundle_rejects_invalid_demand_snapshot(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    init_db(db_path)

    with pytest.raises(ValueError, match="Unknown bundle demand snapshot"):
        export_hong_kong_phase1_bundle(
            database_path=db_path,
            output_dir=tmp_path / "processed",
            demand_snapshots=("peak_16h", "bad"),
            allow_validation_errors=True,
        )


def test_export_powermodels_case_blocks_validation_errors(tmp_path) -> None:
    db_path = tmp_path / "empty.sqlite3"
    output_path = tmp_path / "empty.json"
    init_db(db_path)

    with pytest.raises(ValueError, match="no_buses"):
        export_powermodels_case(database_path=db_path, output_path=output_path)

    assert not output_path.exists()


def test_export_powermodels_case_can_write_with_validation_errors(tmp_path) -> None:
    db_path = tmp_path / "empty.sqlite3"
    output_path = tmp_path / "empty.json"
    init_db(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        allow_validation_errors=True,
    )

    assert result["validation"]["status"] == "error"
    assert output_path.exists()


def _seed_grid(db_path) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        run_id = create_ingest_run(conn, "hong-kong", "query")
        upsert_elements(
            conn,
            region_key="hong-kong",
            ingest_run_id=run_id,
            elements=[
                {
                    "type": "node",
                    "id": 1,
                    "lat": 22.30,
                    "lon": 114.10,
                    "tags": {
                        "power": "substation",
                        "name": "CLP Alpha",
                        "operator": "CLP Power",
                        "voltage": "400000",
                    },
                },
                {
                    "type": "node",
                    "id": 2,
                    "lat": 22.31,
                    "lon": 114.11,
                    "tags": {
                        "power": "substation",
                        "name": "CLP Beta",
                        "operator": "CLP Power",
                        "voltage": "132000",
                    },
                },
                {
                    "type": "way",
                    "id": 10,
                    "tags": {
                        "power": "line",
                        "name": "Alpha Beta",
                        "operator": "CLP Power",
                        "voltage": "400000",
                    },
                    "geometry": [
                        {"lat": 22.3001, "lon": 114.1001},
                        {"lat": 22.3101, "lon": 114.1101},
                    ],
                },
            ],
        )


def _seed_hk_electric_bus(db_path) -> None:
    with connect(db_path) as conn:
        run_id = create_ingest_run(conn, "hong-kong", "query")
        upsert_elements(
            conn,
            region_key="hong-kong",
            ingest_run_id=run_id,
            elements=[
                {
                    "type": "node",
                    "id": 3,
                    "lat": 22.27,
                    "lon": 114.15,
                    "tags": {
                        "power": "substation",
                        "name": "HK Electric Island",
                        "operator": "HK Electric",
                        "voltage": "275000",
                    },
                },
            ],
        )


def _seed_low_voltage_asset(db_path) -> None:
    with connect(db_path) as conn:
        run_id = create_ingest_run(conn, "hong-kong", "query")
        upsert_elements(
            conn,
            region_key="hong-kong",
            ingest_run_id=run_id,
            elements=[
                {
                    "type": "node",
                    "id": 4,
                    "lat": 22.35,
                    "lon": 114.16,
                    "tags": {
                        "power": "substation",
                        "name": "CLP 11kV",
                        "operator": "CLP Power",
                        "voltage": "11000",
                    },
                },
                {
                    "type": "way",
                    "id": 11,
                    "tags": {
                        "power": "minor_line",
                        "name": "CLP 11kV Spur",
                        "operator": "CLP Power",
                        "voltage": "11000",
                    },
                    "geometry": [
                        {"lat": 22.35, "lon": 114.16},
                        {"lat": 22.36, "lon": 114.17},
                    ],
                },
            ],
        )
