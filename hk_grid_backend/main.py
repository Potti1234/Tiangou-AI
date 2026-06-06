"""
HK Grid Digital Twin — FastAPI backend.

Exposes:
  POST /simulate                  run dual-timeline scenario
  GET  /grid/state                current live grid state
  POST /grid/inject_event         inject a disturbance
  GET  /grid/sources              generation sources summary
  GET  /grid/ev_stations          EV charging stations
  POST /grid/manual_action        manually trigger a dispatch action
  GET  /pinn/status               PINN H estimate + training metadata
  WS   /ws/live                   1 Hz live GridState stream
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure project root is on sys.path when launched from any directory
sys.path.insert(0, str(Path(__file__).parent))

from config.hk_grid import get_baseline_copy, get_ev_stations_copy
from config.disturbances import DISTURBANCE_EVENTS
from pinn.model import build_pinn, GridPINN
from pinn.train import train_pinn, load_checkpoint, save_checkpoint
from simulation.simulator import GridSimulator
from simulation.dispatch import DispatchEngine, INTERVENTION_ACTIONS
from simulation.validator import PhysicsValidator
from simulation.dual_timeline import DualTimelineSimulation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHECKPOINT_PATH = "pinn_checkpoint.pt"
SPAIN_DATA_PATH = "data/Spain_Blackout_28Apr2025_Dataset.xlsx"


# ---------------------------------------------------------------------------
# App state — single live simulator instance
# ---------------------------------------------------------------------------

class AppState:
    pinn:       GridPINN
    simulator:  GridSimulator
    dispatch:   DispatchEngine
    validator:  PhysicsValidator
    dual_sim:   DualTimelineSimulation
    ws_clients: list

app_state = AppState()
app_state.ws_clients = []


HK_H_TRUE     = 1.567   # HK grid H at 3 AM (nuclear + coal + CCGT1)
HK_H_TOLERANCE = 0.15   # retrain if checkpoint H differs by more than this


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    needs_train = True
    if Path(CHECKPOINT_PATH).exists():
        candidate = load_checkpoint(CHECKPOINT_PATH)
        h_val = candidate.get_H_estimate()
        if abs(h_val - HK_H_TRUE) <= HK_H_TOLERANCE:
            logger.info(
                "Loaded PINN checkpoint (H=%.3f s, within %.2f s of HK target).",
                h_val, HK_H_TOLERANCE,
            )
            pinn = candidate
            needs_train = False
        else:
            logger.warning(
                "Checkpoint H=%.3f s deviates from HK target %.3f s by %.3f s — "
                "retraining on HK typhoon simulator data.",
                h_val, HK_H_TRUE, abs(h_val - HK_H_TRUE),
            )

    if needs_train:
        logger.info("Training PINN on HK typhoon scenario data…")
        pinn = train_pinn(xlsx_path=SPAIN_DATA_PATH)
        save_checkpoint(pinn, CHECKPOINT_PATH)
        logger.info("PINN trained and saved (H=%.3f s).", pinn.get_H_estimate())

    app_state.pinn      = pinn
    app_state.simulator = GridSimulator(
        get_baseline_copy(), get_ev_stations_copy(), pinn
    )
    app_state.dispatch  = DispatchEngine()
    app_state.validator = PhysicsValidator()
    app_state.dual_sim  = DualTimelineSimulation(pinn)

    # Background task: advance live simulator at 1 Hz
    asyncio.create_task(_live_simulation_loop())

    yield

    # --- shutdown --- (nothing to clean up)


app = FastAPI(
    title="HK Grid Digital Twin",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Background 1 Hz simulation loop
# ---------------------------------------------------------------------------

async def _live_simulation_loop():
    while True:
        await asyncio.sleep(1.0)
        state = app_state.simulator.step()

        if app_state.ws_clients:
            payload = json.dumps(state.to_dict())
            dead = []
            for ws in app_state.ws_clients:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                app_state.ws_clients.remove(ws)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    scenario:   str
    duration_s: int = 300


class InjectEventRequest(BaseModel):
    event_name: str


class ManualActionRequest(BaseModel):
    action_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/simulate")
async def simulate(req: SimulateRequest):
    """
    Run full dual-timeline simulation.
    Returns all frames + KPIs.  Runs synchronously (< 5s for 300s scenario).
    """
    if req.scenario not in DISTURBANCE_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{req.scenario}'. "
                   f"Available: {list(DISTURBANCE_EVENTS.keys())}"
        )

    if req.duration_s < 1 or req.duration_s > 3600:
        raise HTTPException(status_code=400, detail="duration_s must be 1–3600")

    # Run in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        app_state.dual_sim.run,
        req.scenario,
        req.duration_s,
    )
    return result


@app.get("/grid/state")
def get_grid_state():
    """Current live grid state snapshot."""
    sim = app_state.simulator
    H   = sim.compute_H_system()
    Pm  = sim.compute_Pm()
    Pe  = sim.compute_Pe()

    from config.thresholds import compute_risk_score, risk_level_from_score, freq_band
    risk  = compute_risk_score(H, 0.0, sim.f)
    level = risk_level_from_score(risk)
    fband = freq_band(sim.f)

    return {
        "t":              sim.t,
        "f":              sim.f,
        "H_physical":     H,
        "H_pinn":         sim.pinn.get_H_estimate(),
        "Pm":             Pm,
        "Pe":             Pe,
        "balance_mw":     Pm - Pe,
        "risk_score":     risk,
        "risk_level":     level,
        "freq_band":      fband,
        "renewable_frac": sim.compute_renewable_fraction(),
        "ev_active":      sum(1 for s in sim.ev if s["active"]),
    }


@app.post("/grid/inject_event")
def inject_event(req: InjectEventRequest):
    """Inject a named disturbance event into the live simulation."""
    if req.event_name not in DISTURBANCE_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event '{req.event_name}'. "
                   f"Available: {list(DISTURBANCE_EVENTS.keys())}"
        )
    event = DISTURBANCE_EVENTS[req.event_name]
    app_state.simulator.apply_disturbance(event)
    return {"status": "injected", "event": req.event_name,
            "description": event["description"]}


@app.get("/grid/sources")
def get_sources():
    """All generation sources with status, output, and H contribution."""
    S_BASE = 12000.0
    sources = []
    for s in app_state.simulator.get_all_sources():
        h_contribution = 0.0
        if s["online"] and s.get("H", 0) > 0:
            inertia_mva = s.get("inertia_mva", s["capacity_mw"])
            h_contribution = s["H"] * inertia_mva / S_BASE
        sources.append({
            **s,
            "h_contribution_s": round(h_contribution, 4),
        })
    return {"sources": sources, "H_system": app_state.simulator.compute_H_system()}


@app.get("/grid/ev_stations")
def get_ev_stations():
    """EV charging stations with active/inactive status."""
    stations = app_state.simulator.ev
    return {
        "stations":       stations,
        "total":          len(stations),
        "active":         sum(1 for s in stations if s["active"]),
        "total_load_mw":  sum(s["max_load_mw"] for s in stations if s["active"]),
    }


@app.post("/grid/manual_action")
def manual_action(req: ManualActionRequest):
    """Manually trigger a dispatch action (for demo control)."""
    action_map = {a["id"]: a for a in INTERVENTION_ACTIONS}
    if req.action_id not in action_map:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{req.action_id}'. "
                   f"Available: {list(action_map.keys())}"
        )
    action = action_map[req.action_id]
    app_state.simulator.apply_action(action)
    return {"status": "applied", "action": action}


@app.get("/pinn/status")
def get_pinn_status():
    """Current PINN H estimate and metadata."""
    return {
        "H_estimated":   app_state.pinn.get_H_estimate(),
        "log_H":         app_state.pinn.log_H.item(),
        "model_params":  sum(p.numel() for p in app_state.pinn.parameters()),
        "checkpoint":    CHECKPOINT_PATH,
        "target_H_spain": 1.14,
    }


@app.get("/scenarios")
def list_scenarios():
    """List all available disturbance scenarios."""
    return {
        name: {"description": ev["description"], "type": ev["type"]}
        for name, ev in DISTURBANCE_EVENTS.items()
    }


@app.get("/health")
def health():
    return {"status": "ok", "t": app_state.simulator.t}


# ---------------------------------------------------------------------------
# WebSocket — 1 Hz live stream
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    Streams GridState JSON at 1 Hz.
    The background loop pushes to all connected clients.
    """
    await websocket.accept()
    app_state.ws_clients.append(websocket)
    try:
        while True:
            # Keep connection alive; actual data pushed by _live_simulation_loop
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in app_state.ws_clients:
            app_state.ws_clients.remove(websocket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
