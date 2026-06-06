import argparse
import json
from pathlib import Path
from typing import Any

from app.database import connect
from app.repository import list_elements
from app.topology import DEMAND_SNAPSHOTS, build_powermodels_preview, validate_powermodels_case


DEMAND_SNAPSHOT_EXPORTS = (
    ("peak_16h", "16h"),
    ("overnight_04h", "04h"),
)
DEMAND_SNAPSHOT_LABELS = {
    "peak_16h": "16h",
    "overnight_04h": "04h",
    "shoulder_10h": "10h_shoulder",
    "cooling_peak_18h": "18h_cooling",
}


def export_powermodels_case(
    *,
    database_path: Path,
    output_path: Path,
    region_key: str = "hong-kong",
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
    min_voltage_kv: float | None = None,
    allow_validation_errors: bool = False,
) -> dict[str, Any]:
    with connect(database_path) as conn:
        rows = list_elements(conn, region_key=region_key, limit=100000)

    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )
    validation = validate_powermodels_case(case)
    if validation["status"] == "error" and not allow_validation_errors:
        codes = ", ".join(error["code"] for error in validation["errors"])
        raise ValueError(f"PowerModels preview validation failed: {codes}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "output_path": str(output_path),
        "region_key": region_key,
        "demand_snapshot": demand_snapshot,
        "include_hk_interties": include_hk_interties,
        "hk_intertie_derate": hk_intertie_derate,
        "min_voltage_kv": min_voltage_kv,
        "validation": validation,
        "metadata": case["_metadata"],
    }


def export_hong_kong_phase1_bundle(
    *,
    database_path: Path,
    output_dir: Path,
    snap_tolerance_km: float = 0.75,
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
    intertie_derate_scenarios: tuple[float, ...] | None = None,
    demand_snapshots: tuple[str, ...] | None = None,
    min_voltage_kv: float | None = None,
    n_per_mode: int = 1,
    allow_validation_errors: bool = False,
) -> dict[str, Any]:
    if n_per_mode < 1:
        raise ValueError("n_per_mode must be at least 1.")

    derate_scenarios = intertie_derate_scenarios or (hk_intertie_derate,)
    for derate in derate_scenarios:
        _validate_derate_scenario(derate)
    bundle_snapshots = demand_snapshots or tuple(snapshot for snapshot, _ in DEMAND_SNAPSHOT_EXPORTS)
    for demand_snapshot in bundle_snapshots:
        _validate_bundle_snapshot(demand_snapshot)

    exports = []
    multi_derate = len(derate_scenarios) > 1
    for derate in derate_scenarios:
        for demand_snapshot in bundle_snapshots:
            exports.append(
                export_powermodels_case(
                    database_path=database_path,
                    output_path=output_dir / _bundle_filename(DEMAND_SNAPSHOT_LABELS[demand_snapshot], derate, multi_derate=multi_derate),
                    region_key="hong-kong",
                    snap_tolerance_km=snap_tolerance_km,
                    demand_snapshot=demand_snapshot,
                    include_hk_interties=include_hk_interties,
                    hk_intertie_derate=derate,
                    min_voltage_kv=min_voltage_kv,
                    allow_validation_errors=allow_validation_errors,
                )
            )

    manifest = {
        "region_key": "hong-kong",
        "include_hk_interties": include_hk_interties,
        "hk_intertie_derate": hk_intertie_derate,
        "intertie_derate_scenarios": list(derate_scenarios),
        "demand_snapshots": list(bundle_snapshots),
        "min_voltage_kv": min_voltage_kv,
        "n_per_mode": n_per_mode,
        "exports": exports,
    }
    manifest["solver_handoff"] = _write_solver_handoff(output_dir, exports, n_per_mode=n_per_mode)
    manifest_path = output_dir / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path)}


def _bundle_filename(hour_label: str, derate: float, *, multi_derate: bool) -> str:
    if not multi_derate:
        return f"hong_kong_{hour_label}_model.json"
    return f"hong_kong_{hour_label}_intertie_{_derate_label(derate)}_model.json"


def _derate_label(derate: float) -> str:
    return f"{int(round(derate * 100)):03d}"


def _validate_derate_scenario(derate: float) -> None:
    if derate <= 0 or derate > 1:
        raise ValueError("Intertie derate scenarios must be greater than 0 and less than or equal to 1.")


def _validate_bundle_snapshot(demand_snapshot: str) -> None:
    if demand_snapshot not in DEMAND_SNAPSHOT_LABELS:
        known = ", ".join(sorted(DEMAND_SNAPSHOT_LABELS))
        raise ValueError(f"Unknown bundle demand snapshot '{demand_snapshot}'. Known snapshots: {known}")


def _write_solver_handoff(
    output_dir: Path,
    exports: list[dict[str, Any]],
    *,
    n_per_mode: int,
) -> dict[str, Any]:
    required_solver_scripts = [
        "solve_topo_json.jl",
        "export_gridsfm_data.jl",
        "solve_pyg_json.jl",
        "gen_perturbed_data.jl",
    ]
    solvable_paths = [
        str(Path(export["output_path"]).with_suffix("").with_suffix(".solvable.json"))
        for export in exports
    ]
    pyg_paths = [
        str(Path(export["output_path"]).with_suffix("").with_suffix(".pyg.json"))
        for export in exports
    ]

    grids_solvable_path = output_dir / "grids_solvable.txt"
    grids_solvable_path.write_text(
        "\n".join(f"{solvable_path} {n_per_mode}" for solvable_path in solvable_paths) + "\n",
        encoding="utf-8",
    )

    script_path = output_dir / "run_hong_kong_solver_pipeline.ps1"
    lines = [
        "param(",
        '    [string]$SolverPipeline = "..\\GridSFM\\power_grid\\US\\topology_solver_pipeline"',
        ")",
        "$ErrorActionPreference = 'Stop'",
        "",
        "if (-not (Get-Command julia -ErrorAction SilentlyContinue)) {",
        "    throw 'Julia is not available on PATH. Install Julia or open a shell where julia is available before running this handoff script.'",
        "}",
        "$JuliaVersion = & julia --version 2>&1",
        "if ($LASTEXITCODE -ne 0) {",
        "    throw \"Julia is on PATH but is not runnable: $JuliaVersion\"",
        "}",
        "",
        f"$RequiredScripts = @({', '.join(repr(script) for script in required_solver_scripts)})",
        "foreach ($ScriptName in $RequiredScripts) {",
        "    $ScriptPath = Join-Path $SolverPipeline $ScriptName",
        "    if (-not (Test-Path $ScriptPath)) {",
        "        throw \"Missing solver script: $ScriptPath\"",
        "    }",
        "}",
        "",
    ]
    for export, solvable_path, pyg_path in zip(exports, solvable_paths, pyg_paths, strict=True):
        raw_path = export["output_path"]
        lines.extend(
            [
                f'if (-not (Test-Path "{raw_path}")) {{ throw "Missing raw PowerModels file: {raw_path}" }}',
                f'julia --project="$SolverPipeline" "$SolverPipeline\\solve_topo_json.jl" "{raw_path}" "{solvable_path}"',
                f'julia --project="$SolverPipeline" "$SolverPipeline\\export_gridsfm_data.jl" "{solvable_path}" "{pyg_path}"',
                f'julia --project="$SolverPipeline" "$SolverPipeline\\solve_pyg_json.jl" "{solvable_path}" "{pyg_path}"',
            ]
        )
    lines.extend(
        [
            "",
            f'julia --project="$SolverPipeline" "$SolverPipeline\\gen_perturbed_data.jl" "{grids_solvable_path}" 1 "{output_dir / "scenarios"}"',
            "",
        ]
    )
    script_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "script_path": str(script_path),
        "default_solver_pipeline": "..\\GridSFM\\power_grid\\US\\topology_solver_pipeline",
        "required_solver_scripts": required_solver_scripts,
        "grids_solvable_path": str(grids_solvable_path),
        "solvable_paths": solvable_paths,
        "pyg_paths": pyg_paths,
        "n_per_mode": n_per_mode,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an ingested OSM region as a PowerModels preview JSON.")
    parser.add_argument("output_path", type=Path, help="Path for the generated PowerModels JSON, or an output directory with --hong-kong-phase1-bundle.")
    parser.add_argument("--database-path", type=Path, default=Path("data/tiangou.sqlite3"))
    parser.add_argument("--region-key", default="hong-kong")
    parser.add_argument("--snap-tolerance-km", type=float, default=0.75)
    parser.add_argument("--demand-snapshot", choices=sorted(DEMAND_SNAPSHOTS), default="peak_16h")
    parser.add_argument("--hk-intertie-derate", type=float, default=1.0)
    parser.add_argument(
        "--min-voltage-kv",
        type=float,
        default=None,
        help="Drop known bus/branch assets below this voltage before topology export, e.g. 100 for transmission-level handoff.",
    )
    parser.add_argument(
        "--intertie-derate-scenarios",
        type=_parse_derate_scenarios,
        help="Comma-separated intertie derates for --hong-kong-phase1-bundle, for example 1.0,0.75,0.5.",
    )
    parser.add_argument(
        "--bundle-demand-snapshots",
        type=_parse_bundle_snapshots,
        help="Comma-separated demand snapshots for --hong-kong-phase1-bundle, for example peak_16h,overnight_04h,cooling_peak_18h.",
    )
    parser.add_argument("--n-per-mode", type=int, default=1)
    parser.add_argument(
        "--include-hk-interties",
        action="store_true",
        help="Add the public 720 MVA CLP-HK Electric interconnection as a synthetic branch.",
    )
    parser.add_argument(
        "--allow-validation-errors",
        action="store_true",
        help="Write the JSON even when structural validation reports errors.",
    )
    parser.add_argument(
        "--hong-kong-phase1-bundle",
        action="store_true",
        help="Write hong_kong_16h_model.json, hong_kong_04h_model.json, and a manifest into output_path.",
    )
    args = parser.parse_args()

    if args.hong_kong_phase1_bundle:
        result = export_hong_kong_phase1_bundle(
            database_path=args.database_path,
            output_dir=args.output_path,
            snap_tolerance_km=args.snap_tolerance_km,
            include_hk_interties=args.include_hk_interties,
            hk_intertie_derate=args.hk_intertie_derate,
            intertie_derate_scenarios=args.intertie_derate_scenarios,
            demand_snapshots=args.bundle_demand_snapshots,
            min_voltage_kv=args.min_voltage_kv,
            n_per_mode=args.n_per_mode,
            allow_validation_errors=args.allow_validation_errors,
        )
    else:
        result = export_powermodels_case(
            database_path=args.database_path,
            output_path=args.output_path,
            region_key=args.region_key,
            snap_tolerance_km=args.snap_tolerance_km,
            demand_snapshot=args.demand_snapshot,
            include_hk_interties=args.include_hk_interties,
            hk_intertie_derate=args.hk_intertie_derate,
            min_voltage_kv=args.min_voltage_kv,
            allow_validation_errors=args.allow_validation_errors,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_derate_scenarios(raw: str) -> tuple[float, ...]:
    try:
        derates = tuple(float(token.strip()) for token in raw.split(",") if token.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Intertie derate scenarios must be comma-separated numbers.") from exc
    if not derates:
        raise argparse.ArgumentTypeError("Provide at least one intertie derate scenario.")
    try:
        for derate in derates:
            _validate_derate_scenario(derate)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return derates


def _parse_bundle_snapshots(raw: str) -> tuple[str, ...]:
    snapshots = tuple(token.strip() for token in raw.split(",") if token.strip())
    if not snapshots:
        raise argparse.ArgumentTypeError("Provide at least one bundle demand snapshot.")
    try:
        for demand_snapshot in snapshots:
            _validate_bundle_snapshot(demand_snapshot)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return snapshots


if __name__ == "__main__":
    main()
