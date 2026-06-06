# Tiangou-AI

FastAPI backend for collecting OpenStreetMap electricity grid data for Hong Kong first, with Greater Bay Area support built into the same ingestion path.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Run

```powershell
uvicorn app.main:app --reload
```

The SQLite database defaults to `data/tiangou.sqlite3`. Override it with:

```powershell
$env:TIANGOU_DATABASE_PATH="data/custom.sqlite3"
```

## Docker Test Deployment

Build and run the backend plus frontend proxy locally:

```powershell
docker compose up --build
```

Open `http://localhost:8080`. The frontend is served by nginx and proxies `/api/*` to the FastAPI service, so a single Cloudflare Tunnel/Dokploy public route can point at the `frontend` service on port `80`.

The containerized SQLite database is stored in the named Docker volume `tiangou-data`. The backend uses `/data/tiangou.sqlite3` through `TIANGOU_DATABASE_PATH`.

For Dokploy, deploy this repository with Docker Compose and expose only the `frontend` service. The `api` service stays internal on the Compose network.

## Ingest OpenStreetMap Power Data

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest/hong-kong
```

For the Greater Bay Area:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest/greater-bay-area
```

The backend uses raw Overpass QL. The `{{geocodeArea:...}}` macro works in Overpass Turbo, but raw API clients need ordinary Overpass area selectors instead.

## Build a Topology Preview

After ingesting a region, inspect the inferred bus-branch model:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/grid/topology/preview
```

Generate a first PowerModels-style solver handoff JSON:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/grid/topology/powermodels-preview
```

Run structural validation before solver handoff:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/grid/topology/validation
```

Write the preview to a file for the downstream Julia solver pipeline:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json
```

Add the public 720 MVA CLP-HK Electric interconnection when building an optimization case:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json --include-hk-interties
```

Derate that interconnection for transfer-stress cases:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json --include-hk-interties --hk-intertie-derate 0.5
```

Write both Phase 1 Hong Kong snapshots plus a manifest:

```powershell
python -m app.export_powermodels data/processed --hong-kong-phase1-bundle --include-hk-interties
```

This preview uses OSM geometry, voltage-class impedance defaults, public Hong Kong peak-demand anchors, and territory-level equivalent generators. Treat it as an upstream topology-builder artifact for the Julia relaxation/export pipeline, not as an operational grid model.
