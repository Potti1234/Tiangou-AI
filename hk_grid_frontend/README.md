# GridGuard AI — Frontend

React + Vite dashboard connected to the FastAPI simulation backend.

## Quick start

**Terminal 1 — backend:**
```bash
cd hk_grid_backend
source .venv/bin/activate
python main.py
# → http://localhost:8000
```

**Terminal 2 — frontend:**
```bash
cd hk_grid_frontend
npm run dev
# → http://localhost:5173
```

Open **http://localhost:5173** in your browser.

## What it shows

| Left panel | Right panel |
|---|---|
| Conventional grid (no intervention) | GridGuard AI active (PINN-guided dispatch) |
| Red nodes, frequency decline | Green nodes, stable frequency |
| Blackout countdown | Blackout prevented |

## Controls

- **RUN** — fetch a fresh simulation from the backend
- **▶ / ⏸** — play / pause the frame-by-frame animation
- **↺** — replay from start
- Timeline **scrubber** — jump to any point in the simulation
- Scenario dropdown — typhoon, coal trip, or mainland disconnect
- Duration dropdown — 200 / 400 / 600 second simulation window
