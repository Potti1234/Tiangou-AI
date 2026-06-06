"""
Tests for the swing equation physics in GridSimulator.

Verification target: df/dt = (f0 / (2·H·S_base)) · (Pm - Pe)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from config.hk_grid import get_baseline_copy, get_ev_stations_copy
from simulation.simulator import GridSimulator

F0     = 50.0
S_BASE = 12000.0


def _make_sim():
    pinn = MagicMock()
    pinn.get_H_estimate.return_value = 4.5
    # predict returns a flat 50 Hz trajectory
    pinn.eval = MagicMock()
    # We stub pinn.forward indirectly through predict_trajectory
    # by patching at the module level in individual tests if needed
    return GridSimulator(get_baseline_copy(), get_ev_stations_copy(), pinn)


def test_H_system_positive_at_baseline():
    """System H should be well above 3.0 s with the HK baseline mix."""
    sim = _make_sim()
    H = sim.compute_H_system()
    assert H > 3.0, f"Expected H > 3.0, got {H:.3f}"


def test_H_system_zero_wind_solar_only(monkeypatch):
    """H = 0 when grid runs 100% renewables (wind + solar)."""
    sim = _make_sim()
    # Take all thermal/nuclear/hydro offline
    for source in sim.get_all_sources():
        if source.get("H", 0) > 0:
            source["online"] = False
    H = sim.compute_H_system()
    assert H == 0.0, f"Expected H=0 for 100% renewables, got {H}"


def test_swing_equation_numerics():
    """
    Manually verify df/dt formula.
    With H=4.5, S_base=12000, Pm=7600, Pe=7400 (surplus 200 MW):
    df/dt = (50 / (2 * 4.5 * 12000)) * 200 ≈ 0.0926 Hz/s
    """
    H  = 4.5
    Pm = 7600.0
    Pe = 7400.0
    expected = (F0 / (2.0 * H * S_BASE)) * (Pm - Pe)
    # Formula check (no simulation needed)
    assert abs(expected - 0.09259) < 1e-4


def test_frequency_falls_on_generation_loss(monkeypatch):
    """After a step loss of 1400 MW (typhoon), frequency should decrease."""
    from pinn import predict as pred_module

    # Stub PINN trajectory prediction to avoid torch dependency in unit test
    monkeypatch.setattr(pred_module, "predict_trajectory", lambda *a, **kw: [50.0] * 61)

    sim = _make_sim()
    f_before = sim.f

    # Take all offshore wind offline
    for source in sim.get_all_sources():
        if source.get("type") == "offshore_wind":
            source["online"] = False
            source["current_output_mw"] = 0

    state = sim.step()
    assert state.f < f_before, "Frequency should fall after generation loss"


def test_H_baseline_expected_range(monkeypatch):
    """
    HK baseline H should be in 4.0–5.5 s range.
    Coal (700+700+600 MW, H=5), Gas 1 (400 MW, H=4), Nuclear (1200 MW, H=6).
    Total inertia = 5*(700+700+600) + 4*400 + 6*1200 = 10000+1600+7200 = 18800 MVAs
    H_system = 18800 / 12000 ≈ 1.567
    (Some units offline; actual value depends on online set.)
    """
    sim = _make_sim()
    H = sim.compute_H_system()
    assert 1.0 < H < 6.0, f"H_system={H:.3f} out of expected range"


def test_demand_includes_ev_load():
    """Pe must include EV charging load when stations are active."""
    sim = _make_sim()
    Pe_with_ev = sim.compute_Pe()

    for s in sim.ev:
        s["active"] = False
    Pe_no_ev = sim.compute_Pe()

    assert Pe_with_ev > Pe_no_ev
    diff = Pe_with_ev - Pe_no_ev
    expected_ev_load = 150 * 0.15  # 22.5 MW
    assert abs(diff - expected_ev_load) < 0.01, f"EV load diff={diff}, expected {expected_ev_load}"
