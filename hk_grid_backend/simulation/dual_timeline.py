"""
DualTimelineSimulation — runs two parallel simulations of the same disturbance.

Timeline A: NO_INTERVENTION   (traditional reactive, expected: blackout)
Timeline B: PINN_INTERVENTION (PINN-guided dispatch, expected: stable)
"""

import copy
import logging
from typing import List, Optional

from config.hk_grid import get_baseline_copy, get_ev_stations_copy
from config.disturbances import DISTURBANCE_EVENTS
from pinn.model import GridPINN
from simulation.simulator import GridSimulator
from simulation.dispatch import DispatchEngine
from simulation.validator import PhysicsValidator

logger = logging.getLogger(__name__)

DISTURBANCE_T = 30   # seconds into simulation when event fires


class DualTimelineSimulation:
    """
    Executes the same disturbance on two grid instances:
      A — no intervention  (human / reactive only)
      B — PINN-guided dispatch

    Returns frame-by-frame comparison dict, outcomes, and KPIs.
    """

    def __init__(self, pinn_model: GridPINN):
        self.pinn     = pinn_model
        self.dispatch = DispatchEngine()
        self.validator = PhysicsValidator()

    def run(self, scenario_name: str, duration_s: int = 300,
            start_t: float = 3 * 3600) -> dict:
        """
        start_t: simulation clock offset in seconds (default 3 h = 03:00).
                 Sets the hour used for the demand profile lookup.
                 Hour 3 has minimum demand (2 990 MW) giving maximum
                 thermal headroom for governor primary-frequency response.
        """
        if scenario_name not in DISTURBANCE_EVENTS:
            raise ValueError(f"Unknown scenario '{scenario_name}'. "
                             f"Available: {list(DISTURBANCE_EVENTS.keys())}")

        disturbance = DISTURBANCE_EVENTS[scenario_name]

        # Each timeline gets its own PINN copy so online H adaptation
        # (estimate_H_from_window) evolves independently per scenario.
        pinn_A = copy.deepcopy(self.pinn)
        pinn_B = copy.deepcopy(self.pinn)
        sim_A = GridSimulator(get_baseline_copy(), get_ev_stations_copy(), pinn_A,
                              start_t=start_t)
        sim_B = GridSimulator(get_baseline_copy(), get_ev_stations_copy(), pinn_B,
                              start_t=start_t)

        frames: List[dict] = []
        pending_actions_B: List[dict] = []   # actions approved but waiting on lead time
        b_actions_applied: set = set()

        for step in range(duration_s):
            t = step   # frame index = seconds since simulation start
            event = disturbance if step == DISTURBANCE_T else None

            # -- Timeline A: no intervention (cascade relay trips → blackout)
            state_A = sim_A.step(disturbance=event)

            # -- Timeline B: PINN-guided
            state_B = sim_B.step(disturbance=event)

            actions_this_step: List[dict] = []
            intervention_triggered = False

            delta_P_B = state_B.Pm - state_B.Pe

            # ── PINN closed-loop trajectory regulation ───────────────────
            # Trigger on EITHER:
            #   (a) PINN-predicted nadir < 49.5 Hz — purely predictive; fires
            #       the moment the physics rollout sees an upcoming shortfall,
            #       even before frequency has moved at all.
            #   (b) df/dt < −0.02 Hz/s — safety net for excursions that develop
            #       faster than the trajectory window can project.
            # Because the trajectory is ramp-aware, condition (a) fires at the
            # very first step the ramp appears in the PINN's lookahead, giving
            # slow-start assets (CCGTs, SC) the maximum possible lead time.
            traj = state_B.trajectory_60s
            traj_nadir = min(traj) if traj else state_B.f - abs(state_B.df_dt) * 60

            if traj_nadir < 49.5 or state_B.df_dt < -0.02:
                gov_types = ("coal", "gas_ccgt", "nuclear")
                thermal = [
                    s for s in sim_B.get_all_sources()
                    if s["online"] and s.get("type") in gov_types
                ]
                gov_cap_reg      = sum(s["capacity_mw"] for s in thermal)
                gov_headroom_reg = sum(
                    max(0.0, s["capacity_mw"] - s.get("current_output_mw", 0))
                    for s in thermal
                )
                gen_ramps = [ev for ev in sim_B._ramp_events
                             if ev.get("kind") == "generation"]
                dem_ramps = [ev for ev in sim_B._ramp_events
                             if ev.get("kind") not in ("generation", "generation_ramp_up")]

                reg_actions = self.dispatch.regulate_on_trajectory(
                    trajectory=traj,
                    f0=state_B.f,
                    Pm_eff=state_B.Pm_eff,
                    Pe=state_B.Pe,
                    pinn_model=sim_B.pinn,
                    gov_cap=gov_cap_reg,
                    gov_output_init=sim_B._gov_output,
                    gov_headroom=gov_headroom_reg,
                    gen_ramp_mw=sum(ev["remaining_mw"] for ev in gen_ramps),
                    gen_ramp_rate=sum(ev["rate_per_s"]   for ev in gen_ramps),
                    dem_ramp_mw=sum(ev["remaining_mw"] for ev in dem_ramps),
                    dem_ramp_rate=sum(ev["rate_per_s"]   for ev in dem_ramps),
                )

                for action in reg_actions:
                    aid = action["id"]
                    if aid in b_actions_applied:
                        continue
                    if aid in [p["id"] for p in pending_actions_B]:
                        continue
                    intervention_triggered = True
                    lead = action.get("lead_time_s", 0)
                    pending_actions_B.append({
                        **action,
                        "description": (
                            f"PINN regulation: {action['description']} "
                            f"(nadir {action['_baseline_nadir_hz']:.2f}→"
                            f"{action['_predicted_nadir_hz']:.2f} Hz)"
                        ),
                        "scheduled_t": step + int(lead),
                    })
                    logger.info(
                        "PINN regulated '%s' queued at t=%ds  "
                        "predicted nadir %.2f→%.2f Hz (+%.3f Hz),  "
                        "fires at t=%ds",
                        aid, t,
                        action["_baseline_nadir_hz"], action["_predicted_nadir_hz"],
                        action["_improvement_hz"],
                        step + int(lead),
                    )

            # ── Reactive fallback: EV shedding only ─────────────────────
            # The PINN regulation loop handles pre-positioning of all slow
            # assets.  This path only applies the fastest sub-2-second
            # action (EV shedding) once the excursion is confirmed, as a
            # last-resort safety net if the regulation loop hasn't yet fired.
            if state_B.risk_level in ("ALERT", "CRITICAL"):
                for action in self.dispatch.select_actions(
                    state_B.risk_score, state_B.H_physical,
                    delta_P_B, state_B.trajectory_60s,
                ):
                    aid = action["id"]
                    if aid in b_actions_applied:
                        continue
                    if action.get("lead_time_s", 0) >= 2:
                        continue   # slow assets already handled by regulation loop
                    validation = self.validator.validate(state_B, [action], sim_B)
                    if validation["approved"]:
                        sim_B.apply_action(action)
                        b_actions_applied.add(aid)
                        actions_this_step.append(action)
                        intervention_triggered = True

            # Apply any pending lead-time actions that are now ready
            ready = [p for p in pending_actions_B if p.get("scheduled_t", 9999) <= step]
            for action in ready:
                aid = action["id"]
                if aid not in b_actions_applied:
                    sim_B.apply_action(action)
                    b_actions_applied.add(aid)
                    actions_this_step.append(action)
                    logger.info("Action '%s' executed at step %ds", aid, step)
                pending_actions_B.remove(action)

            frames.append({
                "t":                      t,
                "A":                      state_A.to_dict(),
                "B":                      state_B.to_dict(),
                "intervention_triggered": intervention_triggered,
                "actions_taken":          [a["description"] for a in actions_this_step],
            })

        final_f_A = frames[-1]["A"]["f"]
        final_f_B = frames[-1]["B"]["f"]

        def _outcome(f, is_pinn):
            if f < 49.0:  return "BLACKOUT"   # includes f=0 (total collapse)
            if f < 49.4:  return "DEGRADED"   # partial recovery, not yet nominal
            return "STABLE"

        return {
            "scenario":   scenario_name,
            "duration_s": duration_s,
            "frames":     frames,
            "outcome_A":  _outcome(final_f_A, False),
            "outcome_B":  _outcome(final_f_B, True),
            "kpis":       self._compute_kpis(frames),
        }

    # ------------------------------------------------------------------

    def _compute_kpis(self, frames: List[dict]) -> dict:
        a_states = [f["A"] for f in frames]
        b_states = [f["B"] for f in frames]
        all_actions = [a for f in frames for a in f["actions_taken"]]

        ccgt_starts  = sum(1 for a in all_actions if "CCGT" in a)
        ev_shed      = sum(1 for a in all_actions if "EV" in a)

        co2_avoided  = ccgt_starts * 400 * (10 / 60) * 490   # approx kg
        cost_saved   = ccgt_starts * 400 * (10 / 60) * 85    # approx USD

        def _min_f(states):
            return min(s["f"] for s in states)

        def _max_rocof(states):
            return max(abs(s["df_dt"]) for s in states)

        def _min_h(states):
            return min(s["H_physical"] for s in states)

        return {
            "co2_avoided_kg":         round(co2_avoided, 1),
            "cost_saved_usd":         round(cost_saved, 2),
            "ev_stations_interrupted": 150 if ev_shed > 0 else 0,
            "max_rocof_A":            round(_max_rocof(a_states), 4),
            "max_rocof_B":            round(_max_rocof(b_states), 4),
            "min_frequency_A":        round(_min_f(a_states), 3),
            "min_frequency_B":        round(_min_f(b_states), 3),
            "H_min_A":                round(_min_h(a_states), 3),
            "H_min_B":                round(_min_h(b_states), 3),
            "time_to_alert_s":        next(
                (f["t"] for f in frames if f["B"]["risk_level"] == "ALERT"), None
            ),
            "time_to_critical_s":     next(
                (f["t"] for f in frames if f["B"]["risk_level"] == "CRITICAL"), None
            ),
        }
