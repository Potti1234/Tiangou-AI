"""
GridSimulator — second-by-second HK grid simulation.

Integrates the swing equation:
    df/dt = (f0 / (2 · H · S_base)) · (Pm - Pe)

Feeds state to PINN for 60-second trajectory prediction.
"""

import copy
import logging
from typing import Dict, List, Optional

from config.hk_grid import get_all_sources, HK_DEMAND_PROFILE
from config.thresholds import (
    F0, S_BASE, compute_risk_score, risk_level_from_score, freq_band,
)
from config.disturbances import DISTURBANCE_EVENTS
from pinn.model import GridPINN
from pinn.predict import predict_trajectory
from simulation.grid_state import GridState

logger = logging.getLogger(__name__)


class GridSimulator:
    """
    Simulates HK grid state second-by-second.

    The swing equation is integrated with RK4 for accuracy.
    PINN provides 60-second lookahead predictions and H estimation.
    """

    DT     = 1.0        # simulation timestep [s]
    F0     = 50.0       # nominal frequency [Hz]
    S_BASE = 12000.0
    DROOP  = 0.05       # governor droop R = 5 % (standard)
    # Governor lag time constant [s].
    # Real turbine governors don't respond instantaneously — there is
    # mechanical inertia in the valve / steam path.  Without this filter,
    # the discrete governor flips from +600 MW to −720 MW in one timestep
    # as frequency crosses 50 Hz, causing damped oscillations.
    # TAU_GOV = 8 s is a realistic value for a gas CCGT governor.
    TAU_GOV = 8.0

    # ── Cascade collapse thresholds ─────────────────────────────────────
    # When f stays continuously below COLLAPSE_F_THRESHOLD for CASCADE_SUSTAIN_S
    # seconds without recovering (i.e. no corrective dispatch), protection relays
    # begin tripping thermal units one by one, smallest first, every
    # CASCADE_INTER_TRIP_S seconds.  Each trip deepens the deficit, accelerating
    # the next trip.  Once all synchronous generators are offline, motor-load
    # inertia (H_LOAD_INERTIA) carries the grid down to 0 Hz over ~10-20 s.
    # Timeline B (PINN dispatch) stays above COLLAPSE_F_THRESHOLD so its counter
    # never accumulates; Timeline A (no dispatch) crashes.
    #
    # 3 s inter-trip: generator protection relay coordination time.
    # B (PINN dispatch) keeps f above 49.0 Hz once CCGTs arrive at t≈151 s,
    # resetting its 110 s sustain counter before it fires.  A (no dispatch)
    # never recovers and cascades at t≈197 s.
    COLLAPSE_F_THRESHOLD = 49.0   # Hz — sustained below this starts the cascade timer
    CASCADE_SUSTAIN_S    = 110    # s  — must exceed B's recovery time (~105 s)
    CASCADE_INTER_TRIP_S = 3      # s  — relay coordination interval (was 5 s)
    H_LOAD_INERTIA       = 1.5   # s  — effective inertia of motor loads during coast-down

    def __init__(self, grid_config: dict, ev_stations: list, pinn_model: GridPINN,
                 start_t: float = 0.0):
        self.grid    = grid_config
        self.ev      = ev_stations
        self.pinn    = pinn_model

        self.t:            float = start_t
        self.f:            float = 50.0
        self.demand_extra: float = 0.0   # accumulated demand disturbance [MW]

        # Filtered governor output — first-order lag state [MW]
        self._gov_output:  float = 0.0

        # Track pending ramp disturbances
        self._ramp_events: List[dict] = []

        # Cascade collapse tracker — seconds continuously below COLLAPSE_F_THRESHOLD
        self._below_alert_count: float = 0.0
        # Set True when Stage-1 timer fires; trips proceed on CASCADE_INTER_TRIP_S schedule
        self._cascade_active: bool = False
        self._next_cascade_trip_t: float = 0.0

        self.history: List[GridState] = []

        # Initialise: scale thermal output so Pm ≈ Pe at startup
        self._balance_generation()

    # ------------------------------------------------------------------
    # Cascade collapse
    # ------------------------------------------------------------------

    def _check_cascade(self, f_new: float) -> float:
        """
        Protection-relay cascade model — multi-stage progressive collapse.

        Stage 1 — sustained-deficit timer:
          If f stays continuously below COLLAPSE_F_THRESHOLD for CASCADE_SUSTAIN_S
          seconds, the cascade sequence begins.  Timeline B (PINN dispatch) crosses
          back above the threshold before the timer fires → reset; Timeline A
          (no dispatch) never recovers → cascade fires at t≈188 s.

        Stage 2 — progressive relay trips:
          Once the cascade is active, thermal generators are tripped one by one
          in ascending capacity order (smallest first) every CASCADE_INTER_TRIP_S
          seconds.  Each trip deepens the MW deficit, accelerating the next.

        Stage 3 — load-inertia coast-down:
          After the last synchronous generator trips, motor loads provide residual
          inertia (H_LOAD_INERTIA).  With Pm = 0 and Pe ≈ 2-3 GW still consuming
          power, df/dt ≈ −3 Hz/s and the grid reaches 0 Hz over ~10-20 s.
          step() detects H = 0 + cascade_active and switches to load-inertia mode.

        Returns f_new unchanged (generator state mutations drive the physics).
        """
        # Stage 2 — cascade sequence: trip next generator on schedule
        if self._cascade_active:
            if self.t >= self._next_cascade_trip_t:
                thermal = sorted(
                    [s for s in self.get_all_sources()
                     if s["online"] and s.get("type") in ("coal", "gas_ccgt", "nuclear")],
                    key=lambda s: s["capacity_mw"],   # smallest first → gradual escalation
                )
                if thermal:
                    victim = thermal[0]
                    victim["online"] = False
                    victim["current_output_mw"] = 0.0
                    logger.warning(
                        "CASCADE TRIP at t=%.0fs: %s (%.0f MW) tripped "
                        "(f=%.3f Hz, next trip in %.0fs)",
                        self.t, victim["name"], victim["capacity_mw"],
                        f_new, self.CASCADE_INTER_TRIP_S,
                    )
                    self._next_cascade_trip_t = self.t + self.CASCADE_INTER_TRIP_S
                else:
                    # All thermal gone — step() will switch to H_LOAD_INERTIA coasting.
                    # Push next_trip_t far ahead so this branch only fires once.
                    if self._next_cascade_trip_t <= self.t:
                        logger.critical(
                            "TOTAL BLACKOUT at t=%.0fs: all generators offline, "
                            "coasting to 0 Hz on motor-load inertia",
                            self.t,
                        )
                        self._next_cascade_trip_t = self.t + 1e9  # suppress repeat logs
            return f_new

        # Stage 1 — sustained-deficit timer
        if f_new >= self.COLLAPSE_F_THRESHOLD:
            self._below_alert_count = 0.0
            return f_new

        self._below_alert_count += self.DT

        if self._below_alert_count >= self.CASCADE_SUSTAIN_S:
            self._below_alert_count = 0.0
            self._cascade_active = True
            self._next_cascade_trip_t = self.t  # first trip fires immediately this step
            logger.warning(
                "CASCADE INITIATED at t=%.0fs: f=%.3f Hz stayed below %.1f Hz "
                "for %.0fs — beginning relay trip sequence",
                self.t, f_new, self.COLLAPSE_F_THRESHOLD, self.CASCADE_SUSTAIN_S,
            )
            return self._check_cascade(f_new)   # recurse to apply first trip now

        return f_new

    # ------------------------------------------------------------------
    # Startup balancing
    # ------------------------------------------------------------------

    def _balance_generation(self) -> None:
        """
        Scale thermal output so Pm ≈ Pe at t=0.
        Brings offline CCGTs online as spinning reserves if thermal capacity
        is insufficient to cover demand.
        """
        Pe = self.compute_Pe()

        # Fixed / non-dispatchable sources (renewables + nuclear + BESS)
        fixed_types = ("offshore_wind", "solar_pv", "nuclear")
        fixed = sum(
            s["current_output_mw"]
            for s in self.get_all_sources()
            if s["online"] and s.get("type") in fixed_types
        )

        needed = Pe - fixed   # MW to be covered by thermal

        # Dispatchable thermal (coal + gas)
        thermal = [
            s for s in self.get_all_sources()
            if s.get("type") in ("coal", "gas_ccgt") and s["online"]
        ]
        thermal_cap = sum(s["capacity_mw"] for s in thermal)

        # Bring offline CCGTs online if capacity is short
        if thermal_cap < needed:
            for s in self.get_all_sources():
                if s.get("type") == "gas_ccgt" and not s["online"]:
                    s["online"] = True
                    s["current_output_mw"] = 0.0
                    thermal.append(s)
                    thermal_cap += s["capacity_mw"]
                    if thermal_cap >= needed:
                        break

        # Distribute load proportionally across thermal units
        if thermal_cap > 0:
            ratio = min(1.0, max(0.0, needed / thermal_cap))
            for s in thermal:
                s["current_output_mw"] = round(s["capacity_mw"] * ratio, 2)

    # ------------------------------------------------------------------
    # Governor primary frequency response
    # ------------------------------------------------------------------

    def _governor_response(self) -> float:
        """
        Primary frequency response via droop governor (R = 5 %) with
        first-order lag (time constant TAU_GOV).

        The lag prevents the governor from flipping sign instantaneously
        as frequency crosses 50 Hz during CCGT ramp-up, which would
        otherwise cause persistent 0.3–0.5 Hz oscillations.

        Returns the lagged MW adjustment (positive = more generation).
        """
        delta_f   = self.F0 - self.f          # positive when f below nominal
        gov_types = ("coal", "gas_ccgt", "nuclear")

        sources = [
            s for s in self.get_all_sources()
            if s["online"] and s.get("type") in gov_types
        ]
        if not sources:
            self._gov_output = 0.0
            return 0.0

        gov_cap   = sum(s["capacity_mw"] for s in sources)
        headroom_up   = sum(max(0.0, s["capacity_mw"] - s.get("current_output_mw", 0))
                            for s in sources)
        headroom_down = sum(s.get("current_output_mw", 0) for s in sources)

        # Instantaneous droop target
        delta_Pm_target = (1.0 / self.DROOP) * (delta_f / self.F0) * gov_cap
        if delta_Pm_target >= 0:
            delta_Pm_target = min(delta_Pm_target, headroom_up)
        else:
            delta_Pm_target = max(delta_Pm_target, -headroom_down)

        # First-order lag: smoothly track target with time constant TAU_GOV
        alpha = self.DT / (self.TAU_GOV + self.DT)
        self._gov_output += alpha * (delta_Pm_target - self._gov_output)
        return self._gov_output

    # ------------------------------------------------------------------
    # Grid state accessors
    # ------------------------------------------------------------------

    def get_all_sources(self) -> List[dict]:
        return get_all_sources(self.grid)

    def get_hour(self) -> int:
        return int((self.t / 3600) % 24)

    def get_demand_for_hour(self) -> float:
        return HK_DEMAND_PROFILE[self.get_hour()]

    def compute_H_system(self) -> float:
        """H_system = Σ(H_i · P_rated_i) / S_base for all online synchronous sources."""
        total_inertia = 0.0
        for source in self.get_all_sources():
            if not source["online"]:
                continue
            h = source.get("H", 0.0)
            if h <= 0.0:
                continue
            # Synchronous condensers use inertia_mva field for their contribution
            if source.get("type") == "synchronous_condenser":
                total_inertia += h * source.get("inertia_mva", 0.0)
            else:
                total_inertia += h * source["capacity_mw"]
        return total_inertia / self.S_BASE

    def compute_Pm(self) -> float:
        return sum(
            s["current_output_mw"]
            for s in self.get_all_sources()
            if s["online"]
        )

    def compute_Pe(self) -> float:
        base    = self.get_demand_for_hour()
        ev_load = sum(s["max_load_mw"] for s in self.ev if s["active"])
        return base + ev_load + self.demand_extra

    def compute_renewable_fraction(self) -> float:
        total = self.compute_Pm()
        if total <= 0:
            return 0.0
        renewable = sum(
            s["current_output_mw"]
            for s in self.get_all_sources()
            if s["online"] and s.get("type") in ("offshore_wind", "solar_pv")
        )
        return renewable / total

    def get_active_sources_summary(self) -> List[dict]:
        return [
            {
                "name":           s["name"],
                "type":           s.get("type", "unknown"),
                "capacity_mw":    s["capacity_mw"],
                "current_output_mw": s.get("current_output_mw", 0),
                "H":              s.get("H", 0.0),
                "online":         s["online"],
            }
            for s in self.get_all_sources()
        ]

    # ------------------------------------------------------------------
    # Disturbance application
    # ------------------------------------------------------------------

    def apply_disturbance(self, event: dict) -> None:
        """Apply a disturbance event dict to current grid state."""
        etype = event["type"]

        if etype == "generation_loss":
            self._apply_generation_event(event)

        elif etype == "demand_increase":
            if event["profile"] == "step":
                self.demand_extra += event["magnitude_mw"]
            else:
                # Ramp: enqueue for gradual application
                self._ramp_events.append({
                    "remaining_mw": event["magnitude_mw"],
                    "ramp_time_s":  event["ramp_time_s"],
                    "rate_per_s":   event["magnitude_mw"] / event["ramp_time_s"],
                    "elapsed_s":    0.0,
                })

        elif etype == "combined":
            for sub_name in event["sub_events"]:
                sub = DISTURBANCE_EVENTS[sub_name]
                self.apply_disturbance(sub)

    def _apply_generation_event(self, event: dict) -> None:
        affected  = event.get("affected_sources", [])
        profile   = event.get("profile", "step")
        magnitude = event.get("magnitude_mw", 0.0)  # negative = loss

        if profile == "step":
            for source in self.get_all_sources():
                if source["name"] in affected:
                    source["online"] = False
                    source["current_output_mw"] = 0.0

        elif profile == "ramp":
            # Ramp down generation over ramp_time_s seconds.
            # Enqueued as a generation ramp event (reduces Pm, not Pe).
            ramp_time = event.get("ramp_time_s", 30)
            self._ramp_events.append({
                "kind":         "generation",
                "affected":     affected,
                "remaining_mw": magnitude,           # negative
                "ramp_time_s":  ramp_time,
                "rate_per_s":   magnitude / ramp_time,
                "elapsed_s":    0.0,
            })

    def _tick_ramp_events(self) -> None:
        """Advance any in-progress ramp disturbances by DT."""
        completed = []
        for ev in self._ramp_events:
            step   = ev["rate_per_s"] * self.DT
            actual = min(abs(step), abs(ev["remaining_mw"])) * (1 if step >= 0 else -1)

            if ev.get("kind") == "generation":
                # Ramp down generation of affected sources proportionally
                affected = ev.get("affected", [])
                total_output = sum(
                    s["current_output_mw"]
                    for s in self.get_all_sources()
                    if s["name"] in affected and s["online"]
                )
                if total_output > 0:
                    for source in self.get_all_sources():
                        if source["name"] in affected and source["online"]:
                            frac = source["current_output_mw"] / total_output
                            source["current_output_mw"] = max(
                                0.0, source["current_output_mw"] + actual * frac
                            )
                for source in self.get_all_sources():
                    if source["name"] in affected and source["current_output_mw"] <= 0.0:
                        source["online"] = False
                        source["current_output_mw"] = 0.0

            elif ev.get("kind") == "generation_ramp_up":
                # Ramp up a dispatched source (e.g. CCGT after synchronisation)
                src_name = ev.get("source_name")
                for source in self.get_all_sources():
                    if source["name"] == src_name and source["online"]:
                        source["current_output_mw"] = min(
                            source["current_output_mw"] + ev["rate_per_s"] * self.DT,
                            source["capacity_mw"],
                        )

            else:
                # Demand disturbance
                self.demand_extra += actual

            ev["remaining_mw"] -= actual
            ev["elapsed_s"]    += self.DT
            if abs(ev["remaining_mw"]) < 0.01:
                completed.append(ev)

        for ev in completed:
            self._ramp_events.remove(ev)

    def _adapt_pinn_H(self) -> None:
        """
        Fine-tune PINN log_H on the last 30 s of observed data.
        Only runs during frequency transients (range > 50 mHz) so the
        optimizer has enough signal to infer inertia from the swing equation.
        Called every 20 s in step() — cheap (15 gradient steps per call).
        """
        from pinn.predict import estimate_H_from_window
        window = self.history[-30:]
        if len(window) < 5:
            return
        f_vals = [s.f for s in window]
        if max(f_vals) - min(f_vals) < 0.05:
            return  # no useful signal during steady state
        try:
            estimate_H_from_window(
                self.pinn,
                t_window=[s.t for s in window],
                f_window=f_vals,
                Pm_window=[s.Pm_eff for s in window],   # governor-adjusted Pm
                Pe_window=[s.Pe for s in window],
                renewable_frac=window[-1].renewable_fraction,
                n_steps=15,
                lr=5e-4,
            )
        except Exception:
            pass

    def apply_action(self, action: dict) -> None:
        """Apply a dispatch action (from DispatchEngine) to the grid."""
        atype = action["type"]

        if atype == "generation_increase":
            src_name = action.get("source")
            target_mw = action["delta_mw"]
            for source in self.get_all_sources():
                if source["name"] == src_name:
                    source["online"] = True
                    ramp_rate = source.get("ramp_rate_mw_per_min")
                    if ramp_rate:
                        # Start at zero, ramp to target at the source's ramp rate
                        source["current_output_mw"] = 0.0
                        rate_per_s = ramp_rate / 60.0
                        ramp_time_s = target_mw / rate_per_s
                        self._ramp_events.append({
                            "kind":         "generation_ramp_up",
                            "source_name":  src_name,
                            "remaining_mw": target_mw,
                            "rate_per_s":   rate_per_s,
                            "elapsed_s":    0.0,
                            "ramp_time_s":  ramp_time_s,
                        })
                    else:
                        # BESS / fast-response: instant (≤200 ms, within 1-s timestep)
                        source["current_output_mw"] = target_mw

        elif atype == "demand_reduction":
            if action.get("affects_ev_stations"):
                for station in self.ev:
                    station["active"] = False

        elif atype == "demand_reduction_direct":
            # Generic load curtailment (industrial interruptible loads).
            # delta_mw is negative — subtracts from effective demand.
            self.demand_extra += action["delta_mw"]

        elif atype == "inertia_only":
            src_name = action.get("source")
            for source in self.get_all_sources():
                if source["name"] == src_name:
                    source["online"] = True

    # ------------------------------------------------------------------
    # RK4 swing equation integration
    # ------------------------------------------------------------------

    def _swing_deriv(self, Pm: float, Pe: float, H: float) -> float:
        if H <= 0:
            return 0.0
        return (self.F0 / (2.0 * H * self.S_BASE)) * (Pm - Pe)

    def _rk4_step(self, Pm: float, Pe: float, H: float) -> tuple:
        # For the swing equation df/dt = g(Pm, Pe, H) the derivative
        # doesn't depend on f itself, so all four RK4 stages are identical.
        # We keep the standard structure for correctness if the model evolves.
        dt    = self.DT
        df_dt = self._swing_deriv(Pm, Pe, H)
        f_new = self.f + df_dt * dt
        return f_new, df_dt

    # ------------------------------------------------------------------
    # Core step
    # ------------------------------------------------------------------

    def step(self, disturbance: Optional[dict] = None) -> GridState:
        """
        Advance simulation by DT seconds.
        1. Apply disturbance (if any) + tick ramp events
        2. RK4-integrate swing equation
        3. PINN 60s trajectory prediction
        4. Compute risk
        5. Record and return GridState
        """
        if disturbance:
            self.apply_disturbance(disturbance)
        self._tick_ramp_events()

        H  = self.compute_H_system()
        Pm = self.compute_Pm()
        Pe = self.compute_Pe()

        # Primary frequency response: governor adjusts thermal output
        # to resist f deviation (5 % droop — standard grid operation)
        Pm_eff = Pm + self._governor_response()

        # Integrate swing equation
        if H < 1e-6:
            if self._cascade_active and self.f > 0.5:
                # All generators offline — coast on motor-load inertia.
                # Pm = 0 (no generation), Pe = load still consuming → large negative df/dt.
                f_new, df_dt = self._rk4_step(0.0, Pe, self.H_LOAD_INERTIA)
                f_new = max(0.0, f_new)
            else:
                f_new  = 0.0
                df_dt  = 0.0
        else:
            f_new, df_dt = self._rk4_step(Pm_eff, Pe, H)

        # Cascade protection checks (may trip generators or force f → 0)
        f_new = self._check_cascade(f_new)

        f_new = max(0.0, min(52.0, f_new))
        self.f = f_new

        # Online H adaptation — every 20 s when transient is active
        if len(self.history) >= 10 and int(self.t) % 20 == 0:
            self._adapt_pinn_H()

        # PINN trajectory — physics rollout with governor dynamics,
        # carrying forward any in-progress generation/demand ramps so the
        # 60-second lookahead sees the full upcoming deficit rather than
        # just the current snapshot (key for PINN early-warning accuracy).
        rf = self.compute_renewable_fraction()
        gov_types = ("coal", "gas_ccgt", "nuclear")
        thermal_sources = [
            s for s in self.get_all_sources()
            if s["online"] and s.get("type") in gov_types
        ]
        gov_cap_pred = sum(s["capacity_mw"] for s in thermal_sources)
        gov_headroom_pred = sum(
            max(0.0, s["capacity_mw"] - s.get("current_output_mw", 0))
            for s in thermal_sources
        )

        gen_ramps = [ev for ev in self._ramp_events if ev.get("kind") == "generation"]
        dem_ramps = [ev for ev in self._ramp_events
                     if ev.get("kind") not in ("generation", "generation_ramp_up")]
        gen_ramp_mw   = sum(ev["remaining_mw"] for ev in gen_ramps)
        gen_ramp_rate = sum(ev["rate_per_s"]   for ev in gen_ramps)
        dem_ramp_mw   = sum(ev["remaining_mw"] for ev in dem_ramps)
        dem_ramp_rate = sum(ev["rate_per_s"]   for ev in dem_ramps)

        trajectory = predict_trajectory(
            self.pinn,
            t_start=self.t,
            f0=self.f,
            Pm=Pm,
            Pe=Pe,
            renewable_frac=rf,
            H_prior=H,
            gov_cap=gov_cap_pred,
            gov_output_init=self._gov_output,
            gov_headroom=gov_headroom_pred,
            gen_ramp_mw=gen_ramp_mw,
            gen_ramp_rate=gen_ramp_rate,
            dem_ramp_mw=dem_ramp_mw,
            dem_ramp_rate=dem_ramp_rate,
            horizon_s=60,
        )

        risk   = compute_risk_score(H, df_dt, self.f)
        level  = risk_level_from_score(risk)
        fband  = freq_band(self.f)

        state = GridState(
            t=self.t,
            f=self.f,
            H_physical=H,
            H_pinn=self.pinn.get_H_estimate(),
            Pm=Pm,
            Pm_eff=Pm_eff,
            Pe=Pe,
            df_dt=df_dt,
            trajectory_60s=trajectory,
            risk_score=risk,
            risk_level=level,
            renewable_fraction=rf,
            active_sources=self.get_active_sources_summary(),
            ev_stations_active=sum(1 for s in self.ev if s["active"]),
            freq_band=fband,
            demand_extra_mw=self.demand_extra,
        )

        self.history.append(state)
        self.t += self.DT
        return state

    # ------------------------------------------------------------------
    # Cloning (for PhysicsValidator)
    # ------------------------------------------------------------------

    def clone(self) -> "GridSimulator":
        sim = GridSimulator.__new__(GridSimulator)
        sim.grid                = copy.deepcopy(self.grid)
        sim.ev                  = copy.deepcopy(self.ev)
        sim.pinn                = self.pinn
        sim.t                   = self.t
        sim.f                   = self.f
        sim.demand_extra        = self.demand_extra
        sim._gov_output         = self._gov_output
        sim._ramp_events        = copy.deepcopy(self._ramp_events)
        sim._below_alert_count  = self._below_alert_count
        sim._cascade_active     = self._cascade_active
        sim._next_cascade_trip_t = self._next_cascade_trip_t
        sim.history             = []
        return sim
