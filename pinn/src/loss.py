"""
Loss functions for GridPINN training.

Total loss = λ_data · L_data + λ_physics · L_physics + λ_causal · L_causal

L_physics enforces the swing equation via automatic differentiation:
    df/dt = (f0 / (2·H·S_base)) · ΔP

The physics loss operates in PHYSICAL units so the H estimate is
interpretable regardless of how the other quantities are normalised.

L_causal applies an exponential weighting that decays the penalty for
earlier time steps — this is the Karniadakis "causal" PINN trick that
prevents the network from using future information to fit the past.
"""

import sys
sys.path.insert(0, '/mnt/data/hackathon/venv_pkgs')

import torch
import torch.nn as nn
from typing import Tuple, Dict, Optional

F0 = 50.0           # nominal frequency (Hz)
S_BASE = 32_000.0   # Spain MVA base


def physics_residual(
    model,
    t_norm: torch.Tensor,
    Pm_norm: torch.Tensor,
    Pe_norm: torch.Tensor,
    rf_norm: torch.Tensor,
    scalers: Dict,
    f0: float = F0,
    S_base: float = S_BASE,
) -> torch.Tensor:
    """
    Computes the swing-equation physics residual in physical units.

    Autograd differentiates f_pred (normalised) w.r.t. t_norm, then
    the chain rule converts to physical df/dt [Hz/s]:

        df/dt_physical = df_norm/dt_norm * (f_hi - f_lo) / (t_hi - t_lo)

    The rhs of the swing equation is similarly reconstructed in MW from
    the normalised Pm and Pe tensors.
    """
    t_in = t_norm.clone().requires_grad_(True)

    f_pred_norm = model(t_in, Pm_norm, Pe_norm, rf_norm)   # [N, 1]

    # df/dt in normalised coordinates
    df_dt_norm = torch.autograd.grad(
        f_pred_norm,
        t_in,
        grad_outputs=torch.ones_like(f_pred_norm),
        create_graph=True,
        retain_graph=True,
    )[0]   # [N]

    # ---- convert to physical units ----
    f_lo,  f_hi  = scalers['f']
    t_lo,  t_hi  = scalers.get('t1s', scalers.get('t15'))   # whichever phase
    df_dt_phys = df_dt_norm * (f_hi - f_lo) / max(t_hi - t_lo, 1e-6)  # Hz/s

    Pm_lo, Pm_hi = scalers['Pm']
    Pe_lo, Pe_hi = scalers['Pe']
    Pm_phys = Pm_norm * (Pm_hi - Pm_lo) + Pm_lo   # MW
    Pe_phys = Pe_norm * (Pe_hi - Pe_lo) + Pe_lo   # MW

    delta_P = Pm_phys - Pe_phys   # MW  (>0 = over-generation → f rises)

    H = model.H   # learnable, in seconds
    df_dt_swing = (f0 / (2.0 * H * S_base)) * delta_P   # Hz/s (physical rhs)

    residual = df_dt_phys.squeeze() - df_dt_swing.squeeze()   # should be 0
    return residual, f_pred_norm


def compute_loss(
    model,
    t_norm: torch.Tensor,
    Pm_norm: torch.Tensor,
    Pe_norm: torch.Tensor,
    rf_norm: torch.Tensor,
    f_obs_norm: torch.Tensor,
    scalers: Dict,
    t_key: str = 't1s',
    f0: float = F0,
    S_base: float = S_BASE,
    lambda_data: float = 1.0,
    lambda_physics: float = 10.0,
    lambda_causal: float = 0.1,
    causal_eps: float = 0.1,
) -> Tuple[torch.Tensor, float, float, float]:
    """
    Total PINN loss with three components.

    Args:
        t_norm:       normalised time [N]
        Pm_norm:      normalised mechanical power [N]
        Pe_norm:      normalised electrical demand [N]
        rf_norm:      normalised renewable fraction [N]
        f_obs_norm:   normalised observed frequency [N]
        scalers:      dict of (lo, hi) pairs from DataBundle
        t_key:        which time scaler to use ('t1s' or 't15')
        lambda_*:     loss weights
        causal_eps:   decay rate for causal weighting (higher = faster decay)

    Returns:
        (total_loss, loss_data, loss_physics, H_current)
    """
    # Override the time scaler key so physics_residual uses the right one
    scalers_with_tkey = dict(scalers)
    scalers_with_tkey['t1s'] = scalers_with_tkey.get(t_key, scalers_with_tkey.get('t1s'))

    residual, f_pred_norm = physics_residual(
        model, t_norm, Pm_norm, Pe_norm, rf_norm,
        scalers_with_tkey, f0=f0, S_base=S_base,
    )

    # 1. Data loss (MSE on normalised frequency)
    loss_data = nn.functional.mse_loss(f_pred_norm.squeeze(), f_obs_norm)

    # 2. Physics loss (swing equation residual, physical Hz/s)
    loss_physics = (residual ** 2).mean()

    # 3. Causal weighting: exponential decay over time index
    #    weight[i] = exp(-eps * i)  → earlier samples contribute less
    #    This stops the PINN from "cheating" by reading future f values.
    causal_w = torch.exp(-causal_eps * t_norm.squeeze()).detach()
    loss_causal = (causal_w * (f_pred_norm.squeeze() - f_obs_norm) ** 2).mean()

    total = (lambda_data * loss_data
             + lambda_physics * loss_physics
             + lambda_causal * loss_causal)

    return total, loss_data.item(), loss_physics.item(), model.H.item()


def compute_loss_phase1(model, bundle, **kwargs):
    """Phase-1 loss: slow 15-min pre-event data, H frozen."""
    return compute_loss(
        model,
        t_norm    = bundle.t15_norm,
        Pm_norm   = bundle.pm15_norm,
        Pe_norm   = bundle.pe15_norm,
        rf_norm   = bundle.rf15_norm,
        f_obs_norm= bundle.f15_norm,
        scalers   = bundle.scalers,
        t_key     = 't15',
        **kwargs,
    )


def compute_loss_phase2(model, bundle, **kwargs):
    """Phase-2 loss: 1-second collapse data, H trainable."""
    return compute_loss(
        model,
        t_norm    = bundle.t1s_norm,
        Pm_norm   = bundle.pm1s_norm,
        Pe_norm   = bundle.pe1s_norm,
        rf_norm   = bundle.rf1s_norm,
        f_obs_norm= bundle.f1s_norm,
        scalers   = bundle.scalers,
        t_key     = 't1s',
        **kwargs,
    )
