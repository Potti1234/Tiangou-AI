import argparse
import json
from pathlib import Path
from typing import Any

from app.database import connect
from app.repository import list_consumer_proxy_allocation_rows, list_elements
from app.topology import DEMAND_SNAPSHOTS, build_powermodels_preview, build_topology_diagnostics


DEFAULT_OUTPUT_PATH = Path("data/processed/diagnostics/hong_kong_topology_diagnostics.json")


def export_topology_diagnostics(
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
        proxy_rows = list_consumer_proxy_allocation_rows(conn, region_key=region_key, limit=100000)

    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
        consumer_proxies=[dict(row) for row in proxy_rows],
    )
    diagnostics = build_topology_diagnostics(case)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "output_path": str(output_path),
        "region_key": region_key,
        "demand_snapshot": demand_snapshot,
        "summary": diagnostics["summary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export solver-topology diagnostics for synthetic branches and voltage mismatches.")
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--region-key", default="hong-kong")
    parser.add_argument("--snap-tolerance-km", type=float, default=0.75)
    parser.add_argument("--demand-snapshot", choices=sorted(DEMAND_SNAPSHOTS), default="peak_16h")
    parser.add_argument("--include-hk-interties", action="store_true")
    parser.add_argument("--hk-intertie-derate", type=float, default=1.0)
    parser.add_argument("--min-voltage-kv", type=float, default=None)
    args = parser.parse_args()
    result = export_topology_diagnostics(
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
