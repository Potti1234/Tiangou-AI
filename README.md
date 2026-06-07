# Tiangou AI

**Live demo: https://eurotech.lukaspottner.com/**

AI-guided frequency stability system for the Hong Kong power grid. Tiangou AI uses a Physics-Informed Neural Network to predict frequency trajectories 60 seconds ahead and dispatch corrective actions before a disturbance turns into a blackout.

---

## What it does

Power grids must keep frequency within a narrow band. When generation and demand go out of balance, frequency drops. If it falls too far, protection relays trip generators automatically — which can cascade into a full blackout.

Tiangou AI runs a real-time risk score every second based on the predicted frequency minimum, inferred grid dynamics, and current frequency. When the score breaches a threshold, it dispatches the minimum set of corrective actions immediately — often 30–60 seconds before classical rate-of-change detectors would fire.

The simulation runs two parallel timelines side by side: one with no intervention, one with Tiangou AI active. The difference in outcomes is what the system is evaluated against.

---

## Repository layout

```
Tiangou-AI/
├── hk_grid_backend/        # FastAPI simulation server (port 8000)
│   ├── main.py             #   API routes — /simulate, /scenarios, /config
│   ├── simulation/         #   Swing-equation engine, dual-timeline runner
│   ├── pinn/               #   PINN model definition and training script
│   ├── pinn_checkpoint.pt  #   Trained checkpoint loaded at startup
│   └── config/             #   HK grid topology, generator parameters
│
├── hk_grid_frontend/       # React dashboard (Vite, port 5173)
│   └── src/
│       ├── App.jsx          #   Layout, simulation state, playback loop
│       ├── components/
│       │   ├── Header.jsx          # Scenario picker, run/play controls, timeline scrubber
│       │   ├── GridPanel.jsx       # Per-side panel (status cards, map, physics readouts)
│       │   ├── HKMap.jsx           # Leaflet map — HK nodes, transmission edges, live tooltips
│       │   └── CombinedFreqChart.jsx  # Shared frequency chart — both timelines overlaid
│       └── assets/          #   Tiangou AI logo
│
├── app/                    # FastAPI backend — OSM ingestion + PINN research path (port 8001)
│   ├── main.py             #   Full API: ingest, topology, simulation, PINN, export
│   ├── dynamic/            #   PINN model, swing-equation simulator, dispatch logic
│   └── ...                 #   OSM ingestion, topology reconstruction, PowerModels export
│
├── frontend/               # Landing page (React/TypeScript, MapLibre)
│
├── pinn/                   # PINN training notebooks and Spain blackout data exploration
│   ├── src/                #   Model and training code
│   ├── notebooks/          #   Jupyter experiments
│   └── data/               #   Spain 28-Apr-2025 blackout dataset
│
├── data/                   # Public datasets and assumption tables
│   ├── raw/                #   HK Electric, EMSD, Census & Statistics CSVs
│   └── assumptions/        #   Line ratings, transformer defaults, generator parameters
│
├── tests/                  # pytest tests for the app/ backend
├── third_party/            # Vendored GridSFM Julia solver pipeline (MIT)
├── docker-compose.yml               # Full stack (app/ + frontend/)
└── docker-compose.hk-grid.yml       # HK demo only (hk_grid_backend + hk_grid_frontend)
```

The demo at https://eurotech.lukaspottner.com/ runs `hk_grid_backend` + `hk_grid_frontend` only. The `app/` backend is the deeper research path with OSM ingestion, topology reconstruction, and the PowerModels/GridSFM export pipeline.

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

Services exposed by the root Compose file:

| Service | URL |
|---|---|
| Landing/GridSFM frontend | `http://localhost:8080` |

To deploy only the HK grid simulation backend and dashboard:

```bash
docker compose -f docker-compose.hk-grid.yml up --build -d
```

The HK grid dashboard is exposed at `http://localhost:8082`. The HK backend stays internal to that Compose deployment on port `8000`; nginx proxies `/api/*` and `/ws/*` to `hk-grid-backend:8000`. No environment variables are required for `hk_grid_backend/` or `hk_grid_frontend/`.

---

## PINN checkpoint

The Physics-Informed Neural Network checkpoint is at `app/dynamic/pinn_checkpoint.pt`. It requires the CPU PyTorch wheel — the same wheel installed in the setup above and in the Docker image.
