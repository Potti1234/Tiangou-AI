"""
Real-time grid risk score computation using the trained GridPINN.

Interface (consumed by Layer 5 – Dispatch Decision Engine):
  Input:  {'Pm': float, 'Pe': float, 'S_base': float, 'renewable_frac': float}
  Output: {'risk_score': float, 'H_estimated': float, 'rocof': float,
           'risk_level': str, 'time_to_threshold': float,
           'recommended_action': str}
"""

import sys
sys.path.insert(0, '/mnt/data/hackathon/venv_pkgs')

import os
import torch
import numpy as np
from typing import Dict

# load the model class so we can restore a checkpoint
sys.path.insert(0, os.path.dirname(__file__))
from model import build_model

F0 = 50.0
F_THRESHOLD = 49.8      # Hz — under-frequency relay setpoint
ROCOF_MAX   = 0.5       # Hz/s — maximum tolerable RoCoF

# Inertia thresholds derived from Spain event analysis
H_VULNERABLE = 1.5     # s — below this, grid is vulnerable
H_CRITICAL   = 1.0     # s — below this, cascading disconnection likely


def compute_risk_score(model, current_state: Dict) -> Dict:
    """
    Compute a real-time risk score from current grid state.

    Args:
        model:         trained GridPINN (model.H gives current H estimate)
        current_state: dict with keys
            Pm            – mechanical power (MW)
            Pe            – electrical demand (MW)
            S_base        – system MVA base (MW)
            renewable_frac – fraction of generation that is non-synchronous [0,1]
            f_current     – (optional) current measured frequency (Hz), default 50

    Returns:
        dict with risk diagnostics
    """
    model.eval()
    with torch.no_grad():
        H = model.H.item()

    Pm  = float(current_state['Pm'])
    Pe  = float(current_state['Pe'])
    Sb  = float(current_state['S_base'])
    rf  = float(current_state.get('renewable_frac', 0.5))
    f_c = float(current_state.get('f_current', F0))

    # RoCoF from swing equation (Hz/s)
    delta_P = Pm - Pe       # MW  (>0 over-generation, <0 deficit)
    rocof   = (F0 / (2.0 * H * Sb)) * delta_P

    # Time to reach 49.8 Hz threshold (linear extrapolation)
    if abs(rocof) < 1e-6:
        time_to_threshold = float('inf')
    else:
        delta_f = f_c - F_THRESHOLD        # Hz still available before relay
        time_to_threshold = delta_f / (-rocof) if rocof < 0 else float('inf')
        time_to_threshold = max(0.0, time_to_threshold)

    # ---- Risk sub-scores ----
    # Inertia risk: 0 at H≥H_VULNERABLE, 1 at H≤H_CRITICAL
    H_risk = float(np.clip((H_VULNERABLE - H) / (H_VULNERABLE - H_CRITICAL), 0.0, 1.0))

    # RoCoF risk: 0 at |rocof|=0, 1 at |rocof|≥ROCOF_MAX
    rocof_risk = float(np.clip(abs(rocof) / ROCOF_MAX, 0.0, 1.0))

    # Renewable fraction risk: high RF → low synchronous inertia
    rf_risk = float(np.clip((rf - 0.5) / 0.5, 0.0, 1.0))

    # Weighted composite
    risk_score = 0.5 * H_risk + 0.3 * rocof_risk + 0.2 * rf_risk

    # ---- Risk level & recommended action ----
    if risk_score < 0.3:
        risk_level = 'NORMAL'
        action = 'No action required. Grid is stable.'
    elif risk_score < 0.6:
        risk_level = 'ALERT'
        action = (
            f'H = {H:.2f} s (low). '
            f'RoCoF = {rocof:+.3f} Hz/s. '
            'Recommend activating fast-response reserves within 30 s.'
        )
    else:
        risk_level = 'CRITICAL'
        action = (
            f'H = {H:.2f} s (CRITICAL). '
            f'RoCoF = {rocof:+.3f} Hz/s — collapse imminent. '
            'IMMEDIATE dispatch: start backup generators + shed flexible load (EV charging).'
        )

    return {
        'risk_score':         round(risk_score, 4),
        'risk_level':         risk_level,
        'H_estimated':        round(H, 4),
        'rocof_hz_per_s':     round(rocof, 4),
        'time_to_threshold_s': round(time_to_threshold, 2),
        'recommended_action': action,
        # sub-scores for dashboard
        'H_risk':             round(H_risk,    4),
        'rocof_risk':         round(rocof_risk, 4),
        'rf_risk':            round(rf_risk,    4),
    }


def load_trained_model(checkpoint_path: str = None) -> 'GridPINN':
    """Load a trained model from checkpoint."""
    if checkpoint_path is None:
        checkpoint_path = os.path.join(
            os.path.dirname(__file__), '../outputs/pinn_grid_spain_trained.pt')

    ckpt = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    model = build_model(H_init=1.14, freeze_H=False)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()
    print(f'[risk] Loaded checkpoint: H = {model.H.item():.4f} s')
    return model


if __name__ == '__main__':
    # Demo with a freshly-initialised model (no training needed for API test)
    model = build_model(H_init=1.14, freeze_H=False)

    scenarios = [
        {'label': 'Normal HK grid',
         'Pm': 7600, 'Pe': 7600, 'S_base': 12000,
         'renewable_frac': 0.30, 'f_current': 50.0},
        {'label': 'Typhoon – 800 MW wind loss',
         'Pm': 6800, 'Pe': 7600, 'S_base': 12000,
         'renewable_frac': 0.40, 'f_current': 49.95},
        {'label': 'Spain pre-collapse',
         'Pm': 32000, 'Pe': 29250, 'S_base': 32000,
         'renewable_frac': 0.72, 'f_current': 49.94},
    ]

    for s in scenarios:
        label = s.pop('label')
        result = compute_risk_score(model, s)
        print(f'\n=== {label} ===')
        for k, v in result.items():
            print(f'  {k:30s}: {v}')
