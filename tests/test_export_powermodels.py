import json

import pytest

from app.database import connect, init_db
from app.export_powermodels import export_powermodels_case
from app.repository import create_ingest_run, upsert_elements


def test_export_powermodels_case_writes_json(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "hong_kong_16h_model.json"
    _seed_grid(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
    )

    assert result["validation"]["status"] == "ok"
    assert result["metadata"]["branch_count"] == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["baseMVA"] == 100.0
    assert payload["_metadata"]["total_pd_mw"] == 7336.0


def test_export_powermodels_case_writes_overnight_snapshot(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    output_path = tmp_path / "hong_kong_04h_model.json"
    _seed_grid(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        snap_tolerance_km=0.2,
        demand_snapshot="overnight_04h",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["demand_snapshot"] == "overnight_04h"
    assert payload["demand_snapshot"] == "overnight_04h"
    assert payload["_metadata"]["total_pd_mw"] == 4034.8
    assert payload["_metadata"]["total_equivalent_pmax_mw"] == 9170.0


def test_export_powermodels_case_blocks_validation_errors(tmp_path) -> None:
    db_path = tmp_path / "empty.sqlite3"
    output_path = tmp_path / "empty.json"
    init_db(db_path)

    with pytest.raises(ValueError, match="no_buses"):
        export_powermodels_case(database_path=db_path, output_path=output_path)

    assert not output_path.exists()


def test_export_powermodels_case_can_write_with_validation_errors(tmp_path) -> None:
    db_path = tmp_path / "empty.sqlite3"
    output_path = tmp_path / "empty.json"
    init_db(db_path)

    result = export_powermodels_case(
        database_path=db_path,
        output_path=output_path,
        allow_validation_errors=True,
    )

    assert result["validation"]["status"] == "error"
    assert output_path.exists()


def _seed_grid(db_path) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        run_id = create_ingest_run(conn, "hong-kong", "query")
        upsert_elements(
            conn,
            region_key="hong-kong",
            ingest_run_id=run_id,
            elements=[
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
            ],
        )
