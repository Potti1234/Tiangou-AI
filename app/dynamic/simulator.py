from __future__ import annotations

import copy
from typing import Any

from app.dynamic.grid_state import GridState
from app.dynamic.pinn_predict import predict_trajectory
from app.dynamic.thresholds import compute_risk_score, freq_band, risk_level_from_score


class GridSimulator:
    DT = 1.0
    F0 = 50.0
    S_BASE = 12000.0
    DROOP = 0.05
    TAU_GOV = 8.0
    COLLAPSE_F_THRESHOLD = 49.0
    CASCADE_SUSTAIN_S = 110
    CASCADE_INTER_TRIP_S = 3
    H_LOAD_INERTIA = 1.5

    def __init__(
        self,
        grid_config: dict[str, Any],
        demand_profile_mw: dict[int, float],
        ev_stations: list[dict[str, Any]],
        pinn_model: Any,
        start_t: float = 16 * 3600,
    ):
        self.grid = grid_config
        self.demand_profile_mw = demand_profile_mw
        self.ev = copy.deepcopy(ev_stations)
        self.pinn = pinn_model
        self.t = start_t
        self.f = 50.0
        self.demand_extra = 0.0
        self._gov_output = 0.0
        self._ramp_events: list[dict[str, Any]] = []
        self._below_alert_count = 0.0
        self._cascade_active = False
        self._next_cascade_trip_t = 0.0
        self.history: list[GridState] = []
        self._balance_generation()

    def get_all_sources(self) -> list[dict[str, Any]]:
        return self.grid.get("sources", [])

    def get_hour(self) -> int:
        return int((self.t / 3600) % 24)

    def get_demand_for_hour(self) -> float:
        return float(self.demand_profile_mw.get(self.get_hour(), self.demand_profile_mw.get(16, 0.0)))

    def compute_H_system(self) -> float:
        total_inertia = 0.0
        for source in self.get_all_sources():
            if not source.get("online"):
                continue
            h = float(source.get("H") or 0.0)
            if h <= 0.0:
                continue
            total_inertia += h * float(source.get("inertia_mva") or source.get("capacity_mw") or 0.0)
        return total_inertia / self.S_BASE

    def compute_Pm(self) -> float:
        return sum(float(s.get("current_output_mw") or 0.0) for s in self.get_all_sources() if s.get("online"))

    def compute_Pe(self) -> float:
        ev_load = sum(float(s.get("max_load_mw") or 0.0) for s in self.ev if s.get("active", True))
        return self.get_demand_for_hour() + ev_load + self.demand_extra

    def compute_renewable_fraction(self) -> float:
        total = self.compute_Pm()
        if total <= 0:
            return 0.0
        renewable = sum(
            float(s.get("current_output_mw") or 0.0)
            for s in self.get_all_sources()
            if s.get("online") and s.get("type") in {"offshore_wind", "solar_pv"}
        )
        return renewable / total

    def get_active_sources_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.get("name"),
                "source_id": s.get("source_id"),
                "type": s.get("type", "unknown"),
                "capacity_mw": s.get("capacity_mw", 0.0),
                "current_output_mw": s.get("current_output_mw", 0.0),
                "H": s.get("H", 0.0),
                "online": s.get("online", False),
                "provenance": s.get("provenance"),
                "confidence": s.get("confidence"),
            }
            for s in self.get_all_sources()
        ]

    def _balance_generation(self) -> None:
        pe = self.compute_Pe()
        fixed = sum(
            float(s.get("current_output_mw") or 0.0)
            for s in self.get_all_sources()
            if s.get("online") and s.get("type") in {"offshore_wind", "solar_pv", "nuclear", "imports"}
        )
        needed = max(0.0, pe - fixed)
        dispatchable = [
            s for s in self.get_all_sources()
            if s.get("online") and s.get("type") in {"coal", "gas_ccgt", "other_dispatchable", "generic_capacity_equivalent"}
        ]
        cap = sum(float(s.get("capacity_mw") or 0.0) for s in dispatchable)
        if cap <= 0:
            return
        ratio = min(1.0, needed / cap)
        for source in dispatchable:
            source["current_output_mw"] = round(float(source.get("capacity_mw") or 0.0) * ratio, 3)

    def _governor_response(self) -> float:
        delta_f = self.F0 - self.f
        sources = [
            s for s in self.get_all_sources()
            if s.get("online") and s.get("type") in {"coal", "gas_ccgt", "nuclear", "imports", "other_dispatchable", "generic_capacity_equivalent"}
        ]
        if not sources:
            self._gov_output = 0.0
            return 0.0
        gov_cap = sum(float(s.get("capacity_mw") or 0.0) for s in sources)
        headroom_up = sum(max(0.0, float(s.get("capacity_mw") or 0.0) - float(s.get("current_output_mw") or 0.0)) for s in sources)
        headroom_down = sum(float(s.get("current_output_mw") or 0.0) for s in sources)
        target = (1.0 / self.DROOP) * (delta_f / self.F0) * gov_cap
        target = min(target, headroom_up) if target >= 0 else max(target, -headroom_down)
        self._gov_output += self.DT / (self.TAU_GOV + self.DT) * (target - self._gov_output)
        return self._gov_output

    def apply_disturbance(self, event: dict[str, Any]) -> None:
        event_type = event["type"]
        if event_type == "generation_loss":
            self._apply_generation_event(event)
        elif event_type == "demand_increase":
            if event.get("profile") == "ramp":
                ramp_time = max(float(event.get("ramp_time_s") or 60.0), 1.0)
                self._ramp_events.append({
                    "remaining_mw": float(event["magnitude_mw"]),
                    "ramp_time_s": ramp_time,
                    "rate_per_s": float(event["magnitude_mw"]) / ramp_time,
                    "elapsed_s": 0.0,
                })
            else:
                self.demand_extra += float(event["magnitude_mw"])
        elif event_type == "combined":
            for sub_event in event.get("sub_events", []):
                self.apply_disturbance(sub_event)

    def _apply_generation_event(self, event: dict[str, Any]) -> None:
        affected = set(event.get("affected_sources") or [])
        if event.get("profile", "step") == "ramp":
            ramp_time = max(float(event.get("ramp_time_s") or 30.0), 1.0)
            self._ramp_events.append({
                "kind": "generation",
                "affected": list(affected),
                "remaining_mw": float(event.get("magnitude_mw") or 0.0),
                "ramp_time_s": ramp_time,
                "rate_per_s": float(event.get("magnitude_mw") or 0.0) / ramp_time,
                "elapsed_s": 0.0,
            })
            return
        for source in self.get_all_sources():
            if source.get("name") in affected or source.get("source_id") in affected:
                source["online"] = False
                source["current_output_mw"] = 0.0

    def _tick_ramp_events(self) -> None:
        completed = []
        for event in self._ramp_events:
            step = event["rate_per_s"] * self.DT
            actual = min(abs(step), abs(event["remaining_mw"])) * (1 if step >= 0 else -1)
            if event.get("kind") == "generation":
                affected = set(event.get("affected", []))
                total_output = sum(
                    float(s.get("current_output_mw") or 0.0)
                    for s in self.get_all_sources()
                    if (s.get("name") in affected or s.get("source_id") in affected) and s.get("online")
                )
                if total_output > 0:
                    for source in self.get_all_sources():
                        if (source.get("name") in affected or source.get("source_id") in affected) and source.get("online"):
                            frac = float(source.get("current_output_mw") or 0.0) / total_output
                            source["current_output_mw"] = max(0.0, float(source.get("current_output_mw") or 0.0) + actual * frac)
                            if source["current_output_mw"] <= 0:
                                source["online"] = False
            elif event.get("kind") == "generation_ramp_up":
                for source in self.get_all_sources():
                    if source.get("name") == event.get("source_name"):
                        source["online"] = True
                        source["current_output_mw"] = min(
                            float(source.get("capacity_mw") or 0.0),
                            float(source.get("current_output_mw") or 0.0) + abs(event["rate_per_s"]) * self.DT,
                        )
            else:
                self.demand_extra += actual
            event["remaining_mw"] -= actual
            event["elapsed_s"] += self.DT
            if abs(event["remaining_mw"]) < 0.01:
                completed.append(event)
        for event in completed:
            self._ramp_events.remove(event)

    def apply_action(self, action: dict[str, Any]) -> None:
        action_type = action["type"]
        if action_type == "generation_increase":
            target = float(action["delta_mw"])
            for source in self.get_all_sources():
                if source.get("name") == action.get("source"):
                    source["online"] = True
                    if action.get("emergency"):
                        source["current_output_mw"] = min(
                            float(source.get("capacity_mw") or 0.0),
                            float(source.get("current_output_mw") or 0.0) + target,
                        )
                        continue
                    ramp_rate = float(source.get("ramp_rate_mw_per_min") or 0.0)
                    if ramp_rate > 0:
                        source["current_output_mw"] = min(float(source.get("current_output_mw") or 0.0), float(source.get("capacity_mw") or 0.0))
                        self._ramp_events.append({
                            "kind": "generation_ramp_up",
                            "source_name": source.get("name"),
                            "remaining_mw": target,
                            "rate_per_s": ramp_rate / 60.0,
                            "elapsed_s": 0.0,
                        })
                    else:
                        source["current_output_mw"] = min(float(source.get("capacity_mw") or 0.0), target)
        elif action_type == "demand_reduction":
            for station in self.ev:
                station["active"] = False
        elif action_type == "demand_reduction_direct":
            self.demand_extra += float(action["delta_mw"])

    def _swing_deriv(self, Pm: float, Pe: float, H: float) -> float:
        if H <= 0:
            return 0.0
        return (self.F0 / (2.0 * H * self.S_BASE)) * (Pm - Pe)

    def _check_cascade(self, f_new: float) -> float:
        if f_new >= self.COLLAPSE_F_THRESHOLD:
            self._below_alert_count = 0.0
            return f_new
        self._below_alert_count += self.DT
        if self._below_alert_count >= self.CASCADE_SUSTAIN_S:
            self._cascade_active = True
        return f_new

    def step(self, disturbance: dict[str, Any] | None = None) -> GridState:
        if disturbance:
            self.apply_disturbance(disturbance)
        self._tick_ramp_events()
        H = self.compute_H_system()
        Pm = self.compute_Pm()
        Pe = self.compute_Pe()
        Pm_eff = Pm + self._governor_response()
        if H < 1e-6:
            f_new = 0.0
            df_dt = 0.0
        else:
            df_dt = self._swing_deriv(Pm_eff, Pe, H)
            f_new = self.f + df_dt * self.DT
        self.f = max(0.0, min(52.0, self._check_cascade(f_new)))
        rf = self.compute_renewable_fraction()
        gov_sources = [
            s for s in self.get_all_sources()
            if s.get("online") and s.get("type") in {"coal", "gas_ccgt", "nuclear", "imports", "other_dispatchable", "generic_capacity_equivalent"}
        ]
        gov_cap = sum(float(s.get("capacity_mw") or 0.0) for s in gov_sources)
        gov_headroom = sum(max(0.0, float(s.get("capacity_mw") or 0.0) - float(s.get("current_output_mw") or 0.0)) for s in gov_sources)
        gen_ramps = [ev for ev in self._ramp_events if ev.get("kind") == "generation"]
        dem_ramps = [ev for ev in self._ramp_events if ev.get("kind") not in {"generation", "generation_ramp_up"}]
        trajectory = predict_trajectory(
            self.pinn,
            t_start=self.t,
            f0=self.f,
            Pm=Pm,
            Pe=Pe,
            renewable_frac=rf,
            H_prior=H,
            gov_cap=gov_cap,
            gov_output_init=self._gov_output,
            gov_headroom=gov_headroom,
            gen_ramp_mw=sum(float(ev["remaining_mw"]) for ev in gen_ramps),
            gen_ramp_rate=sum(float(ev["rate_per_s"]) for ev in gen_ramps),
            dem_ramp_mw=sum(float(ev["remaining_mw"]) for ev in dem_ramps),
            dem_ramp_rate=sum(float(ev["rate_per_s"]) for ev in dem_ramps),
        )
        risk = compute_risk_score(H, df_dt, self.f)
        state = GridState(
            t=self.t,
            f=self.f,
            H_physical=H,
            H_pinn=float(self.pinn.get_H_estimate()),
            Pm=Pm,
            Pm_eff=Pm_eff,
            Pe=Pe,
            df_dt=df_dt,
            trajectory_60s=trajectory,
            risk_score=risk,
            risk_level=risk_level_from_score(risk),
            renewable_fraction=rf,
            active_sources=self.get_active_sources_summary(),
            ev_stations_active=sum(1 for s in self.ev if s.get("active", True)),
            freq_band=freq_band(self.f),
            demand_extra_mw=self.demand_extra,
        )
        self.history.append(state)
        self.t += self.DT
        return state

    def clone(self) -> "GridSimulator":
        return copy.deepcopy(self)
