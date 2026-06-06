import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from app.gridsfm_solver_config import DEFAULT_GRIDSFM_SOLVER_DIR, REQUIRED_SOLVER_SCRIPTS


def solver_pipeline_dir() -> Path:
    return DEFAULT_GRIDSFM_SOLVER_DIR


def check_julia_available() -> dict[str, Any]:
    julia_path = shutil.which("julia")
    if not julia_path:
        return {
            "available": False,
            "path": None,
            "version": None,
            "error": "Julia is not available on PATH.",
        }

    try:
        result = subprocess.run(
            ["julia", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "available": False,
            "path": julia_path,
            "version": None,
            "error": f"Julia is on PATH but is not runnable: {exc}",
        }

    version = (result.stdout or result.stderr).strip()
    return {
        "available": result.returncode == 0,
        "path": julia_path,
        "version": version if result.returncode == 0 else None,
        "error": None if result.returncode == 0 else f"Julia is on PATH but is not runnable: {version}",
    }


def check_solver_pipeline(path: Path) -> dict[str, Any]:
    required_files = [*REQUIRED_SOLVER_SCRIPTS, "Project.toml", "Manifest.toml", "run_opf_relaxation.jl", "shared/relaxation_levels.json"]
    missing_files = [file_name for file_name in required_files if not (path / file_name).exists()]
    return {
        "available": not missing_files,
        "path": str(path),
        "required_files": required_files,
        "missing_files": missing_files,
        "julia_project_path": str(path),
    }


def instantiate_solver_env(path: Path) -> dict[str, Any]:
    preflight = _preflight(path)
    if preflight["status"] != "ok":
        return preflight
    command = [
        "julia",
        f"--project={path}",
        "-e",
        "using Pkg; Pkg.instantiate(); Pkg.precompile()",
    ]
    result = _run_command(command)
    return {
        "status": "ok" if result["returncode"] == 0 else "error",
        "command": command,
        "result": result,
    }


def build_solver_commands(manifest_path: Path, solver_dir: Path | None = None) -> list[list[str]]:
    manifest = _load_manifest(manifest_path)
    handoff = manifest.get("solver_handoff") or {}
    pipeline_dir = solver_dir or Path(handoff.get("solver_pipeline_path") or DEFAULT_GRIDSFM_SOLVER_DIR)
    grids_solvable_path = Path(handoff.get("grids_solvable_path") or manifest_path.parent / "grids_solvable.txt")
    scenarios_path = manifest_path.parent / "scenarios"

    commands: list[list[str]] = []
    exports = manifest.get("exports") or []
    for export in exports:
        raw_path = Path(export["output_path"])
        solvable_path = raw_path.with_suffix("").with_suffix(".solvable.json")
        pyg_path = raw_path.with_suffix("").with_suffix(".pyg.json")
        commands.extend(
            [
                _julia_command(pipeline_dir, "solve_topo_json.jl", raw_path, solvable_path),
                _julia_command(pipeline_dir, "export_gridsfm_data.jl", solvable_path, pyg_path),
                _julia_command(pipeline_dir, "solve_pyg_json.jl", solvable_path, pyg_path),
            ]
        )

    commands.append(_julia_command(pipeline_dir, "gen_perturbed_data.jl", grids_solvable_path, 1, scenarios_path))
    return commands


def run_solver_handoff(manifest_path: Path, solver_dir: Path | None = None) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    handoff = manifest.get("solver_handoff") or {}
    pipeline_dir = solver_dir or Path(handoff.get("solver_pipeline_path") or DEFAULT_GRIDSFM_SOLVER_DIR)
    preflight = _preflight(pipeline_dir)
    if preflight["status"] != "ok":
        return preflight

    commands = build_solver_commands(manifest_path, pipeline_dir)
    results = []
    for command in commands:
        result = _run_command(command)
        results.append(result)
        if result["returncode"] != 0:
            return {
                "status": "error",
                "solver_pipeline_path": str(pipeline_dir),
                "commands": commands,
                "results": results,
                "failed_command": command,
            }

    return {
        "status": "ok",
        "solver_pipeline_path": str(pipeline_dir),
        "commands": commands,
        "results": results,
    }


def _preflight(path: Path) -> dict[str, Any]:
    julia = check_julia_available()
    solver = check_solver_pipeline(path)
    if julia["available"] and solver["available"]:
        return {"status": "ok", "julia": julia, "solver": solver}
    return {"status": "error", "julia": julia, "solver": solver}


def _julia_command(solver_dir: Path, script_name: str, *args: object) -> list[str]:
    return [
        "julia",
        f"--project={solver_dir}",
        str(solver_dir / script_name),
        *(str(arg) for arg in args),
    ]


def _run_command(command: Sequence[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "command": list(command),
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "command": list(command),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Check or run the embedded GridSFM Julia solver pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Report Julia and embedded solver file status.")
    check_parser.add_argument("--solver-dir", type=Path, default=DEFAULT_GRIDSFM_SOLVER_DIR)

    instantiate_parser = subparsers.add_parser("instantiate", help="Instantiate and precompile the Julia solver environment.")
    instantiate_parser.add_argument("--solver-dir", type=Path, default=DEFAULT_GRIDSFM_SOLVER_DIR)

    run_parser = subparsers.add_parser("run", help="Run the solve/export/verify/scenario handoff from a manifest.")
    run_parser.add_argument("manifest_path", type=Path)
    run_parser.add_argument("--solver-dir", type=Path)

    args = parser.parse_args()
    if args.command == "check":
        result = {
            "status": "ok",
            "julia": check_julia_available(),
            "solver": check_solver_pipeline(args.solver_dir),
        }
        if not result["julia"]["available"] or not result["solver"]["available"]:
            result["status"] = "error"
    elif args.command == "instantiate":
        result = instantiate_solver_env(args.solver_dir)
    else:
        result = run_solver_handoff(args.manifest_path, args.solver_dir)

    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()

