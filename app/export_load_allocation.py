import argparse
import json
from pathlib import Path
from typing import Any

from app.database import connect
from app.repository import list_elements
from app.topology import DEMAND_SNAPSHOTS, build_topology_preview


DEFAULT_OUTPUT_PATH = Path("data/processed/load_allocation/hk_electric_loads.json")


def export_hk_electric_load_allocation(
    *,
    database_path: Path,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    region_key: str = "hong-kong",
    snap_tolerance_km: float = 0.75,
    demand_snapshot: str = "peak_16h",
    include_hk_interties: bool = False,
    hk_intertie_derate: float = 1.0,
    min_voltage_kv: float | None = None,
) -> dict[str, Any]:
    with connect(database_path) as conn:
        rows = list_elements(conn, region_key=region_key, limit=100000)

    topology = build_topology_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )
    loads = [
        load
        for load in topology["loads"]
        if load.get("service_territory") == "hk-electric"
    ]
    missing_provenance = [load["id"] for load in loads if not load.get("provenance")]
    if missing_provenance:
        raise ValueError(f"HK Electric load allocation records are missing provenance: {', '.join(missing_provenance)}")

    payload = {
        "schema": "tiangou.hk_electric_load_allocation.v1",
        "region_key": region_key,
        "demand_snapshot": demand_snapshot,
        "metadata": {
            "calibration": topology["metadata"].get("calibration"),
            "calibration_warnings": topology["metadata"].get("calibration_warnings", []),
            "load_count": len(loads),
            "total_pd_mw": round(sum(float(load.get("pd_mw") or 0.0) for load in loads), 3),
            "total_source_energy_gwh": round(sum(float(load.get("source_energy_gwh") or 0.0) for load in loads), 3),
        },
        "loads": loads,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "output_path": str(output_path),
        "region_key": region_key,
        "demand_snapshot": demand_snapshot,
        "load_count": len(loads),
        "total_pd_mw": payload["metadata"]["total_pd_mw"],
        "total_source_energy_gwh": payload["metadata"]["total_source_energy_gwh"],
        "metadata": payload["metadata"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export calibrated HK Electric load allocation records.")
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--region-key", default="hong-kong")
    parser.add_argument("--snap-tolerance-km", type=float, default=0.75)
    parser.add_argument("--demand-snapshot", choices=sorted(DEMAND_SNAPSHOTS), default="peak_16h")
    parser.add_argument("--include-hk-interties", action="store_true")
    parser.add_argument("--hk-intertie-derate", type=float, default=1.0)
    parser.add_argument("--min-voltage-kv", type=float, default=None)
    args = parser.parse_args()
    result = export_hk_electric_load_allocation(
        database_path=args.database_path,
        output_path=args.output_path,
        region_key=args.region_key,
        snap_tolerance_km=args.snap_tolerance_km,
        demand_snapshot=args.demand_snapshot,
        include_hk_interties=args.include_hk_interties,
        hk_intertie_derate=args.hk_intertie_derate,
        min_voltage_kv=args.min_voltage_kv,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
