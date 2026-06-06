"""
plot_simulation.py — run the dual-timeline simulation and produce
a multi-panel technical figure saved as simulation_results.png.

Panels:
  1. Grid Frequency (Hz)          — A vs B + safety bands
  2. RoCoF |df/dt| (Hz/s)         — A vs B + relay thresholds
  3. System Inertia H (s)         — A vs B + risk bands
  4. Generation vs Demand (MW)    — B timeline (shows dispatch actions)
  5. Composite Risk Score         — B timeline + ALERT/CRITICAL thresholds
  6. PINN 60-s Frequency Forecast — sampled snapshots from B timeline
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

from config.hk_grid import get_baseline_copy, get_ev_stations_copy
from config.disturbances import DISTURBANCE_EVENTS
from pinn.model import build_pinn
from pinn.train import train_pinn, load_checkpoint, save_checkpoint
from simulation.dual_timeline import DualTimelineSimulation

# ── colours ────────────────────────────────────────────────────────────────
C_A       = "#e74c3c"   # red  — no intervention
C_B       = "#2ecc71"   # green — PINN intervention
C_BAND    = "#f0f0f0"
C_WARN    = "#f39c12"
C_CRIT    = "#e74c3c"
C_ALERT   = "#e67e22"
ALPHA_BND = 0.25

SCENARIO  = "typhoon_wind_loss"
DURATION  = 500          # seconds — long enough for CCGT ramp (80 MW/min × 300 s) to complete
CKPT      = "pinn_checkpoint.pt"
OUT_FILE  = "simulation_results.png"

# Forecast snapshot times (seconds into simulation)
FORECAST_SNAPSHOTS = [28, 40, 60, 160, 300]


def load_or_train_pinn():
    if Path(CKPT).exists():
        return load_checkpoint(CKPT)
    print("Training PINN (first run)…")
    m = train_pinn(xlsx_path="data/Spain_Blackout_28Apr2025_Dataset.xlsx")
    save_checkpoint(m, CKPT)
    return m


def extract_series(frames, timeline: str, field: str):
    return [f[timeline][field] for f in frames]


def main():
    print(f"Running dual-timeline simulation: {SCENARIO} ({DURATION} s)…")
    pinn    = load_or_train_pinn()
    dual    = DualTimelineSimulation(pinn)
    result  = dual.run(SCENARIO, DURATION)

    frames  = result["frames"]
    kpis    = result["kpis"]
    t       = [f["t"] for f in frames]

    # ── extract series ──────────────────────────────────────────────────
    f_A      = extract_series(frames, "A", "f")
    f_B      = extract_series(frames, "B", "f")
    rocof_A  = [abs(v) for v in extract_series(frames, "A", "df_dt")]
    rocof_B  = [abs(v) for v in extract_series(frames, "B", "df_dt")]
    H_B_phys = extract_series(frames, "B", "H_physical")
    H_B_pinn = extract_series(frames, "B", "H_pinn")
    Pm_B     = extract_series(frames, "B", "Pm")
    Pe_B     = extract_series(frames, "B", "Pe")
    risk_B   = extract_series(frames, "B", "risk_score")

    # Intervention markers (t where action was taken)
    action_times = [f["t"] for f in frames if f["actions_taken"]]
    action_labels= ["; ".join(f["actions_taken"]) for f in frames if f["actions_taken"]]

    # PINN trajectory snapshots (only from B)
    snap_data = {}
    for snap_t in FORECAST_SNAPSHOTS:
        if snap_t < len(frames):
            traj = frames[snap_t]["B"]["trajectory_60s"]
            snap_data[snap_t] = traj

    # ── layout ──────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(18, 22))
    fig.patch.set_facecolor("#0f1117")

    gs = fig.add_gridspec(
        3, 2,
        hspace=0.42, wspace=0.32,
        left=0.07, right=0.97, top=0.93, bottom=0.05,
    )

    ax_freq    = fig.add_subplot(gs[0, 0])
    ax_rocof   = fig.add_subplot(gs[0, 1])
    ax_H       = fig.add_subplot(gs[1, 0])
    ax_pw      = fig.add_subplot(gs[1, 1])
    ax_risk    = fig.add_subplot(gs[2, 0])
    ax_fcast   = fig.add_subplot(gs[2, 1])

    axes = [ax_freq, ax_rocof, ax_H, ax_pw, ax_risk, ax_fcast]
    for ax in axes:
        ax.set_facecolor("#1a1d27")
        ax.tick_params(colors="#cccccc", labelsize=9)
        ax.xaxis.label.set_color("#cccccc")
        ax.yaxis.label.set_color("#cccccc")
        ax.title.set_color("#ffffff")
        for spine in ax.spines.values():
            spine.set_edgecolor("#444")

    def vline_event(ax, x=30, label="Disturbance (t=30 s)"):
        ax.axvline(x, color="#aaaaaa", lw=1, ls="--", alpha=0.7)
        ax.text(x + 1, ax.get_ylim()[1] * 0.97, label,
                color="#aaaaaa", fontsize=7, va="top")

    # ── 1. Frequency ─────────────────────────────────────────────────────
    ax = ax_freq
    # Safety bands
    ax.axhspan(49.8, 50.2, color="#2ecc71", alpha=0.08, label="Normal band")
    ax.axhspan(49.5, 49.8, color=C_WARN,    alpha=0.10, label="Alert band")
    ax.axhspan(49.0, 49.5, color=C_CRIT,    alpha=0.10, label="UFLS band")
    ax.axhline(49.8, color="#2ecc71", lw=0.6, ls=":", alpha=0.6)
    ax.axhline(49.0, color=C_CRIT,    lw=0.6, ls=":", alpha=0.6)

    ax.plot(t, f_A, color=C_A, lw=1.8, label="No Intervention (A)")
    ax.plot(t, f_B, color=C_B, lw=1.8, label="PINN Dispatch (B)")
    ax.axhline(50.0, color="white", lw=0.5, ls="--", alpha=0.3)

    for at in action_times:
        ax.axvline(at, color="#3498db", lw=0.8, ls=":", alpha=0.6)

    ax.set_title("Grid Frequency", fontweight="bold")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_xlabel("Time (s)")
    ax.set_ylim(min(min(f_A), min(f_B)) - 0.3, 50.5)
    ax.legend(fontsize=8, facecolor="#252836", labelcolor="white",
              loc="lower left", framealpha=0.8)
    vline_event(ax)

    # annotate outcome
    outcome_color = "#2ecc71" if result["outcome_B"] == "STABLE" else C_WARN
    ax.text(DURATION * 0.98, min(f_B) + 0.1,
            f"B: {result['outcome_B']}",
            color=outcome_color, fontsize=9, ha="right", fontweight="bold")
    ax.text(DURATION * 0.98, min(f_A) + 0.05,
            f"A: {result['outcome_A']}",
            color=C_A, fontsize=9, ha="right", fontweight="bold")

    # ── 2. RoCoF ─────────────────────────────────────────────────────────
    ax = ax_rocof
    ax.axhline(0.1, color="#f1c40f", lw=0.8, ls="--", alpha=0.7, label="Safe limit (0.1 Hz/s)")
    ax.axhline(0.3, color=C_WARN,   lw=0.8, ls="--", alpha=0.7, label="Relay trigger (0.3 Hz/s)")
    ax.axhline(0.5, color=C_CRIT,   lw=0.8, ls="--", alpha=0.7, label="Cascade risk (0.5 Hz/s)")
    ax.fill_between(t, rocof_A, alpha=0.15, color=C_A)
    ax.fill_between(t, rocof_B, alpha=0.15, color=C_B)
    ax.plot(t, rocof_A, color=C_A, lw=1.5, label="No Intervention (A)")
    ax.plot(t, rocof_B, color=C_B, lw=1.5, label="PINN Dispatch (B)")

    ax.set_title("Rate of Change of Frequency |df/dt|", fontweight="bold")
    ax.set_ylabel("|df/dt| (Hz/s)")
    ax.set_xlabel("Time (s)")
    ax.legend(fontsize=7.5, facecolor="#252836", labelcolor="white",
              loc="upper right", framealpha=0.8)
    vline_event(ax)
    ax.set_ylim(bottom=0)

    # ── 3. H_physical vs H_pinn (PINN online estimation insight) ─────────
    ax = ax_H
    ax.axhspan(3.0, 7.0, color="#2ecc71", alpha=0.08)
    ax.axhspan(1.5, 3.0, color="#f1c40f", alpha=0.08)
    ax.axhspan(1.0, 1.5, color=C_WARN,   alpha=0.10)
    ax.axhspan(0.0, 1.0, color=C_CRIT,   alpha=0.12)

    ax.axhline(1.5, color="#f1c40f", lw=0.7, ls=":", alpha=0.7)
    ax.axhline(1.0, color=C_WARN,   lw=0.7, ls=":", alpha=0.7)

    ax.plot(t, H_B_phys, color=C_B,       lw=2.0, label="H physical (spinning mass)")
    ax.plot(t, H_B_pinn, color="#e67e22",  lw=1.6, ls="--",
            label="H_pinn (estimated from f dynamics)")

    # Shade divergence between PINN estimate and physical
    ax.fill_between(t, H_B_phys, H_B_pinn, alpha=0.12, color="#e67e22",
                    label="PINN estimation error")

    for y, lbl, col in [(2.2, "WATCH", "#f1c40f"), (1.25, "ALERT", C_WARN)]:
        ax.text(2, y, lbl, color=col, fontsize=7, va="center", alpha=0.7)

    ax.set_title("Inertia H — Physical vs PINN Estimate (Timeline B)", fontweight="bold")
    ax.set_ylabel("H (seconds)")
    ax.set_xlabel("Time (s)")
    ax.legend(fontsize=8, facecolor="#252836", labelcolor="white",
              loc="lower right", framealpha=0.8)
    ax.text(DURATION * 0.98, max(H_B_pinn) * 1.02,
            "PINN infers H from frequency\ndynamics only — no plant metering",
            color="#e67e22", fontsize=7, ha="right", va="bottom", alpha=0.85)
    vline_event(ax)
    ax.set_ylim(bottom=0)

    # ── 4. Generation vs Demand (B) ────────────────────────────────────────
    ax = ax_pw
    ax.fill_between(t, Pm_B, Pe_B,
                    where=[p >= e for p, e in zip(Pm_B, Pe_B)],
                    alpha=0.18, color="#2ecc71", label="Surplus")
    ax.fill_between(t, Pm_B, Pe_B,
                    where=[p < e for p, e in zip(Pm_B, Pe_B)],
                    alpha=0.22, color=C_CRIT, label="Deficit")
    ax.plot(t, Pm_B, color="#3498db", lw=1.8, label="Generation Pm (B)")
    ax.plot(t, Pe_B, color="#e74c3c", lw=1.8, ls="--", label="Demand Pe (B)")

    # Mark dispatch actions
    for at, albl in zip(action_times, action_labels):
        ax.axvline(at, color="#f1c40f", lw=1.0, ls=":", alpha=0.8)
        ax.text(at + 1, max(Pm_B) * 0.99, "⚡", fontsize=8,
                color="#f1c40f", va="top")

    ax.set_title("Generation vs Demand — PINN Timeline (B)", fontweight="bold")
    ax.set_ylabel("Power (MW)")
    ax.set_xlabel("Time (s)")
    ax.legend(fontsize=8, facecolor="#252836", labelcolor="white",
              loc="lower right", framealpha=0.8)
    vline_event(ax)

    # ── 5. Risk Score (B) ─────────────────────────────────────────────────
    ax = ax_risk
    ax.axhspan(0.6, 1.0, color=C_CRIT,   alpha=0.12)
    ax.axhspan(0.3, 0.6, color=C_WARN,   alpha=0.10)
    ax.axhspan(0.1, 0.3, color="#f1c40f", alpha=0.08)

    ax.axhline(0.6, color=C_CRIT,   lw=0.8, ls="--", alpha=0.8, label="CRITICAL (0.6)")
    ax.axhline(0.3, color=C_WARN,   lw=0.8, ls="--", alpha=0.8, label="ALERT (0.3)")
    ax.axhline(0.1, color="#f1c40f", lw=0.8, ls="--", alpha=0.8, label="WATCH (0.1)")

    ax.fill_between(t, risk_B, alpha=0.25, color="#9b59b6")
    ax.plot(t, risk_B, color="#9b59b6", lw=1.8, label="Risk score (B)")

    for at in action_times:
        ax.axvline(at, color="#3498db", lw=0.8, ls=":", alpha=0.7)

    ax.text(5, 0.65, "CRITICAL", color=C_CRIT,   fontsize=7, alpha=0.8)
    ax.text(5, 0.35, "ALERT",    color=C_WARN,   fontsize=7, alpha=0.8)
    ax.text(5, 0.15, "WATCH",    color="#f1c40f", fontsize=7, alpha=0.8)
    ax.text(5, 0.04, "NORMAL",   color="#2ecc71", fontsize=7, alpha=0.8)

    ax.set_title("Composite Risk Score — PINN Timeline (B)", fontweight="bold")
    ax.set_ylabel("Risk Score [0–1]")
    ax.set_xlabel("Time (s)")
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8, facecolor="#252836", labelcolor="white",
              loc="upper right", framealpha=0.8)
    vline_event(ax)

    # ── 6. PINN 60-s Forecast Snapshots ───────────────────────────────────
    ax = ax_fcast
    cmap = plt.cm.plasma
    n_snaps = len(snap_data)

    for i, (snap_t, traj) in enumerate(sorted(snap_data.items())):
        traj_t = [snap_t + j for j in range(len(traj))]
        col    = cmap(i / max(n_snaps - 1, 1))
        ax.plot(traj_t, traj, color=col, lw=1.4, alpha=0.85,
                label=f"Forecast @ t={snap_t}s")
        ax.scatter([snap_t], [traj[0]], color=col, s=30, zorder=5)

    # Overlay actual B frequency in white
    ax.plot(t, f_B, color="white", lw=1.0, alpha=0.4, ls="--", label="Actual f (B)")

    ax.axhline(49.8, color="#2ecc71", lw=0.6, ls=":", alpha=0.6, label="49.8 Hz floor")
    ax.axhline(50.2, color="#2ecc71", lw=0.6, ls=":", alpha=0.6)

    ax.set_title("PINN 60-Second Frequency Forecast Snapshots (B)", fontweight="bold")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_xlabel("Time (s)")
    ax.legend(fontsize=7.5, facecolor="#252836", labelcolor="white",
              loc="lower right", framealpha=0.8)

    # ── Global title + KPI bar ─────────────────────────────────────────────
    scenario_label = DISTURBANCE_EVENTS[SCENARIO]["description"]
    fig.suptitle(
        f"HK Grid Digital Twin — {scenario_label}\n"
        f"Dual Timeline: No Intervention (A)  vs  PINN Dispatch (B)",
        fontsize=13, fontweight="bold", color="white", y=0.975,
    )

    # KPI annotation box
    kpi_text = (
        f"  Min f (A): {kpis['min_frequency_A']:.2f} Hz    "
        f"Min f (B): {kpis['min_frequency_B']:.2f} Hz    "
        f"Max RoCoF (A): {kpis['max_rocof_A']:.3f} Hz/s    "
        f"Max RoCoF (B): {kpis['max_rocof_B']:.3f} Hz/s    "
        f"EV interrupted: {kpis['ev_stations_interrupted']}    "
        f"CO₂ avoided: {kpis['co2_avoided_kg']:.0f} kg  "
    )
    fig.text(0.5, 0.005, kpi_text, ha="center", fontsize=8.5,
             color="#aaaaaa", fontfamily="monospace",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#1a1d27",
                       edgecolor="#444", alpha=0.9))

    plt.savefig(OUT_FILE, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"\nSaved → {OUT_FILE}")

    # Print KPI summary to terminal
    print("\n── KPI Summary ──────────────────────────────────────")
    print(f"  Outcome A (no intervention) : {result['outcome_A']}")
    print(f"  Outcome B (PINN dispatch)   : {result['outcome_B']}")
    print(f"  Min frequency A             : {kpis['min_frequency_A']:.3f} Hz")
    print(f"  Min frequency B             : {kpis['min_frequency_B']:.3f} Hz")
    print(f"  Max |RoCoF| A               : {kpis['max_rocof_A']:.4f} Hz/s")
    print(f"  Max |RoCoF| B               : {kpis['max_rocof_B']:.4f} Hz/s")
    print(f"  Min H A                     : {kpis['H_min_A']:.3f} s")
    print(f"  Min H B                     : {kpis['H_min_B']:.3f} s")
    print(f"  Time to ALERT               : {kpis['time_to_alert_s']} s")
    print(f"  Time to CRITICAL            : {kpis['time_to_critical_s']} s")
    print(f"  EV stations interrupted     : {kpis['ev_stations_interrupted']}")
    print(f"  CO₂ avoided (est.)          : {kpis['co2_avoided_kg']:.0f} kg")
    print(f"  Cost saved (est.)           : ${kpis['cost_saved_usd']:.0f}")
    print("─────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
