"""
Physics loss for GridPINN.

Three-component loss:
  L = L_data + lambda_phys * L_physics + lambda_causal * L_causal

L_data:    MSE(f_pred, f_obs)
L_physics: residual of the swing equation via autograd df/dt
L_causal:  exponential time-weighting (Karniadakis 2022) — prevents
           the network from fitting future data before the past is learned
"""

from typing import Tuple
import torch
import torch.nn as nn

from .model import GridPINN

F0     = 50.0
S_BASE = 12000.0   # HK transfer value; Spain training uses 32000.0

LAMBDA_PHYS    = 10.0
LAMBDA_CAUSAL  = 0.1
CAUSAL_DECAY   = 0.1   # γ in exp(-γ·t)


def physics_loss(
    model: GridPINN,
    t: torch.Tensor,
    Pm: torch.Tensor,
    Pe: torch.Tensor,
    renewable_frac: torch.Tensor,
    H_prior: torch.Tensor,
    f_obs: torch.Tensor,
    s_base: float = S_BASE,
    lambda_phys: float = LAMBDA_PHYS,
    lambda_causal: float = LAMBDA_CAUSAL,
) -> Tuple[torch.Tensor, float, float, float]:
    """
    Returns (total_loss, L_data, L_physics, H_current).

    t must NOT have requires_grad set before calling — we set it here
    so the caller's graph stays clean.
    """
    t = t.detach().requires_grad_(True)

    f_pred = model(t, Pm, Pe, renewable_frac, H_prior)   # (N, 1)

    # Autograd df/dt — the PINN's core trick
    df_dt = torch.autograd.grad(
        f_pred,
        t,
        grad_outputs=torch.ones_like(f_pred),
        create_graph=True,
    )[0]                                                  # (N,) or (N,1)

    # Swing equation: df/dt = (f0 / (2·H·S_base)) · (Pm - Pe)
    H = model.H
    df_dt_physics = (F0 / (2.0 * H * s_base)) * (Pm - Pe)

    L_physics = nn.MSELoss()(df_dt.squeeze(), df_dt_physics.squeeze())
    L_data    = nn.MSELoss()(f_pred.squeeze(), f_obs.squeeze())

    # Causal weighting — earlier time points are weighted more
    weights  = torch.exp(-CAUSAL_DECAY * t.squeeze().detach())
    L_causal = (weights * (f_pred.squeeze() - f_obs.squeeze()) ** 2).mean()

    total = L_data + lambda_phys * L_physics + lambda_causal * L_causal

    return total, L_data.item(), L_physics.item(), H.item()
