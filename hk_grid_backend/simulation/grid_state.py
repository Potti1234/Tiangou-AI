"""GridState dataclass — a single timestep snapshot of HK grid."""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict


@dataclass
class GridState:
    t: float                          # simulation time [s]
    f: float                          # grid frequency [Hz]
    H_physical: float                 # physical H from spinning sources [s]
    H_pinn: float                     # PINN-estimated H [s]
    Pm: float                         # raw generation (no governor) [MW]
    Pm_eff: float                     # generation + governor response [MW]
    Pe: float                         # total demand [MW]
    df_dt: float                      # RoCoF [Hz/s]
    trajectory_60s: List[float]       # PINN predicted f for next 60 s
    risk_score: float                 # composite [0, 1]
    risk_level: str                   # NORMAL / WATCH / ALERT / CRITICAL
    renewable_fraction: float         # fraction of generation from wind + solar
    active_sources: List[Dict]        # summary of online sources
    ev_stations_active: int           # count of active EV chargers
    freq_band: str                    # NORMAL / ALERT / UFLS / BLACKOUT
    demand_extra_mw: float = 0.0      # accumulated demand disturbance [MW]

    def to_dict(self) -> dict:
        d = asdict(self)
        # Keep trajectory_60s as list — JSON serialisable already
        return d
