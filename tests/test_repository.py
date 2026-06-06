import pytest

from app.database import init_db, connect
from app.repository import create_ingest_run, list_elements, upsert_elements


def test_upsert_elements_stores_power_assets(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        run_id = create_ingest_run(conn, "hong-kong", "query")
        count = upsert_elements(
            conn,
            region_key="hong-kong",
            ingest_run_id=run_id,
            elements=[
                {
                    "type": "way",
                    "id": 123,
                    "tags": {
                        "power": "line",
                        "name": "Example Line",
                        "voltage": "400000",
                    },
                    "geometry": [
                        {"lat": 22.1, "lon": 114.1},
                        {"lat": 22.3, "lon": 114.3},
                    ],
                },
                {"type": "node", "id": 456, "tags": {"amenity": "school"}},
            ],
        )
        rows = list_elements(conn, region_key="hong-kong")

    assert count == 1
    assert len(rows) == 1
    assert rows[0]["power"] == "line"
    assert rows[0]["lat"] == pytest.approx(22.2)
    assert rows[0]["lon"] == pytest.approx(114.2)
