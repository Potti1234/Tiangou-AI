from __future__ import annotations

import copy
from typing import Any

from app.dynamic.dispatch import DispatchEngine
from app.dynamic.simulator import GridSimulator
from app.dynamic.validator import PhysicsValidator

DISTURBANCE_T = 30


class DualTimelineSimulation:
    def __init__(
        self,
        pinn_model: Any,
        grid_config: dict[str, Any],
        demand_profile_mw: dict[int, float],
        ev_stations: list[dict[str, Any]],
    ):
        self.pinn = pinn_model
        self.grid_config = grid_config
        self.demand_profile_mw = demand_profile_mw
        self.ev_stations = ev_stations
        self.dispatch = DispatchEngine(grid_config, sum(float(s.get("max_load_mw") or 0.0) for s in ev_stations))
        self.validator = PhysicsValidator()

    def run(self, scenario: dict[str, Any], duration_s: int = 300, start_hour: int = 16) -> dict[str, Any]:
        pinn_A = copy.deepcopy(self.pinn)
        pinn_B = copy.deepcopy(self.pinn)
        sim_A = GridSimulator(copy.deepcopy(self.grid_config), self.demand_profile_mw, self.ev_stations, pinn_A, start_t=start_hour * 3600)
        sim_B = GridSimulator(copy.deepcopy(self.grid_config), self.demand_profile_mw, self.ev_stations, pinn_B, start_t=start_hour * 3600)
        frames: list[dict[str, Any]] = []
        pending_actions: list[dict[str, Any]] = []
        applied: set[str] = set()
        for step in range(duration_s):
            event = scenario if step == DISTURBANCE_T else None
            state_A = sim_A.step(disturbance=event)
            state_B = sim_B.step(disturbance=event)
            actions_this_step: list[dict[str, Any]] = []
            intervention_triggered = False
            trajectory = state_B.trajectory_60s
            if (trajectory and min(trajectory) < 49.5) or state_B.df_dt < -0.02 or state_B.risk_level in {"ALERT", "CRITICAL"}:
                for action in self.dispatch.regulate_on_trajectory(
                    trajectory,
                    f0=state_B.f,
                    Pm_eff=state_B.Pm_eff,
                    Pe=state_B.Pe,
                    pinn_model=sim_B.pinn,
                    gov_cap=_governor_capacity(sim_B),
                    gov_output_init=sim_B._gov_output,
                    gov_headroom=_governor_headroom(sim_B),
                    gen_ramp_mw=sum(float(ramp["remaining_mw"]) for ramp in _generation_ramps(sim_B)),
                    gen_ramp_rate=sum(float(ramp["rate_per_s"]) for ramp in _generation_ramps(sim_B)),
                    dem_ramp_mw=sum(float(ramp["remaining_mw"]) for ramp in _demand_ramps(sim_B)),
                    dem_ramp_rate=sum(float(ramp["rate_per_s"]) for ramp in _demand_ramps(sim_B)),
                ):
                    if action["id"] in applied or action["id"] in {pending["id"] for pending in pending_actions}:
                        continue
                    validation = self.validator.validate(state_B, [action], sim_B)
                    if validation["approved"] or action.get("lead_time_s", 0) <= 5 or float(action.get("_improvement_hz") or 0.0) > 0.02:
                        pending_actions.append({
                            **action,
                            "description": _regulation_description(action),
                            "scheduled_t": step + int(action.get("lead_time_s") or 0),
                        })
                        intervention_triggered = True
                if not intervention_triggered and state_B.risk_level in {"ALERT", "CRITICAL"}:
                    for action in self.dispatch.select_actions(state_B.risk_score, state_B.H_physical, state_B.Pm - state_B.Pe, trajectory):
                        if action["id"] in applied or action["id"] in {pending["id"] for pending in pending_actions}:
                            continue
                        if int(action.get("lead_time_s") or 0) > 5:
                            continue
                        validation = self.validator.validate(state_B, [action], sim_B)
                        if validation["approved"] or action.get("lead_time_s", 0) <= 5:
                            pending_actions.append({**action, "scheduled_t": step + int(action.get("lead_time_s") or 0)})
                            intervention_triggered = True
            ready = [action for action in pending_actions if action["scheduled_t"] <= step]
            for action in ready:
                sim_B.apply_action(action)
                applied.add(action["id"])
                actions_this_step.append(action)
                pending_actions.remove(action)
            frames.append({
                "t": step,
                "A": state_A.to_dict(),
                "B": state_B.to_dict(),
                "intervention_triggered": intervention_triggered,
                "actions_taken": [action["description"] for action in actions_this_step],
            })
        return {
            "scenario": scenario["id"],
            "duration_s": duration_s,
            "frames": frames,
            "outcome_A": _outcome(frames[-1]["A"]["f"]),
            "outcome_B": _outcome(frames[-1]["B"]["f"]),
            "kpis": _compute_kpis(frames),
        }


def _outcome(f: float) -> str:
    if f < 49.0:
        return "BLACKOUT"
    if f < 49.4:
        return "DEGRADED"
    return "STABLE"


def _compute_kpis(frames: list[dict[str, Any]]) -> dict[str, Any]:
    a_states = [frame["A"] for frame in frames]
    b_states = [frame["B"] for frame in frames]
    actions = [action for frame in frames for action in frame["actions_taken"]]
    return {
        "co2_avoided_kg": round(sum(1 for action in actions if "Increase" in action) * 32666.7, 1),
        "cost_saved_usd": round(sum(1 for action in actions if "Increase" in action) * 5666.67, 2),
        "ev_stations_interrupted": sum(1 for action in actions if "EV" in action),
        "intervention_count": len(actions),
        "max_rocof_A": round(max(abs(state["df_dt"]) for state in a_states), 4),
        "max_rocof_B": round(max(abs(state["df_dt"]) for state in b_states), 4),
        "min_frequency_A": round(min(state["f"] for state in a_states), 3),
        "min_frequency_B": round(min(state["f"] for state in b_states), 3),
        "H_min_A": round(min(state["H_physical"] for state in a_states), 3),
        "H_min_B": round(min(state["H_physical"] for state in b_states), 3),
        "time_to_alert_s": next((frame["t"] for frame in frames if frame["B"]["risk_level"] == "ALERT"), None),
        "time_to_critical_s": next((frame["t"] for frame in frames if frame["B"]["risk_level"] == "CRITICAL"), None),
    }


def _governor_sources(simulator: GridSimulator) -> list[dict[str, Any]]:
    return [
        source for source in simulator.get_all_sources()
        if source.get("online") and source.get("type") in {"coal", "gas_ccgt", "nuclear", "imports", "other_dispatchable", "generic_capacity_equivalent"}
    ]


def _governor_capacity(simulator: GridSimulator) -> float:
    return sum(float(source.get("capacity_mw") or 0.0) for source in _governor_sources(simulator))


def _governor_headroom(simulator: GridSimulator) -> float:
    return sum(
        max(0.0, float(source.get("capacity_mw") or 0.0) - float(source.get("current_output_mw") or 0.0))
        for source in _governor_sources(simulator)
    )


def _generation_ramps(simulator: GridSimulator) -> list[dict[str, Any]]:
    return [ramp for ramp in simulator._ramp_events if ramp.get("kind") == "generation"]


def _demand_ramps(simulator: GridSimulator) -> list[dict[str, Any]]:
    return [ramp for ramp in simulator._ramp_events if ramp.get("kind") not in {"generation", "generation_ramp_up"}]


def _regulation_description(action: dict[str, Any]) -> str:
    return (
        f"PINN regulation: {action['description']} "
        f"(nadir {action['_baseline_nadir_hz']:.2f}->{action['_predicted_nadir_hz']:.2f} Hz)"
    )
