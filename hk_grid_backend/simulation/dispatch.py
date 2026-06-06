"""
DispatchEngine — Layer 5.

Selects minimum-cost intervention set given current risk state.
Priority: EV shedding (free) → Gas CCGT (adds H) → SC (pure H)
"""

from typing import List

S_BASE = 12000.0


INTERVENTION_ACTIONS = [
    {
        "id": "start_bess",
        "description": "Dispatch battery storage (+200 MW instant response)",
        "type": "generation_increase",
        "source": "HK Grid Battery Storage",
        "delta_mw": +200,
        "delta_H": 0.0,            # inverter-coupled, no inertia contribution
        "lead_time_s": 0,          # sub-cycle response — fires in the same step
        "cost_per_mwh": 20,
        "co2_kg_per_mwh": 0,
    },
    {
        "id": "shed_ev_charging",
        "description": "Interrupt EV charging stations (−22.5 MW demand reduction)",
        "type": "demand_reduction",
        "delta_mw": -22.5,
        "delta_H": 0.0,
        "lead_time_s": 1,
        "cost_per_mwh": 0,
        "co2_kg_per_mwh": 0,
        "affects_ev_stations": True,
    },
    {
        "id": "fast_demand_response",
        "description": "Interruptible load curtailment (−200 MW industrial demand)",
        "type": "demand_reduction_direct",
        "delta_mw": -200,
        "delta_H": 0.0,
        "lead_time_s": 5,
        "cost_per_mwh": 15,
        "co2_kg_per_mwh": 0,
    },
    {
        "id": "start_gas_ccgt_1",
        "description": "Start Black Point CCGT 2 (+400 MW, +H)",
        "type": "generation_increase",
        "source": "Black Point CCGT 2",
        "delta_mw": +400,
        "delta_H": 400 * 4.0 / S_BASE,
        "lead_time_s": 120,
        "cost_per_mwh": 85,
        "co2_kg_per_mwh": 490,
    },
    {
        "id": "start_gas_ccgt_2",
        "description": "Start Black Point CCGT 3 (+400 MW, +H)",
        "type": "generation_increase",
        "source": "Black Point CCGT 3",
        "delta_mw": +400,
        "delta_H": 400 * 4.0 / S_BASE,
        "lead_time_s": 120,
        "cost_per_mwh": 85,
        "co2_kg_per_mwh": 490,
    },
    {
        "id": "enable_synchronous_condenser",
        "description": "Enable SC Unit 1 (pure inertia, +H, no generation)",
        "type": "inertia_only",
        "source": "SC Unit 1",
        "delta_mw": 0,
        "delta_H": 800 * 4.0 / S_BASE,   # 800 MVA condenser
        "lead_time_s": 30,
        "cost_per_mwh": 5,
        "co2_kg_per_mwh": 0,
    },
]

_ACTION_MAP = {a["id"]: a for a in INTERVENTION_ACTIONS}


class DispatchEngine:

    def select_actions(
        self,
        risk_score: float,
        H: float,
        delta_P: float,
        trajectory: list,
    ) -> List[dict]:
        """
        Greedy selection: cheapest/fastest actions first that project
        H back above 2.0 s and frequency within 49.8–50.2 Hz.

        Returns list of action dicts (full objects, not just ids).
        """
        selected_ids: List[str] = []

        if risk_score >= 0.6:   # CRITICAL
            selected_ids.append("shed_ev_charging")
            selected_ids.append("enable_synchronous_condenser")
            selected_ids.append("start_gas_ccgt_1")
            selected_ids.append("start_gas_ccgt_2")

        elif risk_score >= 0.3:  # ALERT
            # SC always pre-positioned at ALERT — 30 s lead means it can help
            # the recovery oscillations even when it can't prevent the nadir
            selected_ids.append("enable_synchronous_condenser")
            if delta_P < -200:   # meaningful generation deficit
                selected_ids.append("start_gas_ccgt_1")
            if delta_P < -500:   # large deficit — pre-position second CCGT
                selected_ids.append("start_gas_ccgt_2")

        return [_ACTION_MAP[aid] for aid in selected_ids if aid in _ACTION_MAP]

    def select_predictive_actions(
        self,
        delta_P: float,
        physics_min_f: float,
    ) -> List[dict]:
        """
        Pre-position assets when physics extrapolation signals an approaching
        excursion — before risk_score reaches ALERT.

        Three tiers:
          1. Fast demand response (5 s): fires before the nadir, lifts the
             frequency floor by −200 MW load curtailment.
          2. SC (30 s): adds inertia, slows RoCoF during recovery oscillations.
          3. CCGTs (60 s hot-standby vs 120 s cold-start): PINN advance warning
             gives operators time to pre-warm turbines — CCGTs arrive 60 s
             earlier than in reactive dispatch, driving faster recovery.
        """
        actions: List[dict] = []

        # Always: fast demand response — fires at t+5, before the nadir
        actions.append(_ACTION_MAP["fast_demand_response"])

        # Always: SC for inertia support
        actions.append(_ACTION_MAP["enable_synchronous_condenser"])

        # CCGTs with hot-standby lead time (60 s instead of cold-start 120 s)
        if physics_min_f < 49.3 or delta_P < -200:
            actions.append({**_ACTION_MAP["start_gas_ccgt_1"], "lead_time_s": 60})

        if physics_min_f < 49.0 or delta_P < -500:
            actions.append({**_ACTION_MAP["start_gas_ccgt_2"], "lead_time_s": 60})

        return actions

    # Hot-standby lead time for generation assets when PINN dispatches early.
    # The PINN fires during df/dt < −0.02 which gives operators enough advance
    # notice to pre-warm turbines — 60 s vs 120 s cold-start.
    _HOT_STANDBY_S = 60

    def regulate_on_trajectory(
        self,
        trajectory: List[float],
        f0: float,
        Pm_eff: float,
        Pe: float,
        pinn_model,
        gov_cap: float,
        gov_output_init: float,
        gov_headroom: float,
        gen_ramp_mw: float = 0.0,
        gen_ramp_rate: float = 0.0,
        dem_ramp_mw: float = 0.0,
        dem_ramp_rate: float = 0.0,
        target_nadir: float = 49.5,
    ) -> List[dict]:
        """
        Trajectory-driven closed-loop regulation.

        For each available intervention, runs a hypothetical trajectory with
        that action applied (using the PINN physics rollout) and measures the
        predicted nadir improvement.  Generation assets use hot-standby lead
        (60 s) since the PINN fires early enough to pre-warm turbines.

        The evaluation horizon matches the action's effective lead time so that
        slow-start generation actions are assessed over a window long enough to
        capture when they actually arrive:
          • Fast actions  (lead ≤ 30 s): 60 s horizon
          • CCGTs (60 s hot-standby)   : 180 s horizon (nadir visible at t≈90)

        Because this is called every simulation step, each call already sees the
        updated Pm/Pe reflecting any previously applied actions — the loop is
        naturally closed without needing separate integral tracking.
        """
        from pinn.predict import predict_trajectory, DROOP, F0 as FREQ0

        if not trajectory:
            return []

        baseline_nadir = min(trajectory)
        if baseline_nadir >= target_nadir:
            return []   # PINN says the grid is safe — no regulation needed

        # How much MW relief is needed to lift steady-state f by the shortfall?
        # From the droop equation: delta_f_ss = DROOP * needed_mw * F0 / gov_cap
        shortfall  = target_nadir - baseline_nadir          # Hz
        needed_mw  = shortfall * gov_cap / (DROOP * FREQ0)  # MW

        # Evaluate each action by running a hypothetical trajectory
        candidates = []
        for action in INTERVENTION_ACTIONS:
            atype = action["type"]
            dPe = dPm = 0.0

            if atype in ("demand_reduction", "demand_reduction_direct"):
                dPe = action["delta_mw"]     # negative — reduces effective demand
                effective_lead = action["lead_time_s"]
                horizon = max(60, effective_lead + 30)
            elif atype == "generation_increase":
                dPm = action["delta_mw"]     # positive — adds generation
                original_lead = action["lead_time_s"]
                if original_lead > 30:
                    # Slow-start asset (CCGT): override to hot-standby lead since
                    # the PINN dispatches early enough to pre-warm the turbine.
                    effective_lead = self._HOT_STANDBY_S
                    horizon = effective_lead + 120
                else:
                    # Fast-response asset (BESS, spinning reserve): keep its
                    # own lead time and a standard 60 s evaluation window.
                    effective_lead = original_lead
                    horizon = max(60, effective_lead + 30)
            elif atype == "inertia_only":
                # SC doesn't shift the steady-state nadir but slows RoCoF
                candidates.append({
                    **action,
                    "lead_time_s":         action["lead_time_s"],
                    "_baseline_nadir_hz":  round(baseline_nadir, 3),
                    "_predicted_nadir_hz": round(baseline_nadir + 0.05, 3),
                    "_improvement_hz":     0.05,
                })
                continue
            else:
                continue

            hypo_traj = predict_trajectory(
                pinn_model,
                t_start=0, f0=f0,
                Pm=Pm_eff + dPm,
                Pe=Pe + dPe,
                renewable_frac=0.0, H_prior=0.0,
                gov_cap=gov_cap, gov_output_init=gov_output_init,
                gov_headroom=gov_headroom,
                gen_ramp_mw=gen_ramp_mw, gen_ramp_rate=gen_ramp_rate,
                dem_ramp_mw=dem_ramp_mw, dem_ramp_rate=dem_ramp_rate,
                horizon_s=horizon,
            )
            hypo_nadir = min(hypo_traj)
            improvement = hypo_nadir - baseline_nadir
            candidates.append({
                **action,
                "lead_time_s":         effective_lead,
                "_baseline_nadir_hz":  round(baseline_nadir, 3),
                "_predicted_nadir_hz": round(hypo_nadir, 3),
                "_improvement_hz":     round(improvement, 4),
            })

        # Sort: cheapest/fastest first so we use the minimal intervention
        candidates.sort(key=lambda a: (a["lead_time_s"], a["cost_per_mwh"]))

        # Greedily select until predicted nadir is lifted above target
        selected: List[dict] = []
        covered_mw = 0.0
        for action in candidates:
            if action["_improvement_hz"] <= 0.02:
                continue   # negligible benefit — skip
            selected.append(action)
            covered_mw += abs(action.get("delta_mw", 0))
            if covered_mw >= needed_mw:
                break      # enough regulation dispatched

        return selected

    def get_all_actions(self) -> List[dict]:
        return INTERVENTION_ACTIONS
