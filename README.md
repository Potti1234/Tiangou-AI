# Tiangou AI

Tiangou AI is a Hong Kong electricity-grid modeling and simulation project. It combines a FastAPI backend for public-data grid reconstruction, a main React dashboard for topology and dynamic-simulation analysis, and a separate HK grid simulator demo used for the public grid subdomain.

Live sites:

- Main site: https://eurotech.lukaspottner.com/
- Grid simulator: https://grid.lukaspottner.com/

## Project Structure

| Path | Purpose |
|---|---|
| `app/` | Main FastAPI application for OSM ingest, assumptions, topology reconstruction, PowerModels/GridSFM export, analytics, and dynamic simulation. |
| `frontend/` | Main React/Vite frontend for the landing page, map dashboard, analytics, and dynamic simulation views. |
| `hk_grid_backend/` | Standalone FastAPI simulation backend for the HK grid demo. |
| `hk_grid_frontend/` | Standalone React/Vite frontend for the HK grid simulator demo. |
| `data/` | Public raw datasets and assumption tables used by the main backend. Runtime SQLite files and processed outputs are not committed. |
| `tests/` | Pytest coverage for the main backend, topology, assumptions, exports, dynamic simulation, and API behavior. |
| `third_party/gridsfm_solver/` | Vendored GridSFM Julia solver handoff scripts and license files. |
| `pinn/` | PINN training and experiment code/artifacts kept separate from the production `app/` package. |
| `docker-compose.yml` | Main deployment: `app/` API plus `frontend/`. |
| `docker-compose.hk-grid.yml` | HK simulator deployment: `hk_grid_backend/` plus `hk_grid_frontend/`. |
| `HONESTY.md` | Hackathon disclosure of what is real, inferred, mocked, or approximate. |

## Main App

The main app is the GridSFM/topology dashboard and landing site.

### Local Backend

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Local Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend uses `VITE_API_BASE_URL` when set. In Docker, it is built with `VITE_API_BASE_URL=/api` and nginx proxies `/api` to the main API.

### Docker

```bash
docker compose up --build -d
```

Main site URL:

```text
http://localhost:8080
```

## HK Grid Simulator

This is the separate simulator shown on the grid subdomain.

### Local Backend

```bash
cd hk_grid_backend
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Local Frontend

```bash
cd hk_grid_frontend
npm install
npm run dev
```

Local frontend URL:

```text
http://localhost:5173
```

### Docker

```bash
docker compose -f docker-compose.hk-grid.yml up --build -d
```

Grid simulator URL:

```text
http://localhost:8082
```

The HK frontend nginx container proxies `/api/*` and `/ws/*` to `hk-grid-backend:8000`. The backend is internal to the Compose network and does not need a public host port.

## Environment Variables

| Variable | Used by | Required | Notes |
|---|---|---:|---|
| `TIANGOU_DATABASE_PATH` | Main Docker API | Yes in Docker | Set by `docker-compose.yml` to `/data/tiangou.sqlite3`. |
| `VITE_API_BASE_URL` | Main frontend build | Optional | Defaults to local API in dev; Docker sets it to `/api`. |

No environment variables are required for `hk_grid_backend/` or `hk_grid_frontend/`.

## Tests

```bash
pytest
```

Frontend build checks:

```bash
cd frontend
npm run build
```

```bash
cd hk_grid_frontend
npm run build
```

## Notes

Read `HONESTY.md` for the full disclosure of model assumptions, public data sources, synthetic topology, solver sanitization, and known limitations.
