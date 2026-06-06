from __future__ import annotations

from typing import Any


class DispatchEngine:
    def __init__(self, grid_config: dict[str, Any], ev_shed_mw: float):
        self.actions = _build_actions(grid_config, ev_shed_mw)

    def select_actions(self, risk_score: float, H: float, delta_P: float, trajectory: list[float]) -> list[dict[str, Any]]:
        if risk_score < 0.3 and (not trajectory or min(trajectory) >= 49.5):
            return []
        selected = []
        for action in self.actions:
            if action["type"].startswith("demand") or delta_P < -50:
                selected.append(action)
            if len(selected) >= 3:
                break
        return selected

    def regulate_on_trajectory(self, trajectory: list[float], *args, target_nadir: float = 49.5, **kwargs) -> list[dict[str, Any]]:
        if not trajectory or min(trajectory) >= target_nadir:
            return []
        return self.actions[:3]


def _build_actions(grid_config: dict[str, Any], ev_shed_mw: float) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if ev_shed_mw > 0:
        actions.append({
            "id": "shed_ev_charging",
            "description": f"Interrupt EV charging proxies (-{ev_shed_mw:.1f} MW demand)",
            "type": "demand_reduction",
            "delta_mw": -ev_shed_mw,
            "delta_H": 0.0,
            "lead_time_s": 1,
            "cost_per_mwh": 0,
            "co2_kg_per_mwh": 0,
        })
    actions.append({
        "id": "fast_demand_response",
        "description": "Curtail flexible demand (-200 MW assumption)",
        "type": "demand_reduction_direct",
        "delta_mw": -200,
        "delta_H": 0.0,
        "lead_time_s": 5,
        "cost_per_mwh": 15,
        "co2_kg_per_mwh": 0,
    })
    candidates = sorted(
        [
            source for source in grid_config.get("sources", [])
            if source.get("type") in {"gas_ccgt", "other_dispatchable", "generic_capacity_equivalent"} and float(source.get("capacity_mw") or 0.0) > 0
        ],
        key=lambda source: float(source.get("capacity_mw") or 0.0),
        reverse=True,
    )
    for index, source in enumerate(candidates[:2], start=1):
        delta = min(400.0, float(source.get("capacity_mw") or 0.0))
        actions.append({
            "id": f"start_dispatchable_{index}",
            "description": f"Increase {source.get('name')} (+{delta:.0f} MW)",
            "type": "generation_increase",
            "source": source.get("name"),
            "delta_mw": delta,
            "delta_H": delta * float(source.get("H") or 0.0) / 12000.0,
            "lead_time_s": 60,
            "cost_per_mwh": 85,
            "co2_kg_per_mwh": 490,
        })
    return actions

