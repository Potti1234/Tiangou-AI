import json
from pathlib import Path

from app import gridsfm_solver
from app.gridsfm_solver_config import DEFAULT_GRIDSFM_SOLVER_DIR, REQUIRED_SOLVER_SCRIPTS


def test_embedded_solver_files_exist() -> None:
    required_files = [
        "Project.toml",
        "Manifest.toml",
        "run_opf_relaxation.jl",
        "shared/relaxation_levels.json",
        "README.md",
        "PIPELINE_DETAILS.md",
        "LICENSE",
        "NOTICE.md",
        *REQUIRED_SOLVER_SCRIPTS,
    ]

    assert DEFAULT_GRIDSFM_SOLVER_DIR.exists()
    assert [file_name for file_name in required_files if not (DEFAULT_GRIDSFM_SOLVER_DIR / file_name).exists()] == []


def test_check_solver_pipeline_reports_missing_script(tmp_path) -> None:
    (tmp_path / "Project.toml").write_text("", encoding="utf-8")

    result = gridsfm_solver.check_solver_pipeline(tmp_path)

    assert result["available"] is False
    assert "solve_topo_json.jl" in result["missing_files"]
    assert "shared/relaxation_levels.json" in result["missing_files"]


def test_check_julia_available_reports_missing_julia(monkeypatch) -> None:
    monkeypatch.setattr(gridsfm_solver.shutil, "which", lambda _name: None)

    result = gridsfm_solver.check_julia_available()

    assert result == {
        "available": False,
        "path": None,
        "version": None,
        "error": "Julia is not available on PATH.",
    }


def test_build_solver_commands_from_manifest(tmp_path) -> None:
    raw_path = tmp_path / "hong_kong_16h_model.json"
    solver_path = tmp_path / "hong_kong_16h_model.solver_sanitized.json"
    manifest_path = tmp_path / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "exports": [{"output_path": str(raw_path)}],
                "solver_exports": [{"output_path": str(solver_path)}],
                "solver_handoff": {
                    "solver_pipeline_path": "third_party/gridsfm_solver",
                    "grids_solvable_path": str(tmp_path / "grids_solvable.txt"),
                },
            }
        ),
        encoding="utf-8",
    )

    commands = gridsfm_solver.build_solver_commands(manifest_path)

    solver_dir = Path("third_party/gridsfm_solver")
    solvable_path = tmp_path / "hong_kong_16h_model.solver_sanitized.solvable.json"
    pyg_path = tmp_path / "hong_kong_16h_model.solver_sanitized.pyg.json"
    assert commands == [
        ["julia", f"--project={solver_dir}", str(solver_dir / "solve_topo_json.jl"), str(solver_path), str(solvable_path)],
        ["julia", f"--project={solver_dir}", str(solver_dir / "export_gridsfm_data.jl"), str(solvable_path), str(pyg_path)],
        ["julia", f"--project={solver_dir}", str(solver_dir / "solve_pyg_json.jl"), str(solvable_path), str(pyg_path)],
        ["julia", f"--project={solver_dir}", str(solver_dir / "gen_perturbed_data.jl"), str(tmp_path / "grids_solvable.txt"), "1", str(tmp_path / "scenarios")],
    ]


def test_run_solver_handoff_returns_preflight_diagnostic_when_julia_missing(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"exports": []}), encoding="utf-8")
    monkeypatch.setattr(gridsfm_solver, "check_julia_available", lambda: {"available": False, "error": "missing"})
    monkeypatch.setattr(gridsfm_solver, "check_solver_pipeline", lambda _path: {"available": True, "missing_files": []})

    result = gridsfm_solver.run_solver_handoff(manifest_path)

    assert result["status"] == "error"
    assert result["julia"]["available"] is False
    assert result["solver"]["available"] is True
