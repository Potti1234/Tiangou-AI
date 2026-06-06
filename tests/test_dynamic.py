from fastapi.testclient import TestClient

from app import main
from app.dynamic.adapter import build_dynamic_config
from app.dynamic.scenarios import build_scenarios


def _synthetic_case() -> dict:
    return {
        "baseMVA": 100.0,
        "bus": {"1": {"bus_i": 1, "source_id": "bus:1"}},
        "branch": {},
        "load": {
            "1": {
                "load_bus": 1,
                "pd": 10.0,
                "sector": "commercial",
                "hourly_pd_mw": [500.0] * 24,
            }
        },
        "gen": {
            "coal": {"gen_bus": 1, "pmax": 5.0, "pg": 4.0, "energy_source": "coal", "name": "Coal A", "provenance": "observed_osm", "confidence": 0.8},
            "gas": {"gen_bus": 1, "pmax": 4.0, "pg": 2.0, "energy_source": "gas", "name": "Gas A", "provenance": "observed_osm", "confidence": 0.8},
            "nuclear": {"gen_bus": 1, "pmax": 3.0, "pg": 2.5, "energy_source": "nuclear", "name": "Nuclear Import", "provenance": "inferred_import", "confidence": 0.6},
            "wind": {"gen_bus": 1, "pmax": 1.0, "pg": 0.8, "energy_source": "wind", "name": "Wind A", "provenance": "observed_osm", "confidence": 0.7},
            "solar": {"gen_bus": 1, "pmax": 0.5, "pg": 0.2, "energy_source": "solar", "name": "Solar A", "provenance": "observed_osm", "confidence": 0.7},
            "equiv": {"gen_bus": 1, "pmax": 2.0, "pg": 1.5, "resource_type": "equivalent_import_or_local_supply", "name": "Equivalent Supply", "provenance": "synthetic_equivalent_capacity", "confidence": 0.4},
        },
        "_metadata": {"total_pd_mw": 1000.0},
    }


def _consumer_proxies() -> list[dict]:
    return [
        {
            "id": "node:1:charging_station",
            "name": "Fast Charger",
            "proxy_type": "charging_station",
            "reason": "charging_station",
            "weight": 4.0,
            "confidence": 0.65,
            "lat": 22.3,
            "lon": 114.1,
        },
        {
            "id": "way:2:building",
            "name": "North Data Centre",
            "proxy_type": "building",
            "reason": "data_center",
            "weight": 5.0,
            "confidence": 0.7,
            "lat": 22.31,
            "lon": 114.11,
            "data_center_load_estimate": {
                "estimated_it_mw": 12.0,
                "estimated_facility_mw": 17.4,
                "provenance": "synthetic_engineering_default",
                "confidence": 0.46,
            },
        },
    ]


def test_dynamic_adapter_maps_generator_types_and_demand_profile() -> None:
    config = build_dynamic_config(_synthetic_case(), _consumer_proxies())

    types = config.source_mapping["types"]
    assert types["coal"] == 1
    assert types["gas_ccgt"] == 1
    assert types["nuclear"] == 1
    assert types["offshore_wind"] == 1
    assert types["solar_pv"] == 1
    assert types["imports"] == 1
    assert len(config.demand_profile_mw) == 24
    assert config.demand_profile_mw[16] == 1000.0
    assert config.ev_stations[0]["provenance"] == "osm_consumer_proxy_with_assumed_charger_load"
    assert config.data_centers[0]["estimated_facility_mw"] == 17.4


def test_dynamic_scenario_builder_selects_real_grid_assets() -> None:
    config = build_dynamic_config(_synthetic_case(), _consumer_proxies())
    scenarios = {scenario["id"]: scenario for scenario in build_scenarios(config)}

    assert scenarios["largest_generator_trip"]["affected_sources"] == ["Coal A"]
    assert scenarios["import_loss"]["affected_sources"] == ["Nuclear Import"]
    assert scenarios["datacenter_spike"]["magnitude_mw"] == 25.0
    assert scenarios["renewable_weather_loss"]["affected_sources"] == ["Wind A", "Solar A"]
    assert scenarios["combined_stress"]["type"] == "combined"


def test_dynamic_api_scenarios_and_simulation(monkeypatch) -> None:
    monkeypatch.setattr(main, "_build_dashboard_snapshot", lambda params: {"powermodels_case": _synthetic_case()})
    monkeypatch.setattr(main, "_important_proxy_markers_for_analytics", lambda region_key, limit=500: _consumer_proxies())
    monkeypatch.setattr(main, "_DYNAMIC_PINN_MODEL", None)
    monkeypatch.setattr(main, "_DYNAMIC_PINN_STATUS", None)

    with TestClient(main.app) as client:
        scenarios_response = client.get("/dynamic/scenarios")
        status_response = client.get("/dynamic/pinn-status")
        simulate_response = client.post(
            "/dynamic/simulate",
            json={"scenario": "combined_stress", "duration_s": 45, "demand_snapshot": "peak_16h", "model_mode": "full_demo"},
        )

    assert scenarios_response.status_code == 200
    assert any(scenario["id"] == "combined_stress" for scenario in scenarios_response.json()["scenarios"])
    assert status_response.status_code == 200
    assert status_response.json()["checkpoint_loaded"] is False
    assert simulate_response.status_code == 200
    payload = simulate_response.json()
    assert payload["frames"]
    assert set(payload) >= {"scenario", "duration_s", "frames", "outcome_A", "outcome_B", "kpis", "grid_source"}
    assert payload["grid_source"]["schema"] == "tiangou.dynamic.real_grid.v1"
    assert payload["pinn_status"]["startup_training"] is False
