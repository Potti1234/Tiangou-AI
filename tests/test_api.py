from fastapi.testclient import TestClient

from app import main
from app.config import settings


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
        preview_response = client.get("/grid/topology/powermodels-preview")
        overnight_response = client.get(
            "/grid/topology/powermodels-preview",
            params={"demand_snapshot": "overnight_04h"},
        )
        intertie_validation_response = client.get(
            "/grid/topology/validation",
            params={"include_hk_interties": True, "hk_intertie_derate": 0.5},
        )
        validation_response = client.get("/grid/topology/validation")

    assert ingest_response.status_code == 200
    assert preview_response.status_code == 200
    assert overnight_response.status_code == 200
    assert intertie_validation_response.status_code == 200
    assert validation_response.status_code == 200
    payload = preview_response.json()
    assert payload["baseMVA"] == 100.0
    assert payload["_metadata"]["branch_count"] == 1
    assert payload["_metadata"]["load_count"] == 2
    assert payload["_metadata"]["gen_count"] == 1
    assert overnight_response.json()["_metadata"]["total_pd_mw"] == 4034.8
    assert intertie_validation_response.json()["metrics"]["island_count"] == 1
    validation_payload = validation_response.json()
    assert validation_payload["status"] == "ok"
    assert validation_payload["metrics"]["low_confidence_counts"]["load"] == 2
