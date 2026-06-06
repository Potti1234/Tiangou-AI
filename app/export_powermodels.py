import argparse
import json
from pathlib import Path
from typing import Any

from app.database import connect
from app.repository import list_elements
from app.topology import DEMAND_SNAPSHOTS, build_powermodels_preview, validate_powermodels_case


def export_powermodels_case(
    *,
    database_path: Path,
    output_path: Path,
    region_key: str = "hong-kong",
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
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
    allow_validation_errors: bool = False,
) -> dict[str, Any]:
    exports = []
    for demand_snapshot, filename in (
        ("peak_16h", "hong_kong_16h_model.json"),
        ("overnight_04h", "hong_kong_04h_model.json"),
    ):
        exports.append(
            export_powermodels_case(
                database_path=database_path,
                output_path=output_dir / filename,
                region_key="hong-kong",
                snap_tolerance_km=snap_tolerance_km,
                demand_snapshot=demand_snapshot,
                include_hk_interties=include_hk_interties,
                hk_intertie_derate=hk_intertie_derate,
                allow_validation_errors=allow_validation_errors,
            )
        )

    manifest = {
        "region_key": "hong-kong",
        "include_hk_interties": include_hk_interties,
        "hk_intertie_derate": hk_intertie_derate,
        "exports": exports,
    }
    manifest_path = output_dir / "hong_kong_phase1_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an ingested OSM region as a PowerModels preview JSON.")
    parser.add_argument("output_path", type=Path, help="Path for the generated PowerModels JSON, or an output directory with --hong-kong-phase1-bundle.")
    parser.add_argument("--database-path", type=Path, default=Path("data/tiangou.sqlite3"))
    parser.add_argument("--region-key", default="hong-kong")
    parser.add_argument("--snap-tolerance-km", type=float, default=0.75)
    parser.add_argument("--demand-snapshot", choices=sorted(DEMAND_SNAPSHOTS), default="peak_16h")
    parser.add_argument("--hk-intertie-derate", type=float, default=1.0)
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
            allow_validation_errors=args.allow_validation_errors,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
