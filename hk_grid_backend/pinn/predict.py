"""
PINN-based trajectory prediction and H estimation.
"""

from typing import List, Tuple
import torch

from .model import GridPINN

F0      = 50.0
S_BASE  = 12000.0   # HK grid
DROOP   = 0.05      # governor droop R = 5 %
TAU_GOV = 8.0       # governor first-order time constant [s]


def predict_trajectory(
    model: GridPINN,
    t_start: float,
    f0: float,
    Pm: float,
    Pe: float,
    renewable_frac: float,
    H_prior: float,
    gov_cap: float = 0.0,
    gov_output_init: float = 0.0,
    gov_headroom: float = 0.0,
    gen_ramp_mw: float = 0.0,    # remaining MW of in-progress generation ramp (negative = loss)
    gen_ramp_rate: float = 0.0,  # MW/s rate of that ramp (negative for loss)
    dem_ramp_mw: float = 0.0,    # remaining MW of in-progress demand ramp (positive = increase)
    dem_ramp_rate: float = 0.0,  # MW/s rate (positive for increase)
    horizon_s: int = 60,
    dt: float = 1.0,
) -> List[float]:
    """
    Physics-based frequency trajectory using the PINN's online-adapted H.

    Integrates the swing equation step-by-step from f0, including the same
    first-order governor lag (R=5%, tau=8s) used by the simulator.  The PINN's
    role is H estimation (via estimate_H_from_window); the trajectory is
    physics-correct by construction rather than relying on the untrained NN.

    gov_headroom: max available upward MW reserve (clamps the droop target
                  exactly as the real simulator does; 0 means unconstrained).

    gen_ramp_mw / gen_ramp_rate: any in-progress generation ramp (e.g. wind
        typhoon curtailment) carried forward into the lookahead window so the
        prediction sees the full upcoming deficit, not just the current snapshot.
    dem_ramp_mw / dem_ramp_rate: similarly for demand ramps (e.g. datacenter
        spike already in progress).  Both ramps are applied linearly until the
        remaining MW is exhausted.
    """
    H       = model.get_H_estimate()
    gov_out = gov_output_init
    f       = f0
    traj    = [f0]

    headroom_up = gov_headroom if gov_headroom > 0 else float('inf')

    for i in range(horizon_s):
        t_ahead = (i + 1) * dt

        # Carry forward ongoing generation ramp (e.g. wind curtailment still ramping)
        Pm_delta = 0.0
        if gen_ramp_rate < 0 and gen_ramp_mw < 0:
            Pm_delta = max(gen_ramp_mw, gen_ramp_rate * t_ahead)  # gen_ramp_mw is the floor

        # Carry forward ongoing demand ramp (e.g. datacenter spike already ramping)
        Pe_delta = 0.0
        if dem_ramp_rate > 0 and dem_ramp_mw > 0:
            Pe_delta = min(dem_ramp_mw, dem_ramp_rate * t_ahead)

        Pm_t = max(0.0, Pm + Pm_delta)
        Pe_t = Pe + Pe_delta

        if gov_cap > 0:
            delta_f    = F0 - f
            gov_target = (1.0 / DROOP) * (delta_f / F0) * gov_cap
            gov_target = min(gov_target, headroom_up)    # can't exceed available reserve
            gov_target = max(gov_target, -Pm_t)          # can't withdraw more than current output
            alpha      = dt / (TAU_GOV + dt)
            gov_out   += alpha * (gov_target - gov_out)
            Pm_eff     = Pm_t + gov_out
        else:
            Pm_eff = Pm_t

        df_dt = (F0 / (2.0 * H * S_BASE)) * (Pm_eff - Pe_t)
        f     = max(0.0, min(52.0, f + df_dt * dt))
        traj.append(f)

    return traj


def estimate_H_from_window(
    model: GridPINN,
    t_window: List[float],
    f_window: List[float],
    Pm_window: List[float],
    Pe_window: List[float],
    renewable_frac: float,
    n_steps: int = 200,
    lr: float = 1e-3,
) -> Tuple[float, float]:
    """
    Fine-tune log_H on a recent observed window.
    Returns (H_estimate, physics_residual).

    Only log_H is updated — network weights stay frozen.
    Useful for real-time H tracking during live operation.
    """
    model.eval()
    for p in model.net.parameters():
        p.requires_grad_(False)
    model.log_H.requires_grad_(True)

    t_t  = torch.tensor(t_window,     dtype=torch.float32).requires_grad_(True)
    f_t  = torch.tensor(f_window,     dtype=torch.float32)
    Pm_t = torch.tensor(Pm_window,    dtype=torch.float32)
    Pe_t = torch.tensor(Pe_window,    dtype=torch.float32)
    rf_t = torch.full((len(t_window),), renewable_frac, dtype=torch.float32)
    Hp_t = torch.full((len(t_window),), model.H.item(), dtype=torch.float32)

    optimizer = torch.optim.Adam([model.log_H], lr=lr)

    for _ in range(n_steps):
        optimizer.zero_grad()
        t_req = t_t.detach().requires_grad_(True)
        f_pred = model(t_req, Pm_t, Pe_t, rf_t, Hp_t)

        df_dt = torch.autograd.grad(
            f_pred, t_req,
            grad_outputs=torch.ones_like(f_pred),
            create_graph=True,
        )[0]

        H = model.H
        df_dt_phys = (F0 / (2.0 * H * S_BASE)) * (Pm_t - Pe_t)
        loss = torch.nn.MSELoss()(df_dt.squeeze(), df_dt_phys.squeeze())
        loss.backward()
        optimizer.step()

    # Unfreeze network for next training cycle
    for p in model.net.parameters():
        p.requires_grad_(True)

    phys_residual = loss.item()
    return model.H.item(), phys_residual
