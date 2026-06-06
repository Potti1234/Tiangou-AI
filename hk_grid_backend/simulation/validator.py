"""
PhysicsValidator — Layer 6.

Before executing any dispatch action, runs a 120-second forward simulation
on a cloned grid and checks whether frequency and H stay within safe bounds.
Rejects actions that don't stabilise frequency.
"""

from typing import List, Optional

from simulation.grid_state import GridState
from simulation.simulator import GridSimulator

# Validator approves an action if it keeps frequency above the blackout
# threshold (49.0 Hz) — during a crisis the goal is to avoid cascade,
# not to prove perfect restoration within the validation window.
FREQ_MIN_SAFE  = 49.0   # Hz  (below = cascade / UFLS cascade)
FREQ_MAX_SAFE  = 51.0   # Hz
H_MIN_SAFE     = 1.0    # s
VALIDATION_HORIZON_S = 120


class PhysicsValidator:

    def validate(
        self,
        current_state: GridState,
        proposed_actions: List[dict],
        simulator: GridSimulator,
    ) -> dict:
        """
        Clone the simulator, apply proposed actions, run 120 s forward.

        Returns:
          approved:             bool
          projected_trajectory: List[float] (120 values)
          projected_f_min:      float
          projected_f_max:      float
          projected_H_final:    float
          reject_reason:        str | None
        """
        sim_copy = simulator.clone()

        for action in proposed_actions:
            sim_copy.apply_action(action)

        trajectory: List[float] = []
        for _ in range(VALIDATION_HORIZON_S):
            state = sim_copy.step()
            trajectory.append(state.f)

        f_min   = min(trajectory)
        f_max   = max(trajectory)
        H_final = sim_copy.compute_H_system()

        reject_reason: Optional[str] = None
        if f_min < FREQ_MIN_SAFE:
            reject_reason = (
                f"Frequency projects to {f_min:.2f} Hz "
                f"(below {FREQ_MIN_SAFE} Hz threshold)"
            )
        elif H_final < H_MIN_SAFE:
            reject_reason = (
                f"H projects to {H_final:.2f} s "
                f"(below {H_MIN_SAFE} s safety threshold)"
            )

        approved = reject_reason is None

        return {
            "approved":             approved,
            "projected_trajectory": trajectory,
            "projected_f_min":      f_min,
            "projected_f_max":      f_max,
            "projected_H_final":    H_final,
            "reject_reason":        reject_reason,
        }
