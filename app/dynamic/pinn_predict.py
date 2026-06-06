from __future__ import annotations

from typing import Any

F0 = 50.0
S_BASE = 12000.0
DROOP = 0.05
TAU_GOV = 8.0


def predict_trajectory(
    model: Any,
    t_start: float,
    f0: float,
    Pm: float,
    Pe: float,
    renewable_frac: float,
    H_prior: float,
    gov_cap: float = 0.0,
    gov_output_init: float = 0.0,
    gov_headroom: float = 0.0,
    gen_ramp_mw: float = 0.0,
    gen_ramp_rate: float = 0.0,
    dem_ramp_mw: float = 0.0,
    dem_ramp_rate: float = 0.0,
    horizon_s: int = 60,
    dt: float = 1.0,
) -> list[float]:
    H = max(float(model.get_H_estimate()), 0.05)
    gov_out = gov_output_init
    f = f0
    traj = [f0]
    headroom_up = gov_headroom if gov_headroom > 0 else float("inf")

    for i in range(horizon_s):
        t_ahead = (i + 1) * dt
        Pm_delta = max(gen_ramp_mw, gen_ramp_rate * t_ahead) if gen_ramp_rate < 0 and gen_ramp_mw < 0 else 0.0
        Pe_delta = min(dem_ramp_mw, dem_ramp_rate * t_ahead) if dem_ramp_rate > 0 and dem_ramp_mw > 0 else 0.0
        Pm_t = max(0.0, Pm + Pm_delta)
        Pe_t = Pe + Pe_delta
        if gov_cap > 0:
            delta_f = F0 - f
            gov_target = (1.0 / DROOP) * (delta_f / F0) * gov_cap
            gov_target = min(gov_target, headroom_up)
            gov_target = max(gov_target, -Pm_t)
            gov_out += dt / (TAU_GOV + dt) * (gov_target - gov_out)
            Pm_eff = Pm_t + gov_out
        else:
            Pm_eff = Pm_t
        df_dt = (F0 / (2.0 * H * S_BASE)) * (Pm_eff - Pe_t)
        f = max(0.0, min(52.0, f + df_dt * dt))
        traj.append(f)
    return traj


def estimate_H_from_window(*args, **kwargs) -> tuple[float, float]:
    model = args[0]
    return float(model.get_H_estimate()), 0.0

