import json
from dataclasses import dataclass
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.data_sources import load_calibration_bundle
from app.database import get_db, init_db
from app.load_proxies import PROXY_GROUPS, normalize_consumer_proxy_element, rows_to_consumer_proxies
from app.overpass import OverpassClient, OverpassError, build_consumer_proxy_query, build_power_query
from app.regions import REGIONS, get_region
from app.repository import (
    complete_ingest_run,
    consumer_proxy_signature,
    create_ingest_run,
    get_element,
    latest_ingest_run,
    list_consumer_proxy_allocation_rows,
    list_consumer_proxy_elements,
    list_important_consumer_proxy_marker_rows,
    list_elements,
    summarize,
    upsert_consumer_proxy_elements,
    upsert_elements,
)
from app.topology import (
    DEFAULT_MIN_SOLVER_GENERATOR_MW,
    DEFAULT_SOLVER_INCLUDE_POLICY,
    DEMAND_SNAPSHOTS,
    SOLVER_INCLUDE_POLICIES,
    build_asset_reconciliation,
    build_powermodels_preview,
    build_powermodels_validation,
    build_topology_diagnostics,
    build_topology_preview,
    topology_preview_to_powermodels,
    validate_powermodels_case,
)


DEMAND_SNAPSHOT_PATTERN = f"^({'|'.join(sorted(DEMAND_SNAPSHOTS))})$"
SOLVER_INCLUDE_POLICY_PATTERN = f"^({'|'.join(sorted(SOLVER_INCLUDE_POLICIES))})$"
HANDOFF_ARTIFACT_PATHS = {
    "raw_json": "data/processed/hong_kong_16h_model.json",
    "solvable_json": "data/processed/hong_kong_16h_model.solvable.json",
    "pyg_json": "data/processed/hong_kong_16h_model.pyg.json",
    "scenarios": "data/processed/scenarios",
}


@dataclass(frozen=True)
class DashboardSnapshotParams:
    region_key: str
    snap_tolerance_km: float
    demand_snapshot: str
    include_hk_interties: bool
    hk_intertie_derate: float
    min_voltage_kv: float | None
    solver_include_policy: str = DEFAULT_SOLVER_INCLUDE_POLICY
    min_solver_generator_mw: float = DEFAULT_MIN_SOLVER_GENERATOR_MW
    include_synthetic_generator_connections: bool = True
    asset_limit: int = 5000


_DASHBOARD_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_DASHBOARD_CACHE_LOCK = RLock()


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


def _latest_ingest_payload(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _dashboard_cache_key(params: DashboardSnapshotParams, latest_ingest: Any, proxy_status: dict[str, Any]) -> tuple[Any, ...]:
    latest_ingest_payload = _latest_ingest_payload(latest_ingest)
    ingest_signature = None
    if latest_ingest_payload is not None:
        ingest_signature = (
            latest_ingest_payload["id"],
            latest_ingest_payload["status"],
            latest_ingest_payload["completed_at"],
        )
    return (
        str(settings.database_path),
        params.region_key,
        params.snap_tolerance_km,
        params.demand_snapshot,
        params.include_hk_interties,
        params.hk_intertie_derate,
        params.min_voltage_kv,
        params.solver_include_policy,
        params.min_solver_generator_mw,
        params.include_synthetic_generator_connections,
        params.asset_limit,
        ingest_signature,
        proxy_status["count"],
        proxy_status["latest_updated_at"],
    )


def _pipeline_summary_payload(
    *,
    params: DashboardSnapshotParams,
    rows: list[Any],
    topology: dict[str, Any],
    case: dict[str, Any],
    validation: dict[str, Any],
    diagnostics: dict[str, Any],
    reconciliation: dict[str, Any],
    latest_ingest_payload: dict[str, Any] | None,
    consumer_proxy_count: int,
    handoff_artifacts: dict[str, Any],
) -> dict[str, Any]:
    raw_counts = {}
    for row in rows:
        power = row["power"]
        raw_counts[power] = raw_counts.get(power, 0) + 1

    stage_status = {
        "raw_osm": "complete" if rows else "not_run",
        "reconstructed_circuits": "complete" if topology["metadata"]["branch_count"] else "warning",
        "solver_topology": "complete" if case["_metadata"]["bus_count"] else "not_run",
        "validation": validation["status"],
        "handoff_artifacts": handoff_artifacts["status"],
    }
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
        "region_key": params.region_key,
        "parameters": {
            "snap_tolerance_km": params.snap_tolerance_km,
            "demand_snapshot": params.demand_snapshot,
            "include_hk_interties": params.include_hk_interties,
            "hk_intertie_derate": params.hk_intertie_derate,
            "min_voltage_kv": params.min_voltage_kv,
            "solver_include_policy": params.solver_include_policy,
            "min_solver_generator_mw": params.min_solver_generator_mw,
            "include_synthetic_generator_connections": params.include_synthetic_generator_connections,
        },
        "stage_status": stage_status,
        "latest_ingest_run": latest_ingest_payload,
        "raw_osm_counts_by_power": dict(sorted(raw_counts.items())),
        "consumer_proxy_count": consumer_proxy_count,
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
        "asset_reconciliation": {
            "summary": reconciliation["summary"],
            "top_generation_assets": reconciliation["generation_assets"][:10],
            "top_linear_assets": reconciliation["linear_assets"][:10],
            "top_dropped_or_aggregated_assets": reconciliation["dropped_or_aggregated_assets"][:10],
        },
        "handoff_artifacts": handoff_artifacts["paths"],
        "handoff_artifact_exists": handoff_artifacts["exists"],
    }


def _build_dashboard_snapshot(params: DashboardSnapshotParams) -> dict[str, Any]:
    with get_db() as conn:
        latest_ingest = latest_ingest_run(conn, params.region_key)
        proxy_status = consumer_proxy_signature(conn, params.region_key)
        cache_key = _dashboard_cache_key(params, latest_ingest, proxy_status)
        with _DASHBOARD_CACHE_LOCK:
            cached = _DASHBOARD_CACHE.get(cache_key)
        if cached is not None:
            return cached

        rows = list_elements(
            conn,
            region_key=params.region_key,
            limit=100000,
        )
        proxy_rows = list_consumer_proxy_allocation_rows(conn, region_key=params.region_key, limit=100000)

    consumer_proxies_payload = [dict(row) for row in proxy_rows]
    topology = build_topology_preview(
        rows,
        snap_tolerance_km=params.snap_tolerance_km,
        demand_snapshot=params.demand_snapshot,
        include_hk_interties=params.include_hk_interties,
        hk_intertie_derate=params.hk_intertie_derate,
        min_voltage_kv=params.min_voltage_kv,
        consumer_proxies=consumer_proxies_payload,
    )
    case = topology_preview_to_powermodels(
        topology,
        solver_include_policy=params.solver_include_policy,
        min_solver_generator_mw=params.min_solver_generator_mw,
        include_synthetic_generator_connections=params.include_synthetic_generator_connections,
    )
    validation = validate_powermodels_case(case)
    diagnostics = build_topology_diagnostics(case)
    reconciliation = build_asset_reconciliation(rows, topology, case)
    handoff_artifacts = _handoff_artifact_summary()
    latest_ingest_payload = _latest_ingest_payload(latest_ingest)
    summary = _pipeline_summary_payload(
        params=params,
        rows=rows,
        topology=topology,
        case=case,
        validation=validation,
        diagnostics=diagnostics,
        reconciliation=reconciliation,
        latest_ingest_payload=latest_ingest_payload,
        consumer_proxy_count=proxy_status["count"],
        handoff_artifacts=handoff_artifacts,
    )
    snapshot = {
        "region_key": params.region_key,
        "assets": [_asset_row(row) for row in rows[: params.asset_limit]],
        "topology": topology,
        "powermodels_case": case,
        "validation": validation,
        "diagnostics": diagnostics,
        "asset_reconciliation": reconciliation,
        "summary": summary,
    }
    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_CACHE[cache_key] = snapshot
        if len(_DASHBOARD_CACHE) > 16:
            oldest_key = next(iter(_DASHBOARD_CACHE))
            _DASHBOARD_CACHE.pop(oldest_key, None)
    return snapshot


def _important_proxy_reason(proxy: dict[str, Any]) -> str | None:
    proxy_type = str(proxy.get("proxy_type") or "").lower()
    sector = str(proxy.get("sector") or "").lower()
    name = str(proxy.get("name") or "").lower()
    tags = proxy.get("tags") if isinstance(proxy.get("tags"), dict) else {}
    tag_values = " ".join(str(value).lower() for value in tags.values())
    if proxy_type in {"hospital", "charging_station", "station", "ferry_terminal", "aerodrome", "terminal"}:
        return proxy_type
    if proxy_type in {"works", "water_works", "wastewater_plant"}:
        return "industrial_infrastructure"
    if "data_center" in tag_values or "data centre" in tag_values or "data_centre" in tag_values or "data center" in name or "data centre" in name:
        return "data_center"
    if str(tags.get("telecom") or "").lower() == "data_center":
        return "data_center"
    if sector in {"industrial", "commercial"} and proxy_type in {"building", "landuse", "office", "mall"}:
        return f"large_{sector}_proxy"
    return None


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


@app.get("/overpass-query/{region_key}/consumer-proxies")
def consumer_proxy_overpass_query(region_key: str, group: str | None = None) -> dict[str, str]:
    try:
        region = get_region(region_key)
        query = build_consumer_proxy_query(region, group=group)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"region_key": region.key, "group": group or "all", "query": query}


@app.post("/ingest/hong-kong-consumer-proxies")
async def ingest_hong_kong_consumer_proxies() -> dict[str, Any]:
    return await ingest_consumer_proxies("hong-kong")


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


@app.post("/ingest/consumer-proxies/{region_key}")
async def ingest_consumer_proxies(region_key: str) -> dict[str, Any]:
    try:
        region = get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    client = OverpassClient()
    group_results = []
    total_fetched = 0
    total_stored = 0
    errors = []
    for group in PROXY_GROUPS:
        query = build_consumer_proxy_query(region, group=group)
        with get_db() as conn:
            ingest_run_id = create_ingest_run(conn, region.key, query)
        try:
            payload = await client.fetch(query)
            elements = payload.get("elements", [])
            proxies = [
                proxy
                for element in elements
                if (proxy := normalize_consumer_proxy_element(element, region_key=region.key)) is not None
            ]
            with get_db() as conn:
                stored_count = upsert_consumer_proxy_elements(conn, proxies=proxies)
                complete_ingest_run(conn, ingest_run_id, "completed", stored_count)
            total_fetched += len(elements)
            total_stored += stored_count
            group_results.append({"group": group, "ingest_run_id": ingest_run_id, "status": "completed", "fetched_count": len(elements), "stored_count": stored_count})
        except (OverpassError, httpx.HTTPError) as exc:
            error = str(exc)
            with get_db() as conn:
                complete_ingest_run(conn, ingest_run_id, "failed", 0, error)
            errors.append({"group": group, "error": error})
            group_results.append({"group": group, "ingest_run_id": ingest_run_id, "status": "failed", "fetched_count": 0, "stored_count": 0, "error": error})

    return {
        "region_key": region.key,
        "status": "partial" if errors and total_stored else "failed" if errors else "completed",
        "fetched_count": total_fetched,
        "stored_count": total_stored,
        "groups": group_results,
        "errors": errors,
    }


@app.get("/grid/assets")
def assets(
    region_key: str | None = None,
    power: str | None = None,
    limit: int = Query(default=100, ge=1, le=5000),
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


@app.get("/grid/consumer-proxies")
def consumer_proxies(
    region_key: str = "hong-kong",
    sector: str | None = None,
    limit: int = Query(default=1000, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with get_db() as conn:
        return rows_to_consumer_proxies(list_consumer_proxy_elements(conn, region_key=region_key, sector=sector, limit=limit, offset=offset))


@app.get("/grid/consumer-proxies/important")
def important_consumer_proxies(
    region_key: str = "hong-kong",
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[dict[str, Any]]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with get_db() as conn:
        rows = list_important_consumer_proxy_marker_rows(
            conn,
            region_key=region_key,
            category_limits=_important_consumer_proxy_category_limits(limit),
        )

    markers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        proxy = dict(row)
        marker_id = f"{proxy['osm_type']}:{proxy['osm_id']}:{proxy['proxy_type']}"
        if marker_id in seen:
            continue
        seen.add(marker_id)
        reason = proxy["reason"]
        if reason == "transport":
            reason = "airport" if proxy["proxy_type"] == "aerodrome" else proxy["proxy_type"]
        markers.append(
            {
                "id": marker_id,
                "name": proxy["name"],
                "proxy_type": proxy["proxy_type"],
                "sector": proxy["sector"],
                "weight": proxy["weight"],
                "confidence": proxy["confidence"],
                "lat": proxy["lat"],
                "lon": proxy["lon"],
                "reason": reason,
            }
        )
        if len(markers) >= limit:
            break
    return markers


def _important_consumer_proxy_category_limits(limit: int) -> dict[str, int]:
    caps = {
        "data_center": 100,
        "hospital": 150,
        "charging_station": 150,
        "transport": 150,
        "industrial_infrastructure": 150,
        "large_industrial_proxy": 200,
        "large_commercial_proxy": 200,
    }
    return {reason: min(cap, limit) for reason, cap in caps.items()}


@app.get("/grid/topology/preview")
def topology_preview(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
        )
    )["topology"]


@app.get("/grid/topology/powermodels-preview")
def powermodels_preview(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
        )
    )["powermodels_case"]


@app.get("/grid/topology/validation")
def topology_validation(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
        )
    )["summary"]["validation"]


@app.get("/topology/diagnostics")
def topology_diagnostics(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
        )
    )["summary"]["diagnostics"]


@app.get("/topology/asset-reconciliation")
def topology_asset_reconciliation(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=None, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
        )
    )["asset_reconciliation"]


@app.get("/grid/dashboard-snapshot")
def dashboard_snapshot(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=100.0, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
    asset_limit: int = Query(default=5000, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
            asset_limit=asset_limit,
        )
    )


@app.get("/grid/topology/pipeline-summary")
def topology_pipeline_summary(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = False,
    hk_intertie_derate: float = Query(default=1.0, gt=0.0, le=1.0),
    min_voltage_kv: float | None = Query(default=100.0, gt=0.0),
    solver_include_policy: str = Query(default=DEFAULT_SOLVER_INCLUDE_POLICY, pattern=SOLVER_INCLUDE_POLICY_PATTERN),
    min_solver_generator_mw: float = Query(default=DEFAULT_MIN_SOLVER_GENERATOR_MW, ge=0.0),
    include_synthetic_generator_connections: bool = True,
) -> dict[str, Any]:
    try:
        get_region(region_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _build_dashboard_snapshot(
        DashboardSnapshotParams(
            region_key=region_key,
            snap_tolerance_km=snap_tolerance_km,
            demand_snapshot=demand_snapshot,
            include_hk_interties=include_hk_interties,
            hk_intertie_derate=hk_intertie_derate,
            min_voltage_kv=min_voltage_kv,
            solver_include_policy=solver_include_policy,
            min_solver_generator_mw=min_solver_generator_mw,
            include_synthetic_generator_connections=include_synthetic_generator_connections,
        )
    )["summary"]
