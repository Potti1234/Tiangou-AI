import argparse
import json
from pathlib import Path
from typing import Any

from app.export_powermodels import export_powermodels_case
from app.gridsfm_case_tools import write_diagnostic_report
from app.gridsfm_solver import run_solver_handoff


EXPERIMENT_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "name": "strict_transmission_100kv",
        "solver_include_policy": "strict_transmission",
        "min_voltage_kv": 100.0,
        "include_hk_interties": False,
        "include_synthetic_generator_connections": False,
    },
    {
        "name": "strict_transmission_100kv_intertie",
        "solver_include_policy": "strict_transmission",
        "min_voltage_kv": 100.0,
        "include_hk_interties": True,
        "include_synthetic_generator_connections": False,
    },
    {
        "name": "demo_full_osm_100kv",
        "solver_include_policy": "demo_full_osm",
        "min_voltage_kv": 100.0,
        "include_hk_interties": True,
        "include_synthetic_generator_connections": True,
    },
    {
        "name": "demo_full_osm_all_voltage",
        "solver_include_policy": "demo_full_osm",
        "min_voltage_kv": None,
        "include_hk_interties": True,
        "include_synthetic_generator_connections": True,
    },
    {
        "name": "demo_full_osm_all_voltage_no_synthetic_gen_connections",
        "solver_include_policy": "demo_full_osm",
        "min_voltage_kv": None,
        "include_hk_interties": True,
        "include_synthetic_generator_connections": False,
    },
)


def run_gridsfm_export_experiments(
    *,
    database_path: Path,
    output_root: Path,
    demand_snapshot: str = "peak_16h",
    snap_tolerance_km: float = 0.75,
    min_solver_generator_mw: float = 0.5,
    n_per_mode: int = 1,
    run_solver: bool = True,
    allow_validation_errors: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in EXPERIMENT_VARIANTS:
        variant_dir = output_root / variant["name"]
        variant_dir.mkdir(parents=True, exist_ok=True)
        raw_path = variant_dir / "hong_kong_16h_model.json"
        export = export_powermodels_case(
            database_path=database_path,
            output_path=raw_path,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=bool(variant["include_hk_interties"]),
            min_voltage_kv=variant["min_voltage_kv"],
            solver_include_policy=str(variant["solver_include_policy"]),
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=bool(variant["include_synthetic_generator_connections"]),
            solver_sanitize_ac=False,
            allow_validation_errors=allow_validation_errors,
        )
        diagnostic = write_diagnostic_report(raw_path, variant_dir / "diagnostics")
        manifest_path = _write_variant_manifest(variant_dir, export, n_per_mode=n_per_mode)
        solver_result = run_solver_handoff(manifest_path) if run_solver else {"status": "skipped"}
        solver_summary = _solver_summary(raw_path, solver_result)
        result = {
            "name": variant["name"],
            "parameters": {key: value for key, value in variant.items() if key != "name"},
            "raw_path": str(raw_path),
            "manifest_path": str(manifest_path),
            "diagnostic_report_path": diagnostic["report_path"],
            "diagnostic_summary": diagnostic["summary"],
            "likely_ac_feasibility_blockers": diagnostic["likely_ac_feasibility_blockers"],
            "validation_status": export["validation"]["status"],
            "validation_error_codes": [error["code"] for error in export["validation"]["errors"]],
            "solver_status": solver_summary["status"],
            "solver_process_status": solver_result["status"],
            "solver_summary": solver_summary,
            "solver_result_path": str(variant_dir / "solver_result.json"),
        }
        (variant_dir / "solver_result.json").write_text(json.dumps(solver_result, indent=2, sort_keys=True), encoding="utf-8")
        results.append(result)

    summary = {
        "schema": "tiangou.gridsfm_export_experiments.v1",
        "demand_snapshot": demand_snapshot,
        "run_solver": run_solver,
        "variant_count": len(results),
        "variants": results,
        "status_counts": _count_solver_statuses(results),
    }
    summary_path = output_root / "experiment_manifest.json"
    summary["manifest_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def _write_variant_manifest(variant_dir: Path, export: dict[str, Any], *, n_per_mode: int) -> Path:
    raw_path = Path(export["output_path"])
    grids_solvable_path = variant_dir / "grids_solvable.txt"
    solvable_path = raw_path.with_name(f"{raw_path.stem}.solvable.json")
    grids_solvable_path.write_text(f"{solvable_path} {n_per_mode}\n", encoding="utf-8")
    manifest = {
        "exports": [export],
        "solver_exports": [export],
        "solver_handoff": {
            "n_per_mode": n_per_mode,
            "grids_solvable_path": str(grids_solvable_path),
            "solver_pipeline_path": "third_party/gridsfm_solver",
        },
    }
    manifest_path = variant_dir / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def _count_solver_statuses(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        status = str(result["solver_status"])
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _solver_summary(raw_path: Path, solver_result: dict[str, Any]) -> dict[str, Any]:
    if solver_result.get("status") == "skipped":
        return {"status": "skipped"}
    if solver_result.get("status") != "ok":
        return {
            "status": "error",
            "failed_command": solver_result.get("failed_command"),
        }
    solvable_path = raw_path.with_name(f"{raw_path.stem}.solvable.json")
    relaxation = _load_relaxation_metadata(solvable_path)
    if relaxation.get("cold_strict_verified") is True or (
        relaxation.get("solved_level") == 0 and relaxation.get("handoff_acceptance") is None
    ):
        return {
            "status": "strict_ac_solved",
            "solvable_path": str(solvable_path),
            "relaxation": relaxation,
        }
    if relaxation.get("handoff_acceptance") == "relaxed_trial_after_cold_strict_failure":
        return {
            "status": "relaxed_handoff",
            "solvable_path": str(solvable_path),
            "relaxation": relaxation,
        }
    return {
        "status": "ok_unclassified",
        "solvable_path": str(solvable_path),
        "relaxation": relaxation,
    }


def _load_relaxation_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    relaxation = payload.get("_relaxation")
    return relaxation if isinstance(relaxation, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export and optionally solve planned GridSFM bisection variants.")
    parser.add_argument("--database-path", type=Path, default=Path("data/tiangou.sqlite3"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/experiments"))
    parser.add_argument("--demand-snapshot", default="peak_16h")
    parser.add_argument("--snap-tolerance-km", type=float, default=0.75)
    parser.add_argument("--min-solver-generator-mw", type=float, default=0.5)
    parser.add_argument("--n-per-mode", type=int, default=1)
    parser.add_argument("--skip-solver", action="store_true", help="Export variants and diagnostics without running Julia GridSFM.")
    parser.add_argument("--allow-validation-errors", action="store_true")
    args = parser.parse_args()

    result = run_gridsfm_export_experiments(
        database_path=args.database_path,
        output_root=args.output_root,
        demand_snapshot=args.demand_snapshot,
        snap_tolerance_km=args.snap_tolerance_km,
        min_solver_generator_mw=args.min_solver_generator_mw,
        n_per_mode=args.n_per_mode,
        run_solver=not args.skip_solver,
        allow_validation_errors=args.allow_validation_errors,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
