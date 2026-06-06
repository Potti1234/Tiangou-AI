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

## Ingest OpenStreetMap Power Data

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest/hong-kong
```

For the Greater Bay Area:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest/greater-bay-area
```

The backend uses raw Overpass QL. The `{{geocodeArea:...}}` macro works in Overpass Turbo, but raw API clients need ordinary Overpass area selectors instead.
