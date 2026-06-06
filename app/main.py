import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.data_sources import load_calibration_bundle
from app.database import get_db, init_db
from app.overpass import OverpassClient, OverpassError, build_power_query
from app.regions import REGIONS, get_region
from app.repository import (
    complete_ingest_run,
    create_ingest_run,
    get_element,
    latest_ingest_run,
    list_elements,
    summarize,
    upsert_elements,
)
from app.topology import (
    DEMAND_SNAPSHOTS,
    build_powermodels_preview,
    build_powermodels_validation,
    build_topology_diagnostics,
    build_topology_preview,
    validate_powermodels_case,
)


DEMAND_SNAPSHOT_PATTERN = f"^({'|'.join(sorted(DEMAND_SNAPSHOTS))})$"
HANDOFF_ARTIFACT_PATHS = {
    "raw_json": "data/processed/hong_kong_16h_model.json",
    "solvable_json": "data/processed/hong_kong_16h_model.solvable.json",
    "pyg_json": "data/processed/hong_kong_16h_model.pyg.json",
    "scenarios": "data/processed/scenarios",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Tiangou AI Grid Backend",
    description="OpenStreetMap electricity grid ingestion and exploration API for Hong Kong and the Greater Bay Area.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _asset_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    tags_json = data.pop("tags_json", None)
    geometry_json = data.pop("geometry_json", None)
    data["tags"] = json.loads(tags_json) if tags_json else {}
    data["geometry"] = json.loads(geometry_json) if geometry_json else None
    return data


def _element_detail(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json"))
    geometry_json = data.pop("geometry_json")
    data["geometry"] = json.loads(geometry_json) if geometry_json else None
    return data


def _handoff_artifact_summary() -> dict[str, Any]:
    exists = {name: Path(path).exists() for name, path in HANDOFF_ARTIFACT_PATHS.items()}
    present_count = sum(1 for value in exists.values() if value)
    status = "complete" if present_count == len(exists) else "warning" if present_count else "not_run"
    return {
        "status": status,
        "paths": HANDOFF_ARTIFACT_PATHS,
        "exists": exists,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/calibration/summary")
def calibration_summary(year: int | None = None) -> dict[str, Any]:
    try:
        return load_calibration_bundle(Path("data/raw"), year=year).to_dict()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/regions")
def regions() -> list[dict[str, Any]]:
    return [
        {"key": region.key, "label": region.label, "area_names": region.area_names}
        for region in REGIONS.values()
    ]


@app.get("/overpass-query/{region_key}")
def overpass_query(region_key: str) -> dict[str, str]:
    try:
        region = get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"region_key": region.key, "query": build_power_query(region)}


@app.post("/ingest/{region_key}")
async def ingest(region_key: str) -> dict[str, Any]:
    try:
        region = get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    query = build_power_query(region)
    with get_db() as conn:
        ingest_run_id = create_ingest_run(conn, region.key, query)

    try:
        payload = await OverpassClient().fetch(query)
    except OverpassError as exc:
        with get_db() as conn:
            complete_ingest_run(conn, ingest_run_id, "failed", 0, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        with get_db() as conn:
            complete_ingest_run(conn, ingest_run_id, "failed", 0, str(exc))
        raise HTTPException(status_code=502, detail=f"Overpass network failed: {exc}") from exc

    elements = payload.get("elements", [])
    with get_db() as conn:
        stored_count = upsert_elements(
            conn,
            region_key=region.key,
            ingest_run_id=ingest_run_id,
            elements=elements,
        )
        complete_ingest_run(conn, ingest_run_id, "completed", stored_count)

    return {
        "ingest_run_id": ingest_run_id,
        "region_key": region.key,
        "fetched_count": len(elements),
        "stored_count": stored_count,
    }


@app.get("/grid/assets")
def assets(
    region_key: str | None = None,
    power: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    if region_key is not None:
        try:
            get_region(region_key)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        return [
            _asset_row(row)
            for row in list_elements(
                conn,
                region_key=region_key,
                power=power,
                limit=limit,
                offset=offset,
            )
        ]


@app.get("/grid/assets/{osm_type}/{osm_id}")
def asset_detail(osm_type: str, osm_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = get_element(conn, osm_type=osm_type, osm_id=osm_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _element_detail(row)


@app.get("/grid/summary")
def grid_summary() -> list[dict[str, Any]]:
    with get_db() as conn:
        return [_row_dict(row) for row in summarize(conn)]


@app.get("/grid/topology/preview")
def topology_preview(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        rows = list_elements(
            conn,
            region_key=region_key,
            limit=100000,
        )
    return build_topology_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )


@app.get("/grid/topology/powermodels-preview")
def powermodels_preview(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        rows = list_elements(
            conn,
            region_key=region_key,
            limit=100000,
        )
    return build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )


@app.get("/grid/topology/validation")
def topology_validation(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        rows = list_elements(
            conn,
            region_key=region_key,
            limit=100000,
        )
    return build_powermodels_validation(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )


@app.get("/topology/diagnostics")
def topology_diagnostics(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        rows = list_elements(
            conn,
            region_key=region_key,
            limit=100000,
        )
    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )
    return build_topology_diagnostics(case)


@app.get("/grid/topology/pipeline-summary")
def topology_pipeline_summary(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=100.0, gt=0.0),
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        rows = list_elements(
            conn,
            region_key=region_key,
            limit=100000,
        )
        latest_ingest = latest_ingest_run(conn, region_key)

    topology = build_topology_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )
    case = build_powermodels_preview(
        rows,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
    )
    validation = validate_powermodels_case(case)
    diagnostics = build_topology_diagnostics(case)

    raw_counts = {}
    for row in rows:
        power = row["power"]
        raw_counts[power] = raw_counts.get(power, 0) + 1

    handoff_artifacts = _handoff_artifact_summary()
    stage_status = {
        "raw_osm": "complete" if rows else "not_run",
        "reconstructed_circuits": "complete" if topology["metadata"]["branch_count"] else "warning",
        "solver_topology": "complete" if case["_metadata"]["bus_count"] else "not_run",
        "validation": validation["status"],
        "handoff_artifacts": handoff_artifacts["status"],
    }
    latest_ingest_payload = dict(latest_ingest) if latest_ingest is not None else None
    if latest_ingest_payload and latest_ingest_payload["status"] == "running":
        stage_status.update(
            {
                "raw_osm": "running",
                "reconstructed_circuits": "running",
                "solver_topology": "running",
                "validation": "running",
            }
        )
    elif latest_ingest_payload and latest_ingest_payload["status"] == "failed" and not rows:
        stage_status["raw_osm"] = "error"
    if not rows:
        stage_status["reconstructed_circuits"] = "not_run"
        stage_status["validation"] = "not_run"
        if latest_ingest_payload and latest_ingest_payload["status"] == "running":
            stage_status["reconstructed_circuits"] = "running"
            stage_status["validation"] = "running"

    return {
        "region_key": region_key,
        "parameters": {
            "snap_tolerance_km": snap_tolerance_km,
            "demand_snapshot": demand_snapshot,
            "include_hk_interties": include_hk_interties,
            "hk_intertie_derate": hk_intertie_derate,
            "min_voltage_kv": min_voltage_kv,
        },
        "stage_status": stage_status,
        "latest_ingest_run": latest_ingest_payload,
        "raw_osm_counts_by_power": dict(sorted(raw_counts.items())),
        "topology_metadata": topology["metadata"],
        "quality": topology["quality"],
        "solver_metadata": case["_metadata"],
        "validation": {
            "status": validation["status"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "metrics": validation["metrics"],
            "voltage_mismatches": validation["voltage_mismatches"],
        },
        "diagnostics": diagnostics,
        "handoff_artifacts": handoff_artifacts["paths"],
        "handoff_artifact_exists": handoff_artifacts["exists"],
    }
