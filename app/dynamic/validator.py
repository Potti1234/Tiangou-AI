from __future__ import annotations

from typing import Any

FREQ_MIN_SAFE = 49.0
VALIDATION_HORIZON_S = 60


class PhysicsValidator:
    def validate(self, current_state: Any, proposed_actions: list[dict[str, Any]], simulator: Any) -> dict[str, Any]:
        sim_copy = simulator.clone()
        for action in proposed_actions:
            sim_copy.apply_action(action)
        trajectory = [sim_copy.step().f for _ in range(VALIDATION_HORIZON_S)]
        f_min = min(trajectory)
        return {
            "approved": f_min >= FREQ_MIN_SAFE,
            "projected_trajectory": trajectory,
            "projected_f_min": f_min,
            "projected_f_max": max(trajectory),
            "projected_H_final": sim_copy.compute_H_system(),
            "reject_reason": None if f_min >= FREQ_MIN_SAFE else f"Frequency projects to {f_min:.2f} Hz",
        }

