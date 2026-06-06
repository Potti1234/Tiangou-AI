import json
import os

from app.verify_gridsfm_handoff import verify_handoff_artifacts


def test_verify_handoff_artifacts_reports_complete_bundle(tmp_path) -> None:
    raw_path = tmp_path / "hong_kong_16h_model.json"
    solver_path = tmp_path / "hong_kong_16h_model.solver_sanitized.json"
    solvable_path = tmp_path / "hong_kong_16h_model.solver_sanitized.solvable.json"
    pyg_path = tmp_path / "hong_kong_16h_model.solver_sanitized.pyg.json"
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    for path in [raw_path, solver_path, solvable_path, pyg_path, *(scenario_dir / f"scenario_{index}.json" for index in range(6))]:
        path.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "exports": [{"output_path": str(raw_path)}],
                "raw_demo_exports": [{"output_path": str(raw_path)}],
                "solver_exports": [{"output_path": str(solver_path)}],
                "solver_handoff": {"n_per_mode": 1},
            }
        ),
        encoding="utf-8",
    )

    result = verify_handoff_artifacts(manifest_path)

    assert result["status"] == "ok"
    assert result["metrics"]["raw_demo_export_count"] == 1
    assert result["metrics"]["solver_export_count"] == 1
    assert result["metrics"]["raw_count"] == 1
    assert result["metrics"]["solvable_count"] == 1
    assert result["metrics"]["pyg_count"] == 1
    assert result["metrics"]["scenario_json_count"] == 6
    assert result["errors"] == []


def test_verify_handoff_artifacts_reports_missing_outputs(tmp_path) -> None:
    raw_path = tmp_path / "hong_kong_16h_model.json"
    raw_path.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "exports": [{"output_path": str(raw_path)}],
                "solver_handoff": {"n_per_mode": 1},
            }
        ),
        encoding="utf-8",
    )

    result = verify_handoff_artifacts(manifest_path)

    assert result["status"] == "error"
    assert {error["code"] for error in result["errors"]} == {
        "missing_solvable_artifact",
        "missing_pyg_artifact",
        "scenario_artifact_shortfall",
    }


def test_verify_handoff_artifacts_reports_stale_solver_outputs(tmp_path) -> None:
    raw_path = tmp_path / "hong_kong_16h_model.json"
    solvable_path = tmp_path / "hong_kong_16h_model.solvable.json"
    pyg_path = tmp_path / "hong_kong_16h_model.pyg.json"
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    scenario_files = [scenario_dir / f"scenario_{index}.json" for index in range(6)]
    for path in [raw_path, solvable_path, pyg_path, *scenario_files]:
        path.write_text("{}", encoding="utf-8")
    old_time = 1_700_000_000
    new_time = 1_700_001_000
    for path in [solvable_path, pyg_path, *scenario_files]:
        os.utime(path, (old_time, old_time))
    os.utime(raw_path, (new_time, new_time))
    manifest_path = tmp_path / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "exports": [{"output_path": str(raw_path)}],
                "solver_handoff": {"n_per_mode": 1},
            }
        ),
        encoding="utf-8",
    )

    result = verify_handoff_artifacts(manifest_path)

    assert result["status"] == "error"
    assert {error["code"] for error in result["errors"]} == {
        "stale_solvable_artifact",
        "stale_pyg_artifact",
        "stale_scenario_artifacts",
    }
    assert result["metrics"]["fresh_solvable_count"] == 0
    assert result["metrics"]["fresh_pyg_count"] == 0
    assert result["metrics"]["stale_scenario_json_count"] == 6
