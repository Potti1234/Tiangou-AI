import json

from app.verify_gridsfm_handoff import verify_handoff_artifacts


def test_verify_handoff_artifacts_reports_complete_bundle(tmp_path) -> None:
    raw_path = tmp_path / "hong_kong_16h_model.json"
    solvable_path = tmp_path / "hong_kong_16h_model.solvable.json"
    pyg_path = tmp_path / "hong_kong_16h_model.pyg.json"
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    for path in [raw_path, solvable_path, pyg_path, *(scenario_dir / f"scenario_{index}.json" for index in range(6))]:
        path.write_text("{}", encoding="utf-8")
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

    assert result["status"] == "ok"
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
