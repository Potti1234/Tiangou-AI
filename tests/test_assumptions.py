from fastapi.testclient import TestClient

from app import main
from app.assumptions.data_centers import estimate_data_center_load
from app.assumptions.demand_profiles import demand_profile_for_sector, hourly_load_metadata, hourly_profile_summary
from app.assumptions.generators import generator_defaults
from app.assumptions.imports import import_boundary_defaults
from app.assumptions.lines import branch_parameter_defaults
from app.assumptions.provenance import ASSUMPTION_TABLES, REQUIRED_PROVENANCE_COLUMNS, read_table_rows
from app.assumptions.transformers import transformer_parameter_defaults
from app.assumptions.validation import build_assumption_validation_summary


def test_assumption_csvs_have_required_provenance_columns() -> None:
    assert len(ASSUMPTION_TABLES) == 12

    row_counts = {}
    for table in ASSUMPTION_TABLES:
        assert table.path.exists(), table.path
        fieldnames, rows = read_table_rows(table)
        row_counts[table.key] = len(rows)
        assert set(table.required_columns) <= set(fieldnames)
        assert set(REQUIRED_PROVENANCE_COLUMNS) <= set(fieldnames)

    assert row_counts["line_thermal_rating_defaults"] > 0
    assert row_counts["cable_impedance_defaults"] > 0
    assert row_counts["overhead_line_impedance_defaults"] > 0
    assert row_counts["transformer_capacity_defaults"] > 0
    assert row_counts["transformer_tap_defaults"] > 0
    assert row_counts["hong_kong_sector_hourly_profiles"] == 120
    assert row_counts["weather_sensitivity_profiles"] == 10
    assert row_counts["data_center_site_assumptions"] == 3
    assert row_counts["generator_cost_availability_defaults"] == 10
    assert row_counts["generator_dispatch_merit_order"] == 10
    assert row_counts["synthetic_contingency_library"] == 8
    assert row_counts["cross_border_import_limits"] == 4


def test_assumption_validation_summary_reports_complete_enrichment_tables() -> None:
    payload = build_assumption_validation_summary()

    assert payload["schema"] == "tiangou.assumptions.validation_summary.v1"
    assert payload["status"] == "ok"
    assert payload["table_count"] == 12
    assert payload["row_count"] == 211
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert set(payload["provenance_classes"]) == {
        "observed_public",
        "inferred_from_public_statistics",
        "synthetic_engineering_default",
    }
    assert all(table["status"] == "ok" for table in payload["tables"])
    assert payload["provenance_counts"] == {"observed_public": 1, "synthetic_engineering_default": 210}


def test_line_assumption_lookup_scales_rating_and_exposes_provenance() -> None:
    defaults = branch_parameter_defaults("line", 400.0, circuit_count=2)

    assert defaults["rate_mva"] == 3600.0
    assert defaults["rate_mva_per_circuit"] == 1800.0
    assert defaults["parameter_source"] == "assumption_table_lookup"
    assert defaults["parameter_provenance"] == "synthetic_engineering_default"
    assert defaults["parameter_confidence"] == 0.62
    assert defaults["parameter_table_keys"] == [
        "overhead_line_impedance_defaults",
        "line_thermal_rating_defaults",
    ]


def test_transformer_assumption_lookup_exposes_capacity_tap_and_provenance() -> None:
    defaults = transformer_parameter_defaults(400.0, 132.0)

    assert defaults["rate_mva"] == 750.0
    assert defaults["sn_mva_default"] == 750.0
    assert defaults["br_x"] == 0.10
    assert defaults["tap"] == 1.0
    assert defaults["tap_min"] == 0.90
    assert defaults["tap_max"] == 1.10
    assert defaults["parameter_source"] == "transformer_assumption_table_lookup"
    assert defaults["parameter_provenance"] == "synthetic_engineering_default"
    assert defaults["parameter_table_keys"] == [
        "transformer_capacity_defaults",
        "transformer_tap_defaults",
    ]


def test_demand_profile_lookup_normalizes_hourly_shape_and_exposes_provenance() -> None:
    profile = demand_profile_for_sector("residential")
    metadata = hourly_load_metadata("residential", peak_pd_mw=100.0, fallback_pd_mw=60.0)
    summary = hourly_profile_summary()

    assert len(profile["shares"]) == 24
    assert round(sum(profile["shares"]), 6) == 1.0
    assert metadata["load_profile_id"] == "hk_residential_synthetic"
    assert metadata["profile_provenance"] == "synthetic_engineering_default"
    assert len(metadata["hourly_pd_mw"]) == 24
    assert max(metadata["hourly_pd_mw"]) == 100.0
    assert metadata["peak_hour"] == 18
    assert summary["commercial"]["share_sum"] == 1.0


def test_data_center_estimator_uses_floor_area_and_exposes_provenance() -> None:
    estimate = estimate_data_center_load(
        {
            "proxy_type": "data_center",
            "weight": 20_000.0,
            "weight_method": "building_floor_area_proxy",
            "confidence": 0.7,
            "name": "Tagged Data Centre",
            "tags": {"telecom": "data_center"},
        }
    )

    assert estimate is not None
    assert estimate["estimated_it_mw"] == 10.8
    assert estimate["estimated_facility_mw"] == 15.66
    assert estimate["pue"] == 1.45
    assert estimate["floor_area_method"] == "building_floor_area_proxy"
    assert estimate["provenance"] == "synthetic_engineering_default"


def test_generator_defaults_expose_cost_availability_and_provenance() -> None:
    defaults = generator_defaults("gas")

    assert defaults["cost"] == [0.0, 22.0, 0.0]
    assert defaults["cost_class"] == "thermal_gas"
    assert defaults["availability_factor"] == 0.90
    assert defaults["forced_outage_rate"] == 0.06
    assert defaults["co2_t_per_mwh"] == 0.40
    assert defaults["dispatch_priority"] == 5
    assert defaults["synthetic_cost_provenance"] == "synthetic_engineering_default"


def test_import_boundary_defaults_expose_derates_and_provenance() -> None:
    defaults = import_boundary_defaults("clp_hk_electric_interconnection")

    assert defaults["nominal_mw"] == 720.0
    assert defaults["derate_scenarios"] == [1.0, 0.75, 0.5, 0.0]
    assert defaults["availability"] == 0.95
    assert defaults["provenance"] == "observed_public"


def test_assumption_api_summary_and_drilldowns() -> None:
    with TestClient(main.app) as client:
        summary_response = client.get("/assumptions/summary")
        lines_response = client.get("/assumptions/lines")
        transformers_response = client.get("/assumptions/transformers")
        data_centers_response = client.get("/assumptions/data-centers")
        demand_profiles_response = client.get("/assumptions/demand-profiles")
        generators_response = client.get("/assumptions/generators")
        contingencies_response = client.get("/assumptions/contingencies")
        imports_response = client.get("/assumptions/imports")

    assert summary_response.status_code == 200
    assert lines_response.status_code == 200
    assert transformers_response.status_code == 200
    assert data_centers_response.status_code == 200
    assert demand_profiles_response.status_code == 200
    assert generators_response.status_code == 200
    assert contingencies_response.status_code == 200
    assert imports_response.status_code == 200

    summary_payload = summary_response.json()
    assert summary_payload["table_count"] == 12
    assert summary_payload["status"] == "ok"
    assert summary_payload["row_count"] == 211
    assert {table["key"] for table in lines_response.json()} == {
        "line_thermal_rating_defaults",
        "cable_impedance_defaults",
        "overhead_line_impedance_defaults",
    }
    assert transformers_response.json()[0]["category"] == "transformers"
    assert data_centers_response.json()[0]["key"] == "data_center_site_assumptions"
    assert {table["key"] for table in demand_profiles_response.json()} == {
        "hong_kong_sector_hourly_profiles",
        "weather_sensitivity_profiles",
    }
    assert len(generators_response.json()) == 2
    assert contingencies_response.json()[0]["key"] == "synthetic_contingency_library"
    assert imports_response.json()[0]["key"] == "cross_border_import_limits"
