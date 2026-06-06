"""
Two-phase training for GridPINN.

Primary: Spain 28-Apr-2025 blackout dataset (if available).
Fallback: Synthetic HK grid data (H≈1.567 s, S_base=12 000 MVA).

Phase 1 (epochs 0–500):   Pre_Event_15min sheet  — H frozen, learn f-shape
Phase 2 (epochs 500–2000): Second_by_Second sheet — H unfrozen, learn jointly

After training, H should converge to ~1.567 s (±0.2 s) on HK synthetic data.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.optim as optim

from .model import GridPINN, build_pinn
from .loss import physics_loss

logger = logging.getLogger(__name__)

SPAIN_S_BASE = 32000.0   # Spain grid base [MVA]
HK_S_BASE    = 12000.0

PHASE1_EPOCHS = 500
PHASE2_EPOCHS = 1500   # epochs 500–2000
LR_NET        = 1e-3
LR_H          = 1e-4   # 10× smaller for log_H


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _normalise_spain_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure required columns exist with correct names."""
    col_map = {c.lower().strip(): c for c in df.columns}
    required = ["time_s", "frequency_hz", "pm_mw", "pe_mw",
                "renewable_fraction", "h_prior"]
    for r in required:
        if r not in col_map:
            raise ValueError(f"Missing column '{r}' in dataset. Got: {list(df.columns)}")
    return df.rename(columns={v: k for k, v in col_map.items()
                               if k in required})


def load_spain_data(xlsx_path: str) -> dict:
    """
    Load Spain blackout dataset from Excel.
    Returns dict with keys 'phase1' and 'phase2', each a tensor dict.

    Expected sheets:
      'Pre_Event_15min'   — for phase 1
      'Second_by_Second'  — for phase 2
    Falls back to synthetic data if file not found (for offline dev/tests).
    """
    path = Path(xlsx_path)
    if not path.exists():
        logger.info(
            "Spain dataset not found at %s — generating HK typhoon training data "
            "from the actual grid simulator (higher fidelity than analytical fallback).",
            xlsx_path,
        )
        return generate_hk_typhoon_data()

    xl = pd.ExcelFile(xlsx_path)

    def _sheet_to_tensors(sheet_name: str) -> dict:
        df = pd.read_excel(xl, sheet_name=sheet_name)
        df = _normalise_spain_df(df)
        return {
            "t":               torch.tensor(df["time_s"].values,           dtype=torch.float32),
            "Pm":              torch.tensor(df["pm_mw"].values,            dtype=torch.float32),
            "Pe":              torch.tensor(df["pe_mw"].values,            dtype=torch.float32),
            "renewable_frac":  torch.tensor(df["renewable_fraction"].values, dtype=torch.float32),
            "H_prior":         torch.tensor(df["h_prior"].values,          dtype=torch.float32),
            "f_obs":           torch.tensor(df["frequency_hz"].values,     dtype=torch.float32),
        }

    return {
        "phase1": _sheet_to_tensors("Pre_Event_15min"),
        "phase2": _sheet_to_tensors("Second_by_Second"),
    }


def generate_hk_typhoon_data() -> dict:
    """
    Generate training data by running the actual HK grid simulator with the
    combined_stress (typhoon wind loss + datacenter spike) scenario.

    This replaces the crude analytical approximation with high-fidelity data
    that captures:
      - True HK inertia H = 1.567 s (nuclear + coal + CCGT1)
      - Exact governor dynamics (TAU_GOV=8 s, DROOP=5 %, RK4 integration)
      - Real wind ramp profile: −980 MW over 20 s starting at t=30
      - Datacenter demand ramp: +800 MW over 120 s starting at t=60
      - No dispatch (Timeline A trajectory — pure physics, no PINN intervention)

    Returns two phases matching the train_pinn() interface:
      phase1 — 30 pre-disturbance seconds (t=0..29): f ≈ 50 Hz, H stable
      phase2 — full 300-second typhoon event: frequency dips to ~48.7 Hz,
               governor partially compensates, H constant (no generator trips)
    """
    # Import here to avoid circular deps at module level
    from simulation.simulator import GridSimulator
    from config.hk_grid import get_baseline_copy, get_ev_stations_copy
    from config.disturbances import DISTURBANCE_EVENTS
    from pinn.model import GridPINN

    # Fresh simulator — default PINN (won't affect physics, only H estimation)
    sim = GridSimulator(
        get_baseline_copy(), get_ev_stations_copy(), GridPINN(), start_t=3 * 3600
    )
    disturbance = DISTURBANCE_EVENTS["combined_stress"]

    t_lst, f_lst, Pm_lst, Pe_lst, rf_lst, H_lst = [], [], [], [], [], []

    for step in range(300):
        event = disturbance if step == 30 else None
        state = sim.step(disturbance=event)
        t_lst.append(float(step))           # 0-based second index for training
        f_lst.append(state.f)
        Pm_lst.append(state.Pm_eff)         # governor-adjusted: matches actual df/dt
        Pe_lst.append(state.Pe)
        rf_lst.append(state.renewable_fraction)
        H_lst.append(state.H_physical)

    def _t(lst):
        return torch.tensor(lst, dtype=torch.float32)

    # Phase 2 uses only the pre-cascade window (f > 48.0 Hz, H_physical > 0).
    # Cascade timesteps (extreme Pm→0, Pe>>Pm) dominate the physics residual
    # and push log_H toward artificially high values — they must be excluded.
    valid = [
        i for i in range(len(f_lst))
        if f_lst[i] > 48.0 and H_lst[i] > 0.5
    ]
    logger.info(
        "HK typhoon training: using %d/%d timesteps (pre-cascade only, f>48 Hz)",
        len(valid), len(f_lst),
    )

    return {
        "phase1": {                         # pre-disturbance: t=0..29
            "t":              _t(t_lst[:30]),
            "Pm":             _t(Pm_lst[:30]),
            "Pe":             _t(Pe_lst[:30]),
            "renewable_frac": _t(rf_lst[:30]),
            "H_prior":        _t(H_lst[:30]),
            "f_obs":          _t(f_lst[:30]),
        },
        "phase2": {                         # typhoon transient — pre-cascade only
            "t":              _t([t_lst[i] for i in valid]),
            "Pm":             _t([Pm_lst[i] for i in valid]),
            "Pe":             _t([Pe_lst[i] for i in valid]),
            "renewable_frac": _t([rf_lst[i] for i in valid]),
            "H_prior":        _t([H_lst[i] for i in valid]),
            "f_obs":          _t([f_lst[i] for i in valid]),
        },
    }


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_pinn(
    model: Optional[GridPINN] = None,
    xlsx_path: str = "data/Spain_Blackout_28Apr2025_Dataset.xlsx",
    device: str = "cpu",
) -> GridPINN:
    """
    Full two-phase training.  Returns trained model.

    Phase 1: H frozen — network learns f dynamics from coarse pre-event data.
    Phase 2: H unfrozen — joint fine-tuning on second-by-second data.
    """
    if model is None:
        model = build_pinn()
    model = model.to(device)

    data = load_spain_data(xlsx_path)

    def _to_device(d: dict) -> dict:
        return {k: v.to(device) for k, v in d.items()}

    p1 = _to_device(data["phase1"])
    p2 = _to_device(data["phase2"])

    # ---- Phase 1: freeze log_H ----------------------------------------
    model.log_H.requires_grad_(False)
    optimizer1 = optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=LR_NET
    )

    logger.info("Phase 1: training on pre-event data (H frozen)…")
    for epoch in range(PHASE1_EPOCHS):
        optimizer1.zero_grad()
        loss, L_data, L_phys, H_val = physics_loss(
            model, p1["t"], p1["Pm"], p1["Pe"],
            p1["renewable_frac"], p1["H_prior"], p1["f_obs"],
            s_base=HK_S_BASE,
        )
        loss.backward()
        optimizer1.step()

        if epoch % 100 == 0:
            logger.info(
                "P1 epoch %d | loss=%.4f L_data=%.4f L_phys=%.4f H=%.3f",
                epoch, loss.item(), L_data, L_phys, H_val
            )

        if L_data < 0.05:
            logger.info("Phase 1 early stop at epoch %d (L_data=%.4f)", epoch, L_data)
            break

    # ---- Phase 2: unfreeze log_H --------------------------------------
    model.log_H.requires_grad_(True)
    optimizer2 = optim.Adam([
        {"params": [p for n, p in model.named_parameters() if n != "log_H"],
         "lr": LR_NET},
        {"params": [model.log_H],
         "lr": LR_H},
    ])

    logger.info("Phase 2: fine-tuning on second-by-second data (H unfrozen)…")
    for epoch in range(PHASE2_EPOCHS):
        optimizer2.zero_grad()
        loss, L_data, L_phys, H_val = physics_loss(
            model, p2["t"], p2["Pm"], p2["Pe"],
            p2["renewable_frac"], p2["H_prior"], p2["f_obs"],
            s_base=HK_S_BASE,
        )
        loss.backward()
        optimizer2.step()

        if epoch % 200 == 0:
            logger.info(
                "P2 epoch %d | loss=%.4f L_data=%.4f L_phys=%.4f H=%.3f",
                epoch, loss.item(), L_data, L_phys, H_val
            )

        if L_phys < 0.01:
            logger.info("Phase 2 early stop at epoch %d (L_phys=%.4f)", epoch, L_phys)
            break

    final_H = model.get_H_estimate()
    logger.info("Training complete. Final H = %.3f s (target: 1.567 ± 0.2 s)", final_H)

    if abs(final_H - 1.567) > 0.3:
        logger.warning(
            "H=%.3f deviates from HK expected 1.567 s — consider increasing LAMBDA_PHYS.",
            final_H
        )

    return model


def save_checkpoint(model: GridPINN, path: str = "pinn_checkpoint.pt") -> None:
    torch.save({"state_dict": model.state_dict(),
                "H_estimate": model.get_H_estimate()}, path)
    logger.info("Checkpoint saved to %s", path)


def load_checkpoint(path: str, device: str = "cpu") -> GridPINN:
    model = build_pinn().to(device)
    ckpt  = torch.load(path, map_location=device)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    logger.info("Loaded checkpoint from %s (H=%.3f s)", path, model.get_H_estimate())
    return model
