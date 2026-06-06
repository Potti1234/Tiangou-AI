from fastapi.testclient import TestClient

from app import main
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


def test_assumption_validation_summary_reports_line_enrichment_and_remaining_empty_tables() -> None:
    payload = build_assumption_validation_summary()

    assert payload["schema"] == "tiangou.assumptions.validation_summary.v1"
    assert payload["status"] == "warning"
    assert payload["table_count"] == 12
    assert payload["row_count"] == 46
    assert payload["errors"] == []
    assert {warning["code"] for warning in payload["warnings"]} == {"empty_table"}
    assert set(payload["provenance_classes"]) == {
        "observed_public",
        "inferred_from_public_statistics",
        "synthetic_engineering_default",
    }
    assert all(table["status"] == "ok" for table in payload["tables"])
    assert payload["provenance_counts"] == {"synthetic_engineering_default": 46}


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


def test_assumption_api_summary_and_drilldowns() -> None:
    with TestClient(main.app) as client:
        summary_response = client.get("/assumptions/summary")
        lines_response = client.get("/assumptions/lines")
        transformers_response = client.get("/assumptions/transformers")
        data_centers_response = client.get("/assumptions/data-centers")
        generators_response = client.get("/assumptions/generators")
        contingencies_response = client.get("/assumptions/contingencies")
        imports_response = client.get("/assumptions/imports")

    assert summary_response.status_code == 200
    assert lines_response.status_code == 200
    assert transformers_response.status_code == 200
    assert data_centers_response.status_code == 200
    assert generators_response.status_code == 200
    assert contingencies_response.status_code == 200
    assert imports_response.status_code == 200

    summary_payload = summary_response.json()
    assert summary_payload["table_count"] == 12
    assert summary_payload["status"] == "warning"
    assert summary_payload["row_count"] == 46
    assert {table["key"] for table in lines_response.json()} == {
        "line_thermal_rating_defaults",
        "cable_impedance_defaults",
        "overhead_line_impedance_defaults",
    }
    assert transformers_response.json()[0]["category"] == "transformers"
    assert data_centers_response.json()[0]["key"] == "data_center_site_assumptions"
    assert len(generators_response.json()) == 2
    assert contingencies_response.json()[0]["key"] == "synthetic_contingency_library"
    assert imports_response.json()[0]["key"] == "cross_border_import_limits"
