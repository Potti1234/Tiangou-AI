from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class GridState:
    t: float
    f: float
    H_physical: float
    H_pinn: float
    Pm: float
    Pm_eff: float
    Pe: float
    df_dt: float
    trajectory_60s: list[float]
    risk_score: float
    risk_level: str
    renewable_fraction: float
    active_sources: list[dict[str, Any]]
    ev_stations_active: int
    freq_band: str
    demand_extra_mw: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

