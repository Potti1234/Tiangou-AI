import argparse
import json
from pathlib import Path
from typing import Any


def verify_handoff_artifacts(
    manifest_path: Path,
    *,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    solver_handoff = manifest.get("solver_handoff") or {}
    exports = manifest.get("exports") or []
    output_dir = manifest_path.parent
    scenario_dir = scenario_root or output_dir / "scenarios"

    artifact_rows = []
    errors = []
    for export in exports:
        raw_path = Path(export["output_path"])
        solvable_path = Path(str(raw_path.with_suffix("").with_suffix(".solvable.json")))
        pyg_path = Path(str(raw_path.with_suffix("").with_suffix(".pyg.json")))
        row = {
            "raw_path": str(raw_path),
            "solvable_path": str(solvable_path),
            "pyg_path": str(pyg_path),
            "raw_exists": raw_path.exists(),
            "solvable_exists": solvable_path.exists(),
            "pyg_exists": pyg_path.exists(),
        }
        artifact_rows.append(row)
        for field in ("raw", "solvable", "pyg"):
            if not row[f"{field}_exists"]:
                errors.append(
                    {
                        "code": f"missing_{field}_artifact",
                        "path": row[f"{field}_path"],
                    }
                )

    scenario_files = sorted(scenario_dir.rglob("*.json")) if scenario_dir.exists() else []
    expected_scenario_count = _expected_scenario_count(solver_handoff, exports)
    if expected_scenario_count and len(scenario_files) < expected_scenario_count:
        errors.append(
            {
                "code": "scenario_artifact_shortfall",
                "expected_minimum": expected_scenario_count,
                "actual": len(scenario_files),
                "path": str(scenario_dir),
            }
        )

    return {
        "status": "error" if errors else "ok",
        "manifest_path": str(manifest_path),
        "scenario_dir": str(scenario_dir),
        "errors": errors,
        "metrics": {
            "export_count": len(exports),
            "raw_count": sum(1 for row in artifact_rows if row["raw_exists"]),
            "solvable_count": sum(1 for row in artifact_rows if row["solvable_exists"]),
            "pyg_count": sum(1 for row in artifact_rows if row["pyg_exists"]),
            "scenario_json_count": len(scenario_files),
            "expected_minimum_scenario_json_count": expected_scenario_count,
        },
        "artifacts": artifact_rows,
    }


def _expected_scenario_count(solver_handoff: dict[str, Any], exports: list[dict[str, Any]]) -> int:
    n_per_mode = int(solver_handoff.get("n_per_mode") or 0)
    if n_per_mode <= 0:
        return 0
    # gen_perturbed_data.jl currently emits base plus five perturbation modes.
    return len(exports) * n_per_mode * 6


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify generated GridSFM handoff artifacts for a Phase 1 bundle.")
    parser.add_argument("manifest_path", type=Path, help="Path to hong_kong_phase1_manifest.json.")
    parser.add_argument("--scenario-root", type=Path, default=None, help="Override the scenario output directory.")
    args = parser.parse_args()

    result = verify_handoff_artifacts(args.manifest_path, scenario_root=args.scenario_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
