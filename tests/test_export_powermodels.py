import json

import pytest

from app.database import connect, init_db
from app.export_powermodels import export_hong_kong_phase1_bundle, export_powermodels_case
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

    assert result["validation"]["status"] == "ok"
    assert result["metadata"]["branch_count"] == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["baseMVA"] == 100.0
    assert payload["_metadata"]["total_pd_mw"] == 7336.0


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
    assert payload["_metadata"]["total_pd_mw"] == 4034.8
    assert payload["_metadata"]["total_equivalent_pmax_mw"] == 9170.0


def test_export_hong_kong_phase1_bundle_writes_peak_offpeak_and_manifest(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_dir = tmp_path / "processed"
    _seed_grid(db_path)

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
    assert manifest["exports"][0]["validation"]["status"] == "ok"


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
