# Tiangou AI

**Live demo: https://eurotech.lukaspottner.com/**

AI-guided frequency stability system for the Hong Kong power grid. Tiangou AI uses a Physics-Informed Neural Network to predict frequency trajectories 60 seconds ahead and dispatch corrective actions before a disturbance turns into a blackout.

---

## What it does

Power grids must keep frequency within a narrow band. When generation and demand go out of balance, frequency drops. If it falls too far, protection relays trip generators automatically — which can cascade into a full blackout.

Tiangou AI runs a real-time risk score every second based on the predicted frequency minimum, inferred grid dynamics, and current frequency. When the score breaches a threshold, it dispatches the minimum set of corrective actions immediately — often 30–60 seconds before classical rate-of-change detectors would fire.

The simulation runs two parallel timelines side by side: one with no intervention, one with Tiangou AI active. The difference in outcomes is what the system is evaluated against.

---

## Architecture

| Component | Description | Port |
|---|---|---|
| `hk_grid_backend/` | Simulation engine with hardcoded HK grid config and scenario runner | 8000 |
| `app/` | FastAPI backend — OSM grid ingestion, PINN, dynamic simulation | 8001 |
| `hk_grid_frontend/` | Primary React dashboard — dual-panel comparison with HK Leaflet map | 5173 |
| `tiangou-ai-dashboard-v18/` | Alternative React dashboard | 5174 |
| `frontend/` | Landing page | — |

---

## Quick start

### Simulation backend (hk_grid_backend)

```bash
cd hk_grid_backend
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Scenarios available: `combined_stress`, `coal_plant_trip`, `mainland_disconnect`, `datacenter_spike`, `typhoon_wind_loss`, `solar_cloud_ramp`

### Primary frontend

```bash
cd hk_grid_frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. Requires the simulation backend running on port 8000.

### OSM-derived backend (app/)

```bash
python -m venv .venv
source .venv/bin/activate          # or .\.venv\Scripts\Activate.ps1 on Windows
pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8001
```

---

## Hong Kong grid

The grid topology was reconstructed from OpenStreetMap data — real transmission distances, node locations, and generation mix:

- **Lamma Power Station** — coal/gas, ~3,700 MW
- **Castle Peak Power Station** — coal/gas, northwest New Territories
- **Black Point Power Station** — CCGT, northwest New Territories
- **Daya Bay Nuclear** — import connection from mainland China
- **Offshore wind, solar, grid-scale battery storage**

The OSM ingestion pipeline is available via the `app/` backend:

```bash
curl -X POST http://127.0.0.1:8001/ingest/hong-kong
```

---

## Docker

```bash
docker compose up --build
```

Opens at `http://localhost:8080`. The frontend is served by nginx and proxies `/api/*` to the FastAPI service.

---

## PINN checkpoint

The Physics-Informed Neural Network checkpoint is at `app/dynamic/pinn_checkpoint.pt`. It requires the CPU PyTorch wheel — the same wheel installed in the setup above and in the Docker image.
