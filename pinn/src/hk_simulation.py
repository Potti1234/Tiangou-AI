"""
Hong Kong grid simulation — physics-driven with PINN-learned inertia.

Architecture of this simulation:
  - PHYSICS ENGINE: swing equation  df/dt = (f0 / 2·H·S) · (Pm − Pe)
  - PINN CONTRIBUTION: the learned inertia constant H
  - PINN RISK MONITOR: df/dt and H are fed to the risk function at every step

The trained PINN cannot usefully extrapolate its neural network outputs to HK
inputs (which are outside Spain's training distribution). What transfers is H —
the scalar that the PINN extracted from the physics residual loss. H tells us
how much kinetic energy the grid has per MW of nameplate capacity, which is a
grid property that can be estimated from one event and applied elsewhere.

Transfer step (Spain → HK):
  H_hk = H_hk_nominal × (H_spain_pinn / H_spain_nominal)
  This applies the PINN's fractional correction to HK's own nominal inertia.
  If the PINN learned H slightly lower than expected (→ lower H_hk), the HK
  grid is slightly more vulnerable — the correction propagates physically.

Run:
  python hk_simulation.py [--checkpoint ../outputs/pinn_grid_spain_trained.pt]
                          [--scenario typhoon_offshore_wind]  [--no-plot]
"""

import sys
import os
sys.path.insert(0, '/mnt/data/hackathon/venv_pkgs')
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import torch

from model import build_model
from data_loader import load_all

# ── Physical constants ────────────────────────────────────────────────────────
F0           = 50.0        # Hz nominal
HK_S_BASE    = 12_000.0   # MVA
SPAIN_H_NOM  = 1.14        # s  — Spain's expected pre-event inertia
HK_H_NOM     = 4.0         # s  — HK's nominal inertia (conventional-heavy grid)

# ── Risk thresholds calibrated for HK's higher-inertia regime ────────────────
H_VULNERABLE = 3.0   # s  — below this, grid is vulnerable
H_CRITICAL   = 2.0   # s  — below this, cascading likely
ROCOF_ALERT  = 0.20  # Hz/s — df/dt magnitude triggers ALERT
ROCOF_CRIT   = 0.50  # Hz/s — df/dt magnitude triggers CRITICAL

# ── UFLS: inertia step-reduction when generators trip at low frequency ────────
UFLS_STEPS = [
    (48.0, 1.00),   # f ≥ 48 Hz : full inertia
    (47.5, 0.80),   # f ≥ 47.5 Hz: 20% synchronous generation tripped
    (47.0, 0.55),   # f ≥ 47.0 Hz: 45% tripped
    (0.0,  0.30),   # f < 47.0 Hz: 70% tripped — near collapse
]

# ── Scenario definitions ──────────────────────────────────────────────────────
SCENARIOS = {
    'typhoon_offshore_wind': {
        'label':          'Typhoon — 800 MW Offshore Wind Loss',
        'Pm0':            7_600.0,   # MW  pre-event generation
        'Pe0':            7_600.0,   # MW  pre-event demand
        'event_t':        20.0,      # s   event time
        'event_dPm':      -800.0,    # MW  sudden generation drop (wind trips)
        'monitor_from':   20.0,      # s   PINN starts risk monitoring here
        # Post-intervention: Pm=7600-800+650=7450, Pe=7600-200=7400 → ΔP=+50 MW → gentle recovery
        'action_dPm':     +650.0,    # MW  gas peakers + fast-response units
        'action_dPe':     -200.0,    # MW  EV + commercial load shed (demand falls)
        'ev_stations_shed': 47,
        'reactivate_t':   200.0,     # keep EVs shed for full demo window
        'ramp_duration':  None,
    },
    'mainland_disconnect': {
        'label':          'Mainland Disconnect — 1,200 MW Import Lost',
        'Pm0':            7_600.0,
        'Pe0':            8_800.0,   # HK imports 1,200 MW from mainland
        'event_t':        20.0,
        'event_dPm':      -1_200.0,  # import cut → large sudden deficit
        'monitor_from':   20.0,
        'action_dPm':     +900.0,
        'action_dPe':     -500.0,
        'ev_stations_shed': 62,
        'reactivate_t':   200.0,
        'ramp_duration':  None,
    },
    'solar_cloud_event': {
        'label':          'Solar Cloud Event — 600 MW Ramp-Down over 60 s',
        'Pm0':            7_600.0,
        'Pe0':            7_600.0,
        'event_t':        10.0,
        'event_dPm':      -600.0,    # ramp, not step
        'monitor_from':   10.0,
        'action_dPm':     +450.0,
        'action_dPe':     -150.0,
        'ev_stations_shed': 31,
        'reactivate_t':   200.0,
        'ramp_duration':  60.0,
    },
}

EV_STATIONS = [
    {'name': 'HK Island Central',     'lat': 22.282, 'lon': 114.158},
    {'name': 'HK Island Causeway Bay', 'lat': 22.280, 'lon': 114.183},
    {'name': 'Kowloon Mong Kok',       'lat': 22.319, 'lon': 114.170},
    {'name': 'Kowloon Tsim Sha Tsui',  'lat': 22.295, 'lon': 114.172},
    {'name': 'NT Sha Tin',             'lat': 22.376, 'lon': 114.195},
    {'name': 'NT Tuen Mun',            'lat': 22.391, 'lon': 113.977},
    {'name': 'NT Yuen Long',           'lat': 22.445, 'lon': 114.022},
    {'name': 'Lantau Discovery Bay',   'lat': 22.388, 'lon': 114.030},
]


# ── Physics helpers ───────────────────────────────────────────────────────────

def live_H(H_base: float, f: float) -> float:
    """Return effective inertia after UFLS shedding at current frequency."""
    for f_thresh, factor in UFLS_STEPS:
        if f >= f_thresh:
            return H_base * factor
    return H_base * UFLS_STEPS[-1][1]


def swing_dfdt(Pm: float, Pe: float, H: float, S: float = HK_S_BASE) -> float:
    """
    Swing equation: df/dt = (f0 / 2·H·S) · (Pm − Pe)  [Hz/s]

    This is the physics model. H comes from the PINN. Governor dynamics
    (which would bring f back to exactly 50 Hz in steady state) are not
    modelled here — they operate on a slower timescale (seconds to minutes)
    and do not affect the emergency detection window shown in this demo.
    """
    return (F0 / (2.0 * H * S)) * (Pm - Pe)


def generation_at(sc: dict, t: float, dPm_action: float) -> float:
    """Current mechanical power including event ramp and any dispatched peakers."""
    if t < sc['event_t']:
        base = sc['Pm0']
    elif sc['ramp_duration']:
        frac = min((t - sc['event_t']) / sc['ramp_duration'], 1.0)
        base = sc['Pm0'] + sc['event_dPm'] * frac
    else:
        base = sc['Pm0'] + sc['event_dPm']
    return base + dPm_action


# ── Risk scoring driven by actual physics ─────────────────────────────────────

def risk_score(H_live: float, dfdt: float, rf: float) -> dict:
    """
    Risk score from live physics state.

    Inputs come directly from the swing-equation physics step (not a formula
    applied independently). dfdt is the swing equation evaluated with the
    PINN-learned H — it is the physics prediction of how fast frequency is
    changing right now.
    """
    H_risk     = float(np.clip((H_VULNERABLE - H_live) / (H_VULNERABLE - H_CRITICAL), 0, 1))
    rocof_risk = float(np.clip(abs(dfdt) / ROCOF_CRIT, 0, 1))
    rf_risk    = float(np.clip((rf - 0.3) / 0.5, 0, 1))

    score = 0.50 * H_risk + 0.35 * rocof_risk + 0.15 * rf_risk

    if score < 0.3:
        level  = 'NORMAL'
        action = 'No action required.'
    elif score < 0.60:
        level  = 'ALERT'
        action = (f'H={H_live:.2f}s  df/dt={dfdt:+.3f}Hz/s. '
                  'Activate fast-response reserves within 30 s.')
    else:
        level  = 'CRITICAL'
        action = (f'H={H_live:.2f}s  df/dt={dfdt:+.3f}Hz/s — imminent collapse. '
                  'DISPATCH: gas peakers + shed EV/flexible load NOW.')

    return {
        'score':      round(score, 4),
        'level':      level,
        'action':     action,
        'H_risk':     round(H_risk,     4),
        'rocof_risk': round(rocof_risk, 4),
    }


# ── Simulation ────────────────────────────────────────────────────────────────

def run_scenario(
    model,
    scenario_key: str = 'typhoon_offshore_wind',
    t_end: float = 90.0,
    dt: float = 1.0,
) -> dict:
    """
    Physics-driven simulation parameterised by the PINN's learned H.

    The swing equation governs df/dt at every step.
    The PINN's contribution is the inertia H — extracted from Spain data by
    the physics-loss training and then scaled to HK.
    The risk monitor fires on the physics-derived df/dt and live H.
    """
    sc    = SCENARIOS[scenario_key]
    t_vec = np.arange(0.0, t_end + dt, dt)
    N     = len(t_vec)

    # ── Transfer Spain H → HK H ──────────────────────────────────────────────
    H_spain = model.H.item()
    H_hk    = HK_H_NOM * (H_spain / SPAIN_H_NOM)
    H_hk    = max(H_hk, 0.5)

    print(f'  PINN-learned H (Spain) = {H_spain:.4f} s')
    print(f'  HK H (transferred)     = {H_hk:.4f} s')
    print(f'  Transfer ratio         = {H_spain/SPAIN_H_NOM:.4f}  '
          f'(PINN says Spain was {100*(H_spain/SPAIN_H_NOM - 1):+.1f}% from nominal)')

    # Allocate output arrays
    f_ni   = np.full(N, F0)    # no-intervention frequency
    f_pi   = np.full(N, F0)    # PINN-dispatch frequency
    dfdt_ni = np.zeros(N)
    dfdt_pi = np.zeros(N)
    risk_ni = np.zeros(N)
    risk_pi = np.zeros(N)
    H_live_pi = np.full(N, H_hk)

    # ── No-intervention run ───────────────────────────────────────────────────
    for i, t in enumerate(t_vec[:-1]):
        f = f_ni[i]
        if f < 0.5:
            f_ni[i + 1] = 0.0
            continue

        Pm  = generation_at(sc, t, 0.0)
        Pe  = sc['Pe0']
        H   = live_H(H_hk, f)
        rf  = 0.30 + 0.10 * (t / t_end)
        ddt = swing_dfdt(Pm, Pe, H)
        rs  = risk_score(H, ddt, rf)

        dfdt_ni[i] = ddt
        risk_ni[i] = rs['score']
        f_ni[i + 1] = max(0.0, f + ddt * dt)

    # ── PINN-dispatch run ─────────────────────────────────────────────────────
    dPm_action  = 0.0    # committed generation boost (MW)
    dPe_action  = 0.0    # committed demand reduction (MW, negative = less load)
    intervened   = False
    ev_restored  = False
    dispatch_t   = None

    for i, t in enumerate(t_vec[:-1]):
        f = f_pi[i]
        if f < 0.5:
            f_pi[i + 1]       = 0.0
            risk_pi[i + 1]    = risk_pi[i]
            H_live_pi[i + 1]  = H_live_pi[i]
            continue

        Pm  = generation_at(sc, t, dPm_action)
        Pe  = sc['Pe0'] + dPe_action

        # Restore EVs (one-time)
        if intervened and not ev_restored and t >= sc['reactivate_t']:
            ev_restored = True
            dPe_action  = 0.0
            Pe          = sc['Pe0']

        H   = live_H(H_hk, f)
        rf  = 0.30 + 0.10 * (t / t_end)
        ddt = swing_dfdt(Pm, Pe, H)  # ← swing eq with PINN's H + droop governor
        rs  = risk_score(H, ddt, rf)      # ← risk from physics, not from NN

        dfdt_pi[i]    = ddt
        risk_pi[i]    = rs['score']
        H_live_pi[i]  = H

        # Dispatch decision: PINN risk score crosses threshold
        if (not intervened
                and t >= sc['monitor_from']
                and rs['level'] in ('ALERT', 'CRITICAL')):
            intervened    = True
            dispatch_t    = t
            pre_ddt       = ddt          # save pre-dispatch physics for display
            pre_rs        = rs
            dPm_action   += sc['action_dPm']
            dPe_action   += sc['action_dPe']   # negative → demand falls
            # Recompute physics with new dispatch state
            Pm  = generation_at(sc, t, dPm_action)
            Pe  = sc['Pe0'] + dPe_action
            ddt = swing_dfdt(Pm, Pe, H)
            rs  = risk_score(H, ddt, rf)
            dfdt_pi[i] = ddt
            risk_pi[i] = rs['score']

            print(f'\n  [DISPATCH] t={t:.0f}s | f={f:.3f}Hz | '
                  f'df/dt(before)={pre_ddt:+.4f}Hz/s | '
                  f'risk={pre_rs["score"]:.3f} ({pre_rs["level"]})')
            print(f'  +{sc["action_dPm"]:.0f}MW gas peakers  '
                  f'{sc["action_dPe"]:.0f}MW EV shed ({sc["ev_stations_shed"]} stations)')
            print(f'  ΔP: {sc["event_dPm"]:+.0f}MW → {Pm-Pe:+.0f}MW  '
                  f'df/dt: {pre_ddt:+.4f} → {ddt:+.4f} Hz/s')

        # 51 Hz cap: over-frequency relay would trip generation above this
        f_pi[i + 1]      = max(0.0, min(51.0, f + ddt * dt))
        risk_pi[i + 1]   = rs['score']
        H_live_pi[i + 1] = H

    return {
        't':          t_vec,
        'f_ni':       f_ni,
        'f_pi':       f_pi,
        'dfdt_ni':    dfdt_ni,
        'dfdt_pi':    dfdt_pi,
        'risk_ni':    risk_ni,
        'risk_pi':    risk_pi,
        'H_live':     H_live_pi,
        'sc':         sc,
        'scenario_key': scenario_key,
        'H_hk':       H_hk,
        'H_spain':    H_spain,
        'dispatch_t': dispatch_t,
    }


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_simulation(result: dict, save_path: str = None):
    t      = result['t']
    f_ni   = result['f_ni']
    f_pi   = result['f_pi']
    dpi    = result['dfdt_pi']
    risk   = result['risk_pi']
    H_live = result['H_live']
    sc     = result['sc']
    disp_t = result['dispatch_t']

    fig, axes = plt.subplots(4, 1, figsize=(14, 13), sharex=True)
    fig.suptitle(
        f'Hong Kong Grid — Physics Simulation (PINN-parameterised)\n'
        f'Scenario: {sc["label"]}\n'
        f'PINN: H_spain={result["H_spain"]:.3f}s → H_hk={result["H_hk"]:.2f}s  '
        f'|  Swing equation governs df/dt  |  Risk from live physics',
        fontsize=11, fontweight='bold',
    )

    # Panel 1: Frequency
    ax = axes[0]
    ax.plot(t, f_ni, color='#d7191c', lw=2.5, label='No intervention — blackout')
    ax.plot(t, f_pi, color='#1a9641', lw=2.5, label='PINN-triggered dispatch — recovery')
    ax.axhline(49.8, color='orange', ls='--', lw=1.2, label='49.8 Hz relay')
    ax.axhline(47.5, color='red',    ls=':',  lw=1.0, label='47.5 Hz UFLS')
    ax.axvline(sc['event_t'],  color='k',      ls=':', alpha=0.7)
    if disp_t:
        ax.axvline(disp_t, color='purple', ls=':', alpha=0.8)
        ax.text(disp_t + 0.5, 49.2, 'DISPATCH', color='purple', fontsize=8)
    ax.text(sc['event_t'] + 0.5, 49.2, 'Event', color='k', fontsize=8)
    ax.set_ylabel('Frequency (Hz)')
    ax.set_ylim(44, 51)
    ax.legend(fontsize=9, loc='lower left')
    ax.grid(alpha=0.3)

    # Panel 2: df/dt (physics RoCoF from swing equation with PINN H)
    ax = axes[1]
    ax.plot(t, dpi,  color='#756bb1', lw=2, label='df/dt — PINN physics (dispatch case)')
    ax.plot(t, result['dfdt_ni'], color='#d7191c', lw=1.5, ls='--', alpha=0.6,
            label='df/dt — no intervention')
    ax.axhline(0,          color='k',      ls='-',  lw=0.5)
    ax.axhline(-ROCOF_ALERT, color='orange', ls='--', lw=1.0, label=f'ALERT  {-ROCOF_ALERT:+.2f}Hz/s')
    ax.axhline(-ROCOF_CRIT,  color='red',    ls='--', lw=1.0, label=f'CRITICAL {-ROCOF_CRIT:+.2f}Hz/s')
    ax.set_ylabel('df/dt  (Hz/s)')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)

    # Panel 3: Risk score
    ax = axes[2]
    ax.fill_between(t, 0,   0.3,  alpha=0.07, color='green',  label='NORMAL')
    ax.fill_between(t, 0.3, 0.6,  alpha=0.07, color='orange', label='ALERT')
    ax.fill_between(t, 0.6, 1.05, alpha=0.07, color='red',    label='CRITICAL')
    ax.plot(t, result['risk_ni'], color='#d7191c', lw=1.5, ls='--', alpha=0.6,
            label='Risk — no intervention')
    ax.plot(t, risk, color='#2c7bb6', lw=2, label='Risk — PINN dispatch')
    ax.axhline(0.3, color='orange', ls='--', lw=0.8)
    ax.axhline(0.6, color='red',    ls='--', lw=0.8)
    ax.set_ylabel('Risk Score')
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=9, loc='upper left')
    ax.grid(alpha=0.3)

    # Panel 4: Live inertia H(t)
    ax = axes[3]
    ax.plot(t, H_live, color='#fdae61', lw=2, label='H_live (UFLS-adjusted)')
    ax.axhline(H_VULNERABLE, color='orange', ls='--', lw=1,
               label=f'H_vulnerable = {H_VULNERABLE}s')
    ax.axhline(H_CRITICAL,   color='red',    ls='--', lw=1,
               label=f'H_critical = {H_CRITICAL}s')
    ax.set_ylabel('Inertia H (s)')
    ax.set_xlabel('Time (s)')
    ax.set_ylim(0, result['H_hk'] * 1.1)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f'[plot] Saved → {save_path}')
    else:
        plt.show()


def print_demo_narrative(result: dict):
    sc      = result['sc']
    t       = result['t']
    f_ni    = result['f_ni']
    f_pi    = result['f_pi']
    risk_pi = result['risk_pi']
    dfdt_pi = result['dfdt_pi']
    disp_t  = result['dispatch_t']

    blackout_t  = next((t[i] for i, f in enumerate(f_ni) if f < 1.0), None)
    alert_t     = next((t[i] for i, r in enumerate(risk_pi) if r >= 0.3), None)
    crit_t      = next((t[i] for i, r in enumerate(risk_pi) if r >= 0.6), None)
    worst_dfdt  = float(np.min(dfdt_pi[dfdt_pi != 0]))
    recovery_f  = f_pi[min(int(t[-1] - 1), len(f_pi) - 1)]

    print('\n' + '=' * 65)
    print(' DEMO NARRATIVE — HK Grid Digital Twin (Layer 4)')
    print('=' * 65)
    print(f'\n[T=0–{sc["event_t"]:.0f}s]  Normal HK grid.  Risk = GREEN')
    print(f'              f = {F0} Hz  |  H_hk = {result["H_hk"]:.2f}s  |  df/dt = 0')
    print(f'\n[T={sc["event_t"]:.0f}s]     EVENT: {sc["label"]}')
    print(f'              ΔPm = {sc["event_dPm"]:+.0f} MW  '
          f'→  ΔP = {sc["event_dPm"]:.0f} MW (net deficit)')
    print(f'              Swing equation: df/dt = '
          f'{swing_dfdt(sc["Pm0"]+sc["event_dPm"], sc["Pe0"], result["H_hk"]):+.4f} Hz/s')
    if alert_t is not None:
        print(f'\n[T={alert_t:.0f}s]    PINN risk → AMBER (score {risk_pi[int(alert_t)]:.3f})')
    if crit_t is not None:
        print(f'[T={crit_t:.0f}s]    PINN risk → RED   (score {risk_pi[int(crit_t)]:.3f})')
    if disp_t is not None:
        disp_i = int(disp_t)
        print(f'\n[T={disp_t:.0f}s]    PINN DISPATCH:')
        print(f'              + {sc["action_dPm"]:.0f} MW gas peakers')
        print(f'              − {abs(sc["action_dPe"]):.0f} MW EV + commercial load shed '
              f'({sc["ev_stations_shed"]} stations)')
        net_dP = sc['action_dPm'] - sc['action_dPe'] + sc['event_dPm']
        print(f'              ΔP flips from {sc["event_dPm"]:+.0f} MW to {net_dP:+.0f} MW')
        print(f'              df/dt reverses → {dfdt_pi[disp_i]:+.4f} Hz/s (frequency recovers)')
    print(f'\n[Physics]     Peak RoCoF (no intervention) = {worst_dfdt:+.3f} Hz/s')
    print(f'              H degrades via UFLS to '
          f'{min(result["H_live"]):+.2f}s before dispatch')
    if blackout_t:
        print(f'\n[No dispatch] Blackout at T={blackout_t:.0f}s')
    print(f'\n[With PINN]   f at end of simulation = {recovery_f:.2f} Hz')
    print(f'\n[Transfer]    Spain H={result["H_spain"]:.4f}s → HK H={result["H_hk"]:.4f}s')
    print(f'              PINN correction: {100*(result["H_spain"]/SPAIN_H_NOM - 1):+.1f}% from nominal\n')


# ── Public API ────────────────────────────────────────────────────────────────

def simulate_hk_scenario(
    model=None,
    scenario: str = 'typhoon_offshore_wind',
    checkpoint_path: str = None,
    save_plot: str = None,
) -> dict:
    if model is None:
        if checkpoint_path is None:
            checkpoint_path = os.path.join(
                os.path.dirname(__file__), '../outputs/pinn_grid_spain_trained.pt')
        if os.path.exists(checkpoint_path):
            from risk_score import load_trained_model
            model = load_trained_model(checkpoint_path)
        else:
            print('[sim] No checkpoint — using initialised model')
            model = build_model(H_init=1.14, freeze_H=False)
            model.eval()

    print(f'\n[sim] Scenario: {scenario}')
    result = run_scenario(model, scenario_key=scenario)
    print_demo_narrative(result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', default=None)
    parser.add_argument('--scenario',   default='typhoon_offshore_wind',
                        choices=list(SCENARIOS.keys()))
    parser.add_argument('--no-plot', action='store_true')
    args = parser.parse_args()

    out_dir = os.path.join(os.path.dirname(__file__), '../outputs')
    os.makedirs(out_dir, exist_ok=True)
    plot_path = None if args.no_plot else os.path.join(out_dir, 'hk_simulation.png')

    result = simulate_hk_scenario(
        scenario        = args.scenario,
        checkpoint_path = args.checkpoint,
        save_plot       = plot_path,
    )
    if plot_path:
        plot_simulation(result, save_path=plot_path)
