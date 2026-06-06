import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import get_db, init_db
from app.overpass import OverpassClient, OverpassError, build_power_query
from app.regions import REGIONS, get_region
from app.repository import (
    complete_ingest_run,
    create_ingest_run,
    get_element,
    list_elements,
    summarize,
    upsert_elements,
)
from app.topology import (
    DEMAND_SNAPSHOTS,
    build_powermodels_preview,
    build_powermodels_validation,
    build_topology_preview,
)


DEMAND_SNAPSHOT_PATTERN = f"^({'|'.join(sorted(DEMAND_SNAPSHOTS))})$"


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
