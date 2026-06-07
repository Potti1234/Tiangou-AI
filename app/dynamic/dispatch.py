from __future__ import annotations

from typing import Any

from app.dynamic.pinn_predict import DROOP, F0, predict_trajectory

S_BASE = 12000.0


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
            if len(selected) >= 8:
                break
        return selected

    def regulate_on_trajectory(
        self,
        trajectory: list[float],
        f0: float,
        Pm_eff: float,
        Pe: float,
        pinn_model: Any,
        gov_cap: float,
        gov_output_init: float,
        gov_headroom: float,
        gen_ramp_mw: float = 0.0,
        gen_ramp_rate: float = 0.0,
        dem_ramp_mw: float = 0.0,
        dem_ramp_rate: float = 0.0,
        target_nadir: float = 49.5,
    ) -> list[dict[str, Any]]:
        if not trajectory:
            return []

        baseline_nadir = min(trajectory)
        if baseline_nadir >= target_nadir:
            return []

        if gov_cap > 0:
            shortfall = target_nadir - baseline_nadir
            needed_mw = max(0.0, shortfall * gov_cap / (DROOP * F0))
        else:
            needed_mw = abs(Pe - Pm_eff)

        candidates: list[dict[str, Any]] = []
        for action in self.actions:
            action_type = action["type"]
            d_pm = 0.0
            d_pe = 0.0
            effective_lead = int(action.get("lead_time_s") or 0)

            if action_type in {"demand_reduction", "demand_reduction_direct"}:
                d_pe = float(action.get("delta_mw") or 0.0)
                horizon = max(60, effective_lead + 30)
            elif action_type == "generation_increase":
                d_pm = float(action.get("delta_mw") or 0.0)
                ramp_time = _generation_ramp_time_s(action)
                horizon = max(60, effective_lead + ramp_time + 30)
            else:
                continue

            hypo_traj = predict_trajectory(
                pinn_model,
                t_start=0,
                f0=f0,
                Pm=Pm_eff + d_pm,
                Pe=Pe + d_pe,
                renewable_frac=0.0,
                H_prior=0.0,
                gov_cap=gov_cap,
                gov_output_init=gov_output_init,
                gov_headroom=gov_headroom,
                gen_ramp_mw=gen_ramp_mw,
                gen_ramp_rate=gen_ramp_rate,
                dem_ramp_mw=dem_ramp_mw,
                dem_ramp_rate=dem_ramp_rate,
                horizon_s=horizon,
            )
            hypo_nadir = min(hypo_traj)
            improvement = hypo_nadir - baseline_nadir
            candidates.append({
                **action,
                "_baseline_nadir_hz": round(baseline_nadir, 3),
                "_predicted_nadir_hz": round(hypo_nadir, 3),
                "_improvement_hz": round(improvement, 4),
            })

        candidates.sort(key=lambda action: (int(action.get("lead_time_s") or 0), float(action.get("cost_per_mwh") or 0.0)))

        selected: list[dict[str, Any]] = []
        covered_mw = 0.0
        for action in candidates:
            if float(action["_improvement_hz"]) <= 0.02 and action["type"] != "demand_reduction":
                continue
            selected.append(action)
            covered_mw += abs(float(action.get("delta_mw") or 0.0))
            if covered_mw >= needed_mw:
                break

        return selected


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
        "description": "Curtail flexible demand (-800 MW assumption)",
        "type": "demand_reduction_direct",
        "delta_mw": -800,
        "delta_H": 0.0,
        "lead_time_s": 1,
        "cost_per_mwh": 15,
        "co2_kg_per_mwh": 0,
    })
    candidates = sorted(
        [
            source for source in grid_config.get("sources", [])
            if source.get("type") in {"coal", "gas_ccgt", "other_dispatchable", "generic_capacity_equivalent"} and float(source.get("capacity_mw") or 0.0) > 0
        ],
        key=lambda source: float(source.get("capacity_mw") or 0.0),
        reverse=True,
    )
    for index, source in enumerate(candidates[:6], start=1):
        delta = float(source.get("capacity_mw") or 0.0)
        actions.append({
            "id": f"start_dispatchable_{index}",
            "description": f"Fast redispatch {source.get('name')} (+{delta:.0f} MW)",
            "type": "generation_increase",
            "source": source.get("name"),
            "delta_mw": delta,
            "delta_H": delta * float(source.get("H") or 0.0) / S_BASE,
            "lead_time_s": _lead_time_for_source(source),
            "emergency": _lead_time_for_source(source) <= 5,
            "ramp_rate_mw_per_min": source.get("ramp_rate_mw_per_min"),
            "cost_per_mwh": 85,
            "co2_kg_per_mwh": 490,
        })
    return actions


def _lead_time_for_source(source: dict[str, Any]) -> int:
    source_type = source.get("type")
    if source_type in {"gas_ccgt", "other_dispatchable", "generic_capacity_equivalent"}:
        return 60
    if source_type == "coal":
        return 120
    return 30


def _generation_ramp_time_s(action: dict[str, Any]) -> int:
    if action.get("emergency"):
        return 0
    delta_mw = abs(float(action.get("delta_mw") or 0.0))
    ramp_rate_mw_per_min = float(action.get("ramp_rate_mw_per_min") or 0.0)
    if ramp_rate_mw_per_min <= 0:
        return 60
    return max(1, int(delta_mw / ramp_rate_mw_per_min * 60))
