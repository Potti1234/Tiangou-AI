import json
from dataclasses import dataclass
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.assumptions.contingencies import contingency_assumption_tables
from app.assumptions.data_centers import data_center_assumption_tables, estimate_data_center_load
from app.assumptions.demand_profiles import demand_profile_assumption_tables
from app.assumptions.generators import generator_assumption_tables
from app.assumptions.imports import import_assumption_tables
from app.assumptions.lines import line_assumption_tables
from app.assumptions.transformers import transformer_assumption_tables
from app.assumptions.validation import build_assumption_validation_summary
from app.config import settings
from app.data_sources import load_calibration_bundle
from app.database import get_db, init_db
from app.dynamic.adapter import DynamicGridConfig, build_dynamic_config
from app.dynamic.dual_timeline import DualTimelineSimulation
from app.dynamic.pinn_model import load_pinn_checkpoint
from app.dynamic.scenarios import build_scenarios, scenario_by_id
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
from app.studies.baseline import build_baseline_weak_spots
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
from app.verify_gridsfm_handoff import verify_handoff_artifacts


DEMAND_SNAPSHOT_PATTERN = f"^({'|'.join(sorted(DEMAND_SNAPSHOTS))})$"
SOLVER_INCLUDE_POLICY_PATTERN = f"^({'|'.join(sorted(SOLVER_INCLUDE_POLICIES))})$"
HANDOFF_ARTIFACT_PATHS = {
    "raw_json": "data/processed/hong_kong_16h_model.json",
    "raw_demo_json": "data/processed/hong_kong_16h_model.json",
    "solver_json": "data/processed/hong_kong_16h_model.solver_sanitized.json",
    "solvable_json": "data/processed/hong_kong_16h_model.solvable.json",
    "solver_solvable_json": "data/processed/hong_kong_16h_model.solver_sanitized.solvable.json",
    "pyg_json": "data/processed/hong_kong_16h_model.pyg.json",
    "solver_pyg_json": "data/processed/hong_kong_16h_model.solver_sanitized.pyg.json",
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


class DynamicSimulateRequest(BaseModel):
    scenario: str
    duration_s: int = 400
    demand_snapshot: str = "peak_16h"
    model_mode: str = "full_demo"


_DASHBOARD_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_DASHBOARD_CACHE_LOCK = RLock()
_DYNAMIC_PINN_MODEL: Any | None = None
_DYNAMIC_PINN_STATUS: dict[str, Any] | None = None


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
    manifest_path = Path("data/processed/hong_kong_phase1_manifest.json")
    manifest: dict[str, Any] | None = None
    artifact_report: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {"status": "error", "error": "Manifest exists but could not be parsed as JSON."}
        else:
            artifact_report = verify_handoff_artifacts(manifest_path)

    paths = _handoff_paths_from_manifest(manifest) if isinstance(manifest, dict) else dict(HANDOFF_ARTIFACT_PATHS)
    exists = {name: Path(path).exists() for name, path in paths.items()}
    freshness = _handoff_freshness_from_report(artifact_report)
    raw_demo_exports = manifest.get("raw_demo_exports", []) if isinstance(manifest, dict) else []
    solver_exports = manifest.get("solver_exports", []) if isinstance(manifest, dict) else []
    raw_demo_generated = bool(raw_demo_exports) and all(Path(export.get("output_path", "")).exists() for export in raw_demo_exports if isinstance(export, dict))
    generated = {
        "raw_json": raw_demo_generated or freshness["raw_exports_fresh"],
        "raw_demo_json": raw_demo_generated,
        "solver_json": bool(solver_exports) and freshness["raw_exports_fresh"],
        "solvable_json": freshness["solvable_exports_fresh"],
        "solver_solvable_json": freshness["solvable_exports_fresh"],
        "pyg_json": freshness["pyg_exports_fresh"],
        "solver_pyg_json": freshness["pyg_exports_fresh"],
        "scenarios": freshness["scenario_artifacts_fresh"],
    }
    present_count = sum(1 for value in exists.values() if value)
    if artifact_report is not None:
        status = "complete" if artifact_report["status"] == "ok" else "warning"
    else:
        status = "warning" if present_count else "not_run"
    return {
        "status": status,
        "paths": paths,
        "exists": exists,
        "generated": generated,
        "freshness": freshness,
        "artifact_report": artifact_report,
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "manifest": manifest,
        "feasibility_warning": (
            "The refreshed 57-bus/63-branch case can export raw PowerModels, but the Julia AC relaxation may fail "
            "after DC warm-start because the synthetic/demo grid is not yet AC-feasible."
        ),
    }


def _handoff_paths_from_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    raw_exports = [export for export in manifest.get("raw_demo_exports") or manifest.get("exports") or [] if isinstance(export, dict)]
    solver_exports = [export for export in manifest.get("solver_exports") or manifest.get("exports") or [] if isinstance(export, dict)]
    raw_path = Path(raw_exports[0]["output_path"]) if raw_exports else Path(HANDOFF_ARTIFACT_PATHS["raw_json"])
    solver_path = Path(solver_exports[0]["output_path"]) if solver_exports else raw_path
    return {
        "raw_json": str(raw_path),
        "raw_demo_json": str(raw_path),
        "solver_json": str(solver_path),
        "solvable_json": str(_artifact_path(solver_path, "solvable")),
        "solver_solvable_json": str(_artifact_path(solver_path, "solvable")),
        "pyg_json": str(_artifact_path(solver_path, "pyg")),
        "solver_pyg_json": str(_artifact_path(solver_path, "pyg")),
        "scenarios": "data/processed/scenarios",
    }


def _artifact_path(raw_path: Path, kind: str) -> Path:
    return raw_path.with_name(f"{raw_path.stem}.{kind}.json")


def _handoff_freshness_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "raw_exports_fresh": False,
            "solvable_exports_fresh": False,
            "pyg_exports_fresh": False,
            "scenario_artifacts_fresh": False,
            "stale_codes": [],
            "error_codes": [],
        }
    metrics = report.get("metrics", {})
    export_count = int(metrics.get("export_count") or 0)
    expected_scenarios = int(metrics.get("expected_minimum_scenario_json_count") or 0)
    scenario_count = int(metrics.get("scenario_json_count") or 0)
    stale_scenarios = int(metrics.get("stale_scenario_json_count") or 0)
    error_codes = [str(error.get("code")) for error in report.get("errors", []) if isinstance(error, dict)]
    return {
        "raw_exports_fresh": export_count > 0 and int(metrics.get("raw_count") or 0) == export_count,
        "solvable_exports_fresh": export_count > 0 and int(metrics.get("fresh_solvable_count") or 0) == export_count,
        "pyg_exports_fresh": export_count > 0 and int(metrics.get("fresh_pyg_count") or 0) == export_count,
        "scenario_artifacts_fresh": expected_scenarios > 0 and scenario_count >= expected_scenarios and stale_scenarios == 0,
        "stale_codes": [code for code in error_codes if code.startswith("stale_")],
        "error_codes": error_codes,
    }


def _latest_manifest_export_summary(manifest: Any) -> dict[str, Any] | None:
    if not isinstance(manifest, dict):
        return None
    exports = manifest.get("exports")
    if not isinstance(exports, list) or not exports:
        return None
    latest = exports[-1]
    if not isinstance(latest, dict):
        return None
    metadata = latest.get("metadata") if isinstance(latest.get("metadata"), dict) else {}
    output_path = latest.get("output_path")
    output_exists = Path(output_path).exists() if isinstance(output_path, str) else False
    return {
        "status": "generated" if output_exists else "missing_output",
        "output_path": output_path,
        "output_exists": output_exists,
        "demand_snapshot": latest.get("demand_snapshot") or metadata.get("demand_snapshot"),
        "bus_count": metadata.get("bus_count"),
        "branch_count": metadata.get("branch_count"),
        "load_count": metadata.get("load_count"),
        "gen_count": metadata.get("gen_count"),
        "total_pd_mw": metadata.get("total_pd_mw"),
        "total_pmax_mw": metadata.get("total_pmax_mw"),
    }


def _latest_solver_export_summary(manifest: Any) -> dict[str, Any] | None:
    if not isinstance(manifest, dict):
        return None
    exports = manifest.get("solver_exports")
    if not isinstance(exports, list) or not exports:
        return None
    latest = exports[-1]
    if not isinstance(latest, dict):
        return None
    metadata = latest.get("metadata") if isinstance(latest.get("metadata"), dict) else {}
    output_path = latest.get("output_path")
    output_exists = Path(output_path).exists() if isinstance(output_path, str) else False
    return {
        "status": "generated" if output_exists else "missing_output",
        "output_path": output_path,
        "output_exists": output_exists,
        "solver_sanitized": latest.get("solver_sanitized") or metadata.get("solver_sanitized"),
        "solver_sanitization_summary": latest.get("solver_sanitization_summary") or metadata.get("solver_sanitization_summary"),
        "bus_count": metadata.get("bus_count"),
        "branch_count": metadata.get("branch_count"),
        "load_count": metadata.get("load_count"),
        "gen_count": metadata.get("gen_count"),
        "total_pd_mw": metadata.get("total_pd_mw"),
        "total_pmax_mw": metadata.get("total_pmax_mw"),
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
    baseline_weak_spots: dict[str, Any],
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
        "baseline_weak_spots": {
            "schema": baseline_weak_spots["schema"],
            "study_type": baseline_weak_spots["study_type"],
            "system_summary": baseline_weak_spots["system_summary"],
        },
        "asset_reconciliation": {
            "summary": reconciliation["summary"],
            "top_generation_assets": reconciliation["generation_assets"][:10],
            "top_linear_assets": reconciliation["linear_assets"][:10],
            "top_dropped_or_aggregated_assets": reconciliation["dropped_or_aggregated_assets"][:10],
        },
        "handoff_artifacts": handoff_artifacts["paths"],
        "handoff_artifact_exists": handoff_artifacts["exists"],
        "handoff_artifact_status": {
            "status": handoff_artifacts["status"],
            "raw_powermodels_export_generated": handoff_artifacts["generated"]["raw_json"],
            "raw_demo_powermodels_export_generated": handoff_artifacts["generated"]["raw_demo_json"],
            "solver_powermodels_export_generated": handoff_artifacts["generated"]["solver_json"],
            "gridsfm_relaxed_solvable_json_generated": handoff_artifacts["generated"]["solvable_json"],
            "pyg_export_generated": handoff_artifacts["generated"]["pyg_json"],
            "scenario_files_generated": handoff_artifacts["generated"]["scenarios"],
            "freshness": handoff_artifacts["freshness"],
            "verification": handoff_artifacts["artifact_report"],
            "manifest_path": handoff_artifacts["manifest_path"],
            "manifest_exists": handoff_artifacts["manifest_exists"],
            "manifest_export_count": len(handoff_artifacts["manifest"].get("exports", [])) if isinstance(handoff_artifacts.get("manifest"), dict) else 0,
            "manifest_raw_demo_export_count": len(handoff_artifacts["manifest"].get("raw_demo_exports", [])) if isinstance(handoff_artifacts.get("manifest"), dict) else 0,
            "manifest_solver_export_count": len(handoff_artifacts["manifest"].get("solver_exports", [])) if isinstance(handoff_artifacts.get("manifest"), dict) else 0,
            "latest_raw_powermodels_export": _latest_manifest_export_summary(handoff_artifacts.get("manifest")),
            "latest_solver_powermodels_export": _latest_solver_export_summary(handoff_artifacts.get("manifest")),
            "feasibility_warning": handoff_artifacts["feasibility_warning"],
        },
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
    baseline_weak_spots = build_baseline_weak_spots(case, validation)
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
        baseline_weak_spots=baseline_weak_spots,
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
        "baseline_weak_spots": baseline_weak_spots,
        "asset_reconciliation": reconciliation,
        "summary": summary,
    }
    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_CACHE[cache_key] = snapshot
        if len(_DASHBOARD_CACHE) > 16:
            oldest_key = next(iter(_DASHBOARD_CACHE))
            _DASHBOARD_CACHE.pop(oldest_key, None)
    return snapshot


def _dynamic_snapshot_params(demand_snapshot: str = "peak_16h", model_mode: str = "full_demo") -> DashboardSnapshotParams:
    if demand_snapshot not in DEMAND_SNAPSHOTS:
        raise HTTPException(status_code=400, detail=f"Unknown demand_snapshot '{demand_snapshot}'.")
    if model_mode not in {"full_demo", "transmission"}:
        raise HTTPException(status_code=400, detail="model_mode must be 'full_demo' or 'transmission'.")
    return DashboardSnapshotParams(
        region_key="hong-kong",
        snap_tolerance_km=0.75,
        demand_snapshot=demand_snapshot,
        include_hk_interties=True,
        hk_intertie_derate=1.0,
        min_voltage_kv=None if model_mode == "full_demo" else 100.0,
        solver_include_policy="demo_full_osm" if model_mode == "full_demo" else "strict_transmission",
        min_solver_generator_mw=DEFAULT_MIN_SOLVER_GENERATOR_MW,
        include_synthetic_generator_connections=model_mode == "full_demo",
        asset_limit=1,
    )


def _dynamic_consumer_proxies(region_key: str = "hong-kong", limit: int = 500) -> list[dict[str, Any]]:
    return _important_proxy_markers_for_analytics(region_key, limit=limit)


def _build_dynamic_grid_config(demand_snapshot: str = "peak_16h", model_mode: str = "full_demo") -> DynamicGridConfig:
    params = _dynamic_snapshot_params(demand_snapshot=demand_snapshot, model_mode=model_mode)
    snapshot = _build_dashboard_snapshot(params)
    return build_dynamic_config(
        snapshot["powermodels_case"],
        consumer_proxies=_dynamic_consumer_proxies(params.region_key, limit=500),
        demand_snapshot=demand_snapshot,
    )


def _dynamic_pinn() -> tuple[Any, dict[str, Any]]:
    global _DYNAMIC_PINN_MODEL, _DYNAMIC_PINN_STATUS
    if _DYNAMIC_PINN_MODEL is not None and _DYNAMIC_PINN_STATUS is not None:
        return _DYNAMIC_PINN_MODEL, _DYNAMIC_PINN_STATUS
    checkpoint_candidates = [Path("app/dynamic/pinn_checkpoint.pt"), Path("data/models/pinn_checkpoint.pt")]
    checkpoint_path = next((path for path in checkpoint_candidates if path.exists()), checkpoint_candidates[0])
    model, loaded, reason = load_pinn_checkpoint(str(checkpoint_path))
    param_count = sum(param.numel() for param in model.parameters()) if hasattr(model, "parameters") else 0
    _DYNAMIC_PINN_MODEL = model
    _DYNAMIC_PINN_STATUS = {
        "checkpoint_loaded": loaded,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_status": "loaded" if loaded else reason,
        "H_estimated": model.get_H_estimate(),
        "model_params": param_count,
        "startup_training": False,
        "training_data_dependency": "No API startup dependency on Spain_Blackout_28Apr2025_Dataset.xlsx.",
    }
    return model, _DYNAMIC_PINN_STATUS


def _dynamic_grid_source_payload(config: DynamicGridConfig) -> dict[str, Any]:
    return {
        "schema": "tiangou.dynamic.real_grid.v1",
        "source": "powermodels_case",
        "provenance_summary": config.provenance,
        "source_mapping": config.source_mapping,
        "synthetic_assumption_counts": {
            "ev_station_count": len(config.ev_stations),
            "data_center_count": len(config.data_centers),
            "synthetic_or_inferred_source_count": config.provenance.get("synthetic_or_inferred_source_count", 0),
        },
    }


def _chart_rows_from_counts(counts: dict[str, int | float], *, value_key: str = "value") -> list[dict[str, Any]]:
    return [
        {"label": label.replace("_", " "), "key": label, value_key: value}
        for label, value in sorted(counts.items(), key=lambda item: (-float(item[1]), item[0]))
    ]


def _provenance_class(value: str | None) -> str:
    if not value:
        return "unknown"
    if value.startswith("observed"):
        return "observed_public"
    if value.startswith("inferred"):
        return "inferred_from_public_statistics"
    if value.startswith("synthetic"):
        return "synthetic_engineering_default"
    if "synthetic" in value:
        return "synthetic_engineering_default"
    if "public" in value:
        return "observed_public"
    return "inferred_from_public_statistics"


def _add_count(counter: dict[str, int], key: Any) -> None:
    label = str(key or "unknown")
    counter[label] = counter.get(label, 0) + 1


def _add_float(counter: dict[str, float], key: Any, value: float) -> None:
    label = str(key or "unknown")
    counter[label] = round(counter.get(label, 0.0) + value, 6)


def _assumption_tables_payload() -> list[dict[str, Any]]:
    return (
        line_assumption_tables()
        + transformer_assumption_tables()
        + data_center_assumption_tables()
        + demand_profile_assumption_tables()
        + generator_assumption_tables()
        + contingency_assumption_tables()
        + import_assumption_tables()
    )


def _low_confidence_assumption_counts(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    examples: dict[str, dict[str, Any]] = {}
    for table in tables:
        category = str(table.get("category") or table.get("key") or "unknown")
        for row in table.get("rows", []):
            try:
                confidence = float(row.get("confidence", 1.0))
            except (TypeError, ValueError):
                continue
            if confidence >= 0.6:
                continue
            counts[category] = counts.get(category, 0) + 1
            examples.setdefault(
                category,
                {
                    "table": table.get("key"),
                    "confidence": confidence,
                    "assumption": row.get("assumptions") or row.get("method") or row.get("source") or "Low-confidence assumption",
                },
            )
    return [
        {"category": category, "count": count, "example": examples.get(category)}
        for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _important_proxy_markers_for_analytics(region_key: str, limit: int = 500) -> list[dict[str, Any]]:
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
        marker = {
            "id": marker_id,
            "name": proxy["name"],
            "category": reason,
            "proxy_type": proxy["proxy_type"],
            "sector": proxy["sector"],
            "weight": proxy["weight"],
            "confidence": proxy["confidence"],
        }
        if reason == "data_center":
            estimate_input = dict(proxy)
            tags_json = estimate_input.pop("tags_json", None)
            estimate_input["tags"] = json.loads(tags_json) if tags_json else {}
            marker["data_center_load_estimate"] = estimate_data_center_load(estimate_input)
        markers.append(marker)
        if len(markers) >= limit:
            break
    return markers


def _analytics_from_snapshot(
    *,
    snapshot: dict[str, Any],
    demand_snapshots: list[dict[str, Any]],
    assumption_summary: dict[str, Any],
    assumption_tables: list[dict[str, Any]],
    consumer_proxy_markers: list[dict[str, Any]],
) -> dict[str, Any]:
    case = snapshot["powermodels_case"]
    summary = snapshot["summary"]
    validation = snapshot["validation"]
    baseline = snapshot["baseline_weak_spots"]
    metadata = case.get("_metadata", {})
    loads = case.get("load", {})
    generators = case.get("gen", {})
    branches = case.get("branch", {})
    buses = case.get("bus", {})

    load_by_sector: dict[str, float] = {}
    load_by_provenance: dict[str, float] = {}
    for load in loads.values():
        mw = round(float(load.get("pd") or 0.0) * 100.0, 6)
        _add_float(load_by_sector, load.get("sector") or load.get("service_territory") or "aggregate", mw)
        _add_float(load_by_provenance, _provenance_class(load.get("provenance")), mw)

    gen_capacity: dict[tuple[str, str], float] = {}
    for gen in generators.values():
        source = str(gen.get("energy_source") or "unknown")
        resource_type = str(gen.get("resource_type") or "unknown")
        key = (source, resource_type)
        gen_capacity[key] = round(gen_capacity.get(key, 0.0) + float(gen.get("pmax") or 0.0) * 100.0, 6)

    branch_by_voltage: dict[str, dict[str, Any]] = {}
    for branch in branches.values():
        voltage = branch.get("matched_voltage_kv")
        voltage_label = f"{int(voltage)} kV" if isinstance(voltage, int | float) else "unknown"
        row = branch_by_voltage.setdefault(voltage_label, {"voltage_level": voltage_label, "branch_count": 0, "thermal_rating_mva": 0.0})
        row["branch_count"] += 1
        row["thermal_rating_mva"] = round(row["thermal_rating_mva"] + float(branch.get("rate_a") or 0.0), 6)

    branch_provenance: dict[str, int] = {}
    bus_provenance: dict[str, int] = {}
    for branch in branches.values():
        _add_count(branch_provenance, branch.get("provenance"))
    for bus in buses.values():
        _add_count(bus_provenance, bus.get("provenance"))

    proxy_counts: dict[str, int] = {}
    data_center_sites: list[dict[str, Any]] = []
    for marker in consumer_proxy_markers:
        _add_count(proxy_counts, marker.get("category"))
        estimate = marker.get("data_center_load_estimate")
        if isinstance(estimate, dict):
            data_center_sites.append(
                {
                    "id": marker["id"],
                    "name": marker.get("name") or marker["id"],
                    "estimated_facility_mw": estimate.get("estimated_facility_mw", 0),
                    "estimated_it_mw": estimate.get("estimated_it_mw", 0),
                    "provenance": estimate.get("provenance"),
                    "confidence": estimate.get("confidence"),
                }
            )

    baseline_system = baseline["system_summary"]
    reserve_margin = baseline_system.get("reserve_margin_estimate")
    return {
        "schema": "tiangou.grid.analytics_dashboard.v1",
        "region_key": summary["region_key"],
        "metadata_cards": {
            "buses": validation["metrics"]["bus_count"],
            "branches": validation["metrics"]["branch_count"],
            "loads": validation["metrics"]["load_count"],
            "generators": validation["metrics"]["gen_count"],
            "total_demand_mw": validation["metrics"]["total_pd_mw"],
            "total_pmax_mw": validation["metrics"]["total_pmax_mw"],
            "reserve_margin": reserve_margin,
            "island_count": validation["metrics"]["island_count"],
            "synthetic_branch_share": baseline_system["synthetic_branch_share"],
            "severe_voltage_mismatch_count": validation["metrics"]["severe_branch_voltage_mismatch_count"],
            "observed_inferred_synthetic_row_counts": assumption_summary["provenance_counts"],
        },
        "charts": {
            "load_by_sector": _chart_rows_from_counts(load_by_sector, value_key="mw"),
            "load_by_provenance_class": _chart_rows_from_counts(load_by_provenance, value_key="mw"),
            "generation_capacity_by_source": [
                {"energy_source": source, "resource_type": resource_type, "pmax_mw": value}
                for (source, resource_type), value in sorted(gen_capacity.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
            ],
            "branch_by_voltage_level": sorted(branch_by_voltage.values(), key=lambda row: (row["voltage_level"] == "unknown", row["voltage_level"])),
            "branch_provenance_counts": _chart_rows_from_counts(branch_provenance, value_key="count"),
            "bus_provenance_counts": _chart_rows_from_counts(bus_provenance, value_key="count"),
            "weak_spot_risk_top_branches": baseline_system["top_10_risky_branches"][:10],
            "weak_spot_risk_top_buses": baseline_system["top_10_risky_buses"][:10],
            "low_confidence_assumption_counts": _low_confidence_assumption_counts(assumption_tables)[:20],
            "consumer_proxy_counts_by_category": _chart_rows_from_counts(proxy_counts, value_key="count"),
            "data_center_estimated_mw_top_sites": sorted(data_center_sites, key=lambda item: -float(item["estimated_facility_mw"]))[:10],
            "demand_snapshots": demand_snapshots,
        },
        "transparency": {
            "provenance_classes": {
                "observed_public": "Observed from public source tables or public OSM tags.",
                "inferred_from_public_statistics": "Inferred from public statistics, geography, or allocation rules.",
                "synthetic_engineering_default": "Explainable engineering default, not utility-confirmed equipment data.",
            },
            "assumption_summary": assumption_summary,
            "lowest_confidence_assumptions": _low_confidence_assumption_counts(assumption_tables)[:10],
            "synthetic_note": "Synthetic values are explainable defaults, not utility-confirmed equipment data.",
        },
        "solver_artifacts": summary["handoff_artifact_status"],
        "model_parameters": summary["parameters"],
        "source_summary": {
            "dashboard_snapshot": "/grid/dashboard-snapshot",
            "powermodels_case": "powermodels_case",
            "baseline_weak_spots": "baseline_weak_spots",
            "validation_metrics": "validation.metrics",
            "assumptions": "/assumptions/*",
            "consumer_proxy_markers": "/grid/consumer-proxies/important",
            "demand_snapshot": metadata.get("demand_snapshot"),
        },
    }


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


@app.get("/assumptions/summary")
def assumptions_summary() -> dict[str, Any]:
    return build_assumption_validation_summary()


@app.get("/assumptions/lines")
def assumptions_lines() -> list[dict[str, Any]]:
    return line_assumption_tables()


@app.get("/assumptions/transformers")
def assumptions_transformers() -> list[dict[str, Any]]:
    return transformer_assumption_tables()


@app.get("/assumptions/data-centers")
def assumptions_data_centers() -> list[dict[str, Any]]:
    return data_center_assumption_tables()


@app.get("/assumptions/demand-profiles")
def assumptions_demand_profiles() -> list[dict[str, Any]]:
    return demand_profile_assumption_tables()


@app.get("/assumptions/generators")
def assumptions_generators() -> list[dict[str, Any]]:
    return generator_assumption_tables()


@app.get("/assumptions/contingencies")
def assumptions_contingencies() -> list[dict[str, Any]]:
    return contingency_assumption_tables()


@app.get("/assumptions/imports")
def assumptions_imports() -> list[dict[str, Any]]:
    return import_assumption_tables()


@app.get("/regions")
def regions() -> list[dict[str, Any]]:
    return [
        {"key": region.key, "label": region.label, "area_names": region.area_names}
        for region in REGIONS.values()
    ]


@app.get("/dynamic/config")
def dynamic_config(
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    model_mode: str = "full_demo",
) -> dict[str, Any]:
    config = _build_dynamic_grid_config(demand_snapshot=demand_snapshot, model_mode=model_mode)
    return {
        "grid_config": config.grid_config,
        "demand_profile_mw": config.demand_profile_mw,
        "ev_stations": config.ev_stations,
        "data_centers": config.data_centers,
        "source_mapping": config.source_mapping,
        "provenance": config.provenance,
        "grid_source": _dynamic_grid_source_payload(config),
    }


@app.get("/dynamic/scenarios")
def dynamic_scenarios(
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    model_mode: str = "full_demo",
) -> dict[str, Any]:
    config = _build_dynamic_grid_config(demand_snapshot=demand_snapshot, model_mode=model_mode)
    return {
        "scenarios": build_scenarios(config),
        "grid_source": _dynamic_grid_source_payload(config),
    }


@app.post("/dynamic/simulate")
def dynamic_simulate(req: DynamicSimulateRequest) -> dict[str, Any]:
    if req.duration_s < 1 or req.duration_s > 3600:
        raise HTTPException(status_code=400, detail="duration_s must be 1-3600")
    config = _build_dynamic_grid_config(demand_snapshot=req.demand_snapshot, model_mode=req.model_mode)
    scenario = scenario_by_id(config, req.scenario)
    if scenario is None:
        raise HTTPException(status_code=400, detail=f"Unknown dynamic scenario '{req.scenario}'.")
    if not scenario.get("available", True):
        raise HTTPException(status_code=400, detail=scenario.get("unavailable_reason", "Scenario is unavailable."))
    pinn, pinn_status = _dynamic_pinn()
    start_hour = 4 if req.demand_snapshot == "overnight_04h" else 16
    result = DualTimelineSimulation(
        pinn,
        config.grid_config,
        config.demand_profile_mw,
        config.ev_stations,
    ).run(scenario, duration_s=req.duration_s, start_hour=start_hour)
    result["scenario_payload"] = scenario
    result["grid_source"] = _dynamic_grid_source_payload(config)
    result["pinn_status"] = pinn_status
    return result


@app.get("/dynamic/pinn-status")
def dynamic_pinn_status() -> dict[str, Any]:
    _, status = _dynamic_pinn()
    return status


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
        marker = {
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
        if reason == "data_center":
            estimate_input = dict(proxy)
            tags_json = estimate_input.pop("tags_json", None)
            estimate_input["tags"] = json.loads(tags_json) if tags_json else {}
            marker["data_center_load_estimate"] = estimate_data_center_load(estimate_input)
        markers.append(marker)
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


@app.get("/studies/baseline-weak-spots")
def baseline_weak_spots(
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
    )["baseline_weak_spots"]


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


@app.get("/grid/analytics-dashboard")
def analytics_dashboard(
    region_key: str = "hong-kong",
    snap_tolerance_km: float = Query(default=0.75, ge=0.0, le=10.0),
    demand_snapshot: str = Query(default="peak_16h", pattern=DEMAND_SNAPSHOT_PATTERN),
    include_hk_interties: bool = True,
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

    base_params = DashboardSnapshotParams(
        region_key=region_key,
        snap_tolerance_km=snap_tolerance_km,
        demand_snapshot=demand_snapshot,
        include_hk_interties=include_hk_interties,
        hk_intertie_derate=hk_intertie_derate,
        min_voltage_kv=min_voltage_kv,
        solver_include_policy=solver_include_policy,
        min_solver_generator_mw=min_solver_generator_mw,
        include_synthetic_generator_connections=include_synthetic_generator_connections,
        asset_limit=1,
    )
    snapshot = _build_dashboard_snapshot(base_params)

    demand_snapshot_keys = [key for key in ("peak_16h", "overnight_04h") if key in DEMAND_SNAPSHOTS]
    if demand_snapshot not in demand_snapshot_keys:
        demand_snapshot_keys.insert(0, demand_snapshot)
    demand_snapshots: list[dict[str, Any]] = []
    for snapshot_key in demand_snapshot_keys:
        snapshot_payload = _build_dashboard_snapshot(
            DashboardSnapshotParams(
                **{**base_params.__dict__, "demand_snapshot": snapshot_key}
            )
        )
        metrics = snapshot_payload["validation"]["metrics"]
        demand_snapshots.append(
            {
                "snapshot": snapshot_key,
                "total_demand_mw": metrics["total_pd_mw"],
                "total_pmax_mw": metrics["total_pmax_mw"],
                "reserve_margin": (
                    round((metrics["total_pmax_mw"] - metrics["total_pd_mw"]) / metrics["total_pd_mw"], 6)
                    if metrics["total_pd_mw"] > 0
                    else None
                ),
            }
        )

    assumption_summary = build_assumption_validation_summary()
    assumption_tables = _assumption_tables_payload()
    consumer_proxy_markers = _important_proxy_markers_for_analytics(region_key, limit=500)
    return _analytics_from_snapshot(
        snapshot=snapshot,
        demand_snapshots=demand_snapshots,
        assumption_summary=assumption_summary,
        assumption_tables=assumption_tables,
        consumer_proxy_markers=consumer_proxy_markers,
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
