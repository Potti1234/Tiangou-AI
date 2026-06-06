from fastapi.testclient import TestClient

from app import main
from app.assumptions.provenance import ASSUMPTION_TABLES, REQUIRED_PROVENANCE_COLUMNS, read_table_rows
from app.assumptions.validation import build_assumption_validation_summary


def test_assumption_csv_scaffolding_has_required_provenance_columns() -> None:
    assert len(ASSUMPTION_TABLES) == 12

    for table in ASSUMPTION_TABLES:
        assert table.path.exists(), table.path
        fieldnames, rows = read_table_rows(table)
        assert rows == []
        assert set(table.required_columns) <= set(fieldnames)
        assert set(REQUIRED_PROVENANCE_COLUMNS) <= set(fieldnames)


def test_assumption_validation_summary_reports_scaffold_only_state() -> None:
    payload = build_assumption_validation_summary()

    assert payload["schema"] == "tiangou.assumptions.validation_summary.v1"
    assert payload["status"] == "warning"
    assert payload["table_count"] == 12
    assert payload["row_count"] == 0
    assert payload["errors"] == []
    assert payload["warnings"][0]["code"] == "scaffold_only"
    assert set(payload["provenance_classes"]) == {
        "observed_public",
        "inferred_from_public_statistics",
        "synthetic_engineering_default",
    }
    assert all(table["status"] == "ok" for table in payload["tables"])


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
