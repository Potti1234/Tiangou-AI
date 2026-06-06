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
    allow_validation_errors: bool = False,
) -> dict[str, Any]:
    with connect(database_path) as conn:
        rows = list_elements(conn, region_key=region_key, limit=100000)

    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
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
        "validation": validation,
        "metadata": case["_metadata"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an ingested OSM region as a PowerModels preview JSON.")
    parser.add_argument("output_path", type=Path, help="Path for the generated PowerModels JSON.")
    parser.add_argument("--database-path", type=Path, default=Path("data/tiangou.sqlite3"))
    parser.add_argument("--region-key", default="hong-kong")
    parser.add_argument("--snap-tolerance-km", type=float, default=0.75)
    parser.add_argument("--demand-snapshot", choices=sorted(DEMAND_SNAPSHOTS), default="peak_16h")
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
    args = parser.parse_args()

    result = export_powermodels_case(
        database_path=args.database_path,
        output_path=args.output_path,
        region_key=args.region_key,
        snap_tolerance_km=args.snap_tolerance_km,
        demand_snapshot=args.demand_snapshot,
        include_hk_interties=args.include_hk_interties,
        allow_validation_errors=args.allow_validation_errors,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
