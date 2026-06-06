from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.repository import create_ingest_run, list_consumer_proxy_allocation_rows, upsert_consumer_proxy_elements


def test_health_initializes_database(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert settings.database_path.exists()


def test_ingest_endpoint_stores_mocked_overpass_elements(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    async def fake_fetch(self, query: str):
        return {
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 22.31,
                    "lon": 114.17,
                    "tags": {"power": "substation", "name": "Mock Substation"},
                },
                {"type": "node", "id": 2, "tags": {"amenity": "cafe"}},
            ]
        }

    monkeypatch.setattr(main.OverpassClient, "fetch", fake_fetch)

    with TestClient(main.app) as client:
        ingest_response = client.post("/ingest/hong-kong")
        assets_response = client.get("/grid/assets", params={"region_key": "hong-kong"})
        detail_response = client.get("/grid/assets/node/1")

    assert ingest_response.status_code == 200
    assert ingest_response.json()["stored_count"] == 1
    assert assets_response.status_code == 200
    assert assets_response.json()[0]["name"] == "Mock Substation"
    assert detail_response.status_code == 200
    assert detail_response.json()["tags"]["power"] == "substation"


def test_powermodels_preview_endpoint_exports_ingested_grid(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    async def fake_fetch(self, query: str):
        return {
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 22.30,
                    "lon": 114.10,
                    "tags": {
                        "power": "substation",
                        "name": "CLP Alpha",
                        "operator": "CLP Power",
                        "voltage": "400000",
                    },
                },
                {
                    "type": "node",
                    "id": 2,
                    "lat": 22.31,
                    "lon": 114.11,
                    "tags": {
                        "power": "substation",
                        "name": "CLP Beta",
                        "operator": "CLP Power",
                        "voltage": "132000",
                    },
                },
                {
                    "type": "way",
                    "id": 10,
                    "tags": {
                        "power": "line",
                        "name": "Alpha Beta",
                        "operator": "CLP Power",
                        "voltage": "400000",
                    },
                    "geometry": [
                        {"lat": 22.3001, "lon": 114.1001},
                        {"lat": 22.3101, "lon": 114.1101},
                    ],
                },
            ]
        }

    monkeypatch.setattr(main.OverpassClient, "fetch", fake_fetch)

    with TestClient(main.app) as client:
        ingest_response = client.post("/ingest/hong-kong")
        dashboard_response = client.get(
            "/grid/dashboard-snapshot",
            params={"include_hk_interties": True, "min_voltage_kv": 100.0},
        )
        preview_response = client.get("/grid/topology/powermodels-preview")
        demo_policy_response = client.get(
            "/grid/topology/powermodels-preview",
            params={"solver_include_policy": "demo_full_osm", "min_solver_generator_mw": 0.5},
        )
        overnight_response = client.get(
            "/grid/topology/powermodels-preview",
            params={"demand_snapshot": "overnight_04h"},
        )
        cooling_response = client.get(
            "/grid/topology/powermodels-preview",
            params={"demand_snapshot": "cooling_peak_18h"},
        )
        filtered_response = client.get(
            "/grid/topology/powermodels-preview",
            params={"min_voltage_kv": 100.0},
        )
        intertie_validation_response = client.get(
            "/grid/topology/validation",
            params={"include_hk_interties": True, "hk_intertie_derate": 0.5},
        )
        validation_response = client.get("/grid/topology/validation")
        diagnostics_response = client.get(
            "/topology/diagnostics",
            params={"include_hk_interties": True, "hk_intertie_derate": 0.5},
        )
        reconciliation_response = client.get(
            "/topology/asset-reconciliation",
            params={"include_hk_interties": True, "hk_intertie_derate": 0.5},
        )
        calibration_response = client.get("/calibration/summary")
        summary_response = client.get(
            "/grid/topology/pipeline-summary",
            params={"include_hk_interties": True, "min_voltage_kv": 100.0},
        )
        baseline_response = client.get(
            "/studies/baseline-weak-spots",
            params={"include_hk_interties": True, "min_voltage_kv": 100.0},
        )
        analytics_response = client.get(
            "/grid/analytics-dashboard",
            params={"include_hk_interties": True, "min_voltage_kv": 100.0},
        )

    assert ingest_response.status_code == 200
    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert set(dashboard_payload) >= {"assets", "topology", "powermodels_case", "summary"}
    assert dashboard_payload["summary"]["stage_status"]["solver_topology"] == "complete"
    assert preview_response.status_code == 200
    assert demo_policy_response.status_code == 200
    assert overnight_response.status_code == 200
    assert cooling_response.status_code == 200
    assert filtered_response.status_code == 200
    assert intertie_validation_response.status_code == 200
    assert validation_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert reconciliation_response.status_code == 200
    assert calibration_response.status_code == 200
    assert summary_response.status_code == 200
    assert baseline_response.status_code == 200
    assert analytics_response.status_code == 200
    payload = preview_response.json()
    assert payload["baseMVA"] == 100.0
    assert demo_policy_response.json()["_metadata"]["solver_include_policy"] == "demo_full_osm"
    assert demo_policy_response.json()["_metadata"]["min_solver_generator_mw"] == 0.5
    assert payload["_metadata"]["branch_count"] == 1
    assert payload["_metadata"]["load_count"] == 8
    assert payload["_metadata"]["gen_count"] == 1
    assert payload["_metadata"]["provenance_summary"]["load"] == {
        "inferred_clp_substation_allocated": 8
    }
    assert overnight_response.json()["_metadata"]["total_pd_mw"] == 3286.639
    assert cooling_response.json()["_metadata"]["total_pd_mw"] == 8772.81
    assert filtered_response.json()["_metadata"]["min_voltage_kv"] == 100.0
    assert intertie_validation_response.json()["metrics"]["island_count"] == 1
    validation_payload = validation_response.json()
    assert validation_payload["status"] == "warning"
    assert validation_payload["warnings"][0]["code"] == "hk_electric_observed_total_mismatch"
    assert validation_payload["warnings"][-1]["code"] == "clp_inferred_from_territory_total"
    assert validation_payload["metrics"]["severe_branch_voltage_mismatch_count"] == 0
    assert validation_payload["metrics"]["low_confidence_counts"]["load"] == 0
    assert validation_payload["metrics"]["calibration"]["load_provenance_class_share"]["synthetic"] == 0.0
    diagnostics_payload = diagnostics_response.json()
    assert set(diagnostics_payload) >= {"summary", "synthetic_branches", "voltage_mismatches", "recommended_next_fixes"}
    assert diagnostics_payload["summary"]["synthetic_branch_count"] == 0
    assert diagnostics_payload["summary"]["missing_provenance_count"] == 0
    assert diagnostics_payload["summary"]["severe_voltage_mismatch_count"] == intertie_validation_response.json()["metrics"]["severe_branch_voltage_mismatch_count"]
    reconciliation_payload = reconciliation_response.json()
    assert set(reconciliation_payload) >= {"summary", "linear_assets", "generation_assets", "dropped_or_aggregated_assets"}
    assert reconciliation_payload["summary"]["raw_by_power"] == {"line": 1, "substation": 2}
    assert reconciliation_payload["summary"]["raw_linear_count"] == 1
    assert reconciliation_payload["linear_assets"][0]["status"] == "retained_solver_branch"
    calibration_payload = calibration_response.json()
    assert calibration_payload["source_year"] == 2023
    assert calibration_payload["sector_gwh"]["commercial"] == 7359.0
    assert calibration_payload["inferred_clp_total_gwh"] == 35480.223
    assert "CLP demand inferred from official Hong Kong totals" in calibration_payload["warnings"][0]
    summary_payload = summary_response.json()
    assert summary_payload["stage_status"]["raw_osm"] == "complete"
    assert summary_payload["stage_status"]["solver_topology"] == "complete"
    assert summary_payload["stage_status"]["validation"] in {"ok", "warning", "error"}
    assert summary_payload["stage_status"]["handoff_artifacts"] in {"not_run", "warning", "complete"}
    assert summary_payload["raw_osm_counts_by_power"] == {"line": 1, "substation": 2}
    assert summary_payload["topology_metadata"]["min_voltage_kv"] == 100.0
    assert set(summary_payload["topology_metadata"]["load_allocation_validation"]) >= {
        "method",
        "proxy_allocation_share",
        "fallback_allocation_share",
        "proxy_count_by_sector",
        "median_proxy_to_bus_distance_km",
        "top_buses_by_allocated_demand",
        "top_sectors_by_allocated_demand",
        "warnings",
    }
    assert summary_payload["solver_metadata"]["branch_count"] == 1
    assert summary_payload["asset_reconciliation"]["summary"]["raw_linear_count"] == 1
    assert summary_payload["validation"]["metrics"]["island_count"] == 1
    assert set(summary_payload["baseline_weak_spots"]["system_summary"]) >= {
        "total_demand_mw",
        "total_pmax_mw",
        "reserve_margin_estimate",
        "synthetic_branch_share",
        "inferred_voltage_count",
        "promoted_generator_count",
        "top_10_risky_branches",
        "top_10_risky_buses",
        "warnings",
    }
    baseline_payload = baseline_response.json()
    assert baseline_payload["schema"] == "tiangou.study.baseline_weak_spots.v1"
    assert baseline_payload["study_type"] == "heuristic_research_demo"
    assert isinstance(baseline_payload["system_summary"]["promoted_generator_count"], int)
    assert baseline_payload["system_summary"]["top_10_risky_branches"][0]["risk_score"] >= 0
    assert baseline_payload["system_summary"]["top_10_risky_branches"][0]["reasons"]
    assert baseline_payload["system_summary"]["top_10_risky_buses"][0]["risk_score"] >= 0
    assert baseline_payload["system_summary"]["top_10_risky_buses"][0]["reasons"]
    assert summary_payload["handoff_artifacts"]["pyg_json"].endswith(".pyg.json")
    assert set(summary_payload["handoff_artifact_exists"]) == {"raw_json", "solvable_json", "pyg_json", "scenarios"}
    analytics_payload = analytics_response.json()
    assert analytics_payload["schema"] == "tiangou.grid.analytics_dashboard.v1"
    assert set(analytics_payload["metadata_cards"]) >= {
        "buses",
        "branches",
        "loads",
        "generators",
        "total_demand_mw",
        "total_pmax_mw",
        "reserve_margin",
        "island_count",
        "synthetic_branch_share",
        "severe_voltage_mismatch_count",
        "observed_inferred_synthetic_row_counts",
    }
    assert analytics_payload["metadata_cards"]["buses"] == validation_payload["metrics"]["bus_count"]
    assert analytics_payload["charts"]["load_by_sector"]
    assert analytics_payload["charts"]["load_by_provenance_class"]
    assert analytics_payload["charts"]["generation_capacity_by_source"]
    assert analytics_payload["charts"]["branch_by_voltage_level"]
    assert len(analytics_payload["charts"]["weak_spot_risk_top_branches"]) <= 10
    assert len(analytics_payload["charts"]["weak_spot_risk_top_buses"]) <= 10
    assert len(analytics_payload["charts"]["low_confidence_assumption_counts"]) <= 20
    assert {"peak_16h", "overnight_04h"} <= {row["snapshot"] for row in analytics_payload["charts"]["demand_snapshots"]}
    assert analytics_payload["transparency"]["assumption_summary"]["provenance_counts"] == analytics_payload["metadata_cards"]["observed_inferred_synthetic_row_counts"]
    assert analytics_payload["solver_artifacts"]["raw_powermodels_export_generated"] in {True, False}
    assert analytics_payload["solver_artifacts"]["latest_raw_powermodels_export"] is None or set(analytics_payload["solver_artifacts"]["latest_raw_powermodels_export"]) >= {
        "status",
        "output_path",
        "output_exists",
        "demand_snapshot",
        "bus_count",
        "branch_count",
    }
    assert "57-bus/63-branch case can export raw PowerModels" in analytics_payload["solver_artifacts"]["feasibility_warning"]


def test_consumer_proxy_ingest_endpoint_stores_normalized_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    async def fake_fetch(self, query: str):
        return {
            "elements": [
                {
                    "type": "way",
                    "id": 500,
                    "center": {"lat": 22.30, "lon": 114.10},
                    "tags": {"building": "apartments", "building:levels": "30", "name": "Mock Towers"},
                    "geometry": [
                        {"lat": 22.3000, "lon": 114.1000},
                        {"lat": 22.3000, "lon": 114.1010},
                        {"lat": 22.3010, "lon": 114.1010},
                        {"lat": 22.3010, "lon": 114.1000},
                    ],
                }
            ]
        }

    monkeypatch.setattr(main.OverpassClient, "fetch", fake_fetch)

    with TestClient(main.app) as client:
        ingest_response = client.post("/ingest/hong-kong-consumer-proxies")
        proxies_response = client.get("/grid/consumer-proxies", params={"region_key": "hong-kong"})
        important_response = client.get("/grid/consumer-proxies/important", params={"region_key": "hong-kong"})

    assert ingest_response.status_code == 200
    assert ingest_response.json()["stored_count"] >= 1
    assert proxies_response.status_code == 200
    assert important_response.status_code == 200
    proxy = proxies_response.json()[0]
    assert proxy["sector"] == "residential"
    assert proxy["proxy_type"] == "building"
    assert proxy["weight"] > 0
    with main.get_db() as conn:
        allocation_row = dict(list_consumer_proxy_allocation_rows(conn, region_key="hong-kong")[0])
    assert set(allocation_row) == {"sector", "proxy_type", "weight", "confidence", "lat", "lon"}


def test_important_consumer_proxy_endpoint_prioritizes_small_important_categories(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    with TestClient(main.app) as client:
        with main.get_db() as conn:
            proxies = [
                {
                    "osm_type": "node",
                    "osm_id": 1,
                    "region_key": "hong-kong",
                    "proxy_type": "building",
                    "sector": "commercial",
                    "weight": 1_000_000.0,
                    "weight_method": "building_floor_area_proxy",
                    "confidence": 0.5,
                    "name": "Huge Generic Tower",
                    "tags": {"building": "yes"},
                    "lat": 22.30,
                    "lon": 114.10,
                },
                {
                    "osm_type": "node",
                    "osm_id": 2,
                    "region_key": "hong-kong",
                    "proxy_type": "building",
                    "sector": "commercial",
                    "weight": 5.0,
                    "weight_method": "poi_default_weight",
                    "confidence": 0.7,
                    "name": "North Data Centre",
                    "tags": {"building": "yes", "telecom": "data_center"},
                    "lat": 22.31,
                    "lon": 114.11,
                },
                {
                    "osm_type": "node",
                    "osm_id": 3,
                    "region_key": "hong-kong",
                    "proxy_type": "building",
                    "sector": "commercial",
                    "weight": 6.0,
                    "weight_method": "building_floor_area_proxy",
                    "confidence": 0.7,
                    "name": "General Hospital",
                    "tags": {"building": "hospital"},
                    "lat": 22.32,
                    "lon": 114.12,
                },
                {
                    "osm_type": "node",
                    "osm_id": 4,
                    "region_key": "hong-kong",
                    "proxy_type": "charging_station",
                    "sector": "transport_or_public_services",
                    "weight": 12.0,
                    "weight_method": "charging_station_socket_count",
                    "confidence": 0.65,
                    "name": "Fast Charger",
                    "tags": {"amenity": "charging_station"},
                    "lat": 22.33,
                    "lon": 114.13,
                },
                {
                    "osm_type": "node",
                    "osm_id": 5,
                    "region_key": "hong-kong",
                    "proxy_type": "station",
                    "sector": "transport_or_public_services",
                    "weight": 80.0,
                    "weight_method": "poi_default_weight",
                    "confidence": 0.75,
                    "name": "Central Station",
                    "tags": {"railway": "station"},
                    "lat": 22.34,
                    "lon": 114.14,
                },
                {
                    "osm_type": "node",
                    "osm_id": 6,
                    "region_key": "hong-kong",
                    "proxy_type": "wastewater_plant",
                    "sector": "industrial",
                    "weight": 90.0,
                    "weight_method": "poi_default_weight",
                    "confidence": 0.75,
                    "name": "Treatment Works",
                    "tags": {"man_made": "wastewater_plant"},
                    "lat": 22.35,
                    "lon": 114.15,
                },
            ]
            upsert_consumer_proxy_elements(conn, proxies=proxies)

        response = client.get("/grid/consumer-proxies/important", params={"region_key": "hong-kong", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    reasons = {marker["reason"] for marker in payload}
    assert len(payload) == 5
    assert {"data_center", "hospital", "charging_station", "station", "industrial_infrastructure"} <= reasons
    assert all("tags" not in marker and "geometry" not in marker for marker in payload)
    data_center_marker = next(marker for marker in payload if marker["reason"] == "data_center")
    assert data_center_marker["data_center_load_estimate"]["estimated_it_mw"] == 12.0
    assert data_center_marker["data_center_load_estimate"]["estimated_facility_mw"] == 17.4
    assert data_center_marker["data_center_load_estimate"]["provenance"] == "synthetic_engineering_default"


def test_important_consumer_proxy_endpoint_excludes_power_producers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    with TestClient(main.app) as client:
        with main.get_db() as conn:
            upsert_consumer_proxy_elements(
                conn,
                proxies=[
                    {
                        "osm_type": "way",
                        "osm_id": 10,
                        "region_key": "hong-kong",
                        "proxy_type": "building",
                        "sector": "industrial",
                        "weight": 500_000.0,
                        "weight_method": "building_floor_area_proxy",
                        "confidence": 0.7,
                        "name": "Island Power Station",
                        "tags": {
                            "building": "industrial",
                            "power": "plant",
                            "plant:output:electricity": "800 MW",
                        },
                        "lat": 22.20,
                        "lon": 114.10,
                    },
                    {
                        "osm_type": "way",
                        "osm_id": 11,
                        "region_key": "hong-kong",
                        "proxy_type": "building",
                        "sector": "industrial",
                        "weight": 400_000.0,
                        "weight_method": "building_floor_area_proxy",
                        "confidence": 0.7,
                        "name": "Industrial Works",
                        "tags": {"building": "industrial"},
                        "lat": 22.21,
                        "lon": 114.11,
                    },
                ],
            )

        response = client.get("/grid/consumer-proxies/important", params={"region_key": "hong-kong", "limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert "way:10:building" not in {marker["id"] for marker in payload}
    assert "way:11:building" in {marker["id"] for marker in payload}


def test_pipeline_summary_reports_running_ingest_stage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.sqlite3")

    with TestClient(main.app) as client:
        with main.get_db() as conn:
            ingest_run_id = create_ingest_run(conn, "hong-kong", "query")
        response = client.get("/grid/topology/pipeline-summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_ingest_run"]["id"] == ingest_run_id
    assert payload["latest_ingest_run"]["status"] == "running"
    assert payload["stage_status"]["raw_osm"] == "running"
    assert payload["stage_status"]["reconstructed_circuits"] == "running"
    assert payload["stage_status"]["solver_topology"] == "running"
    assert payload["stage_status"]["validation"] == "running"


def test_frontend_baseline_panel_does_not_add_hosting_capacity_ui() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "Baseline weak spots" in source
    assert "Top weak branches" in source
    assert "Top weak buses" in source
    assert "hosting capacity" not in source.lower()
