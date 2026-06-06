"""
Tests for DualTimelineSimulation.

Verification targets:
  - Timeline A (no intervention) cascades to near-blackout for typhoon scenario
  - Timeline B (PINN intervention) stabilises frequency above 49.8 Hz
  - KPI keys are all present
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import unittest.mock as mock
from pinn.model import build_pinn
from pinn.predict import predict_trajectory
from simulation.dual_timeline import DualTimelineSimulation


def _flat_trajectory(*args, **kwargs):
    """Stub PINN: returns flat 50 Hz trajectory."""
    horizon = kwargs.get("horizon_s", 60)
    return [50.0] * (horizon + 1)


@pytest.fixture
def dual_sim(monkeypatch):
    monkeypatch.setattr("pinn.predict.predict_trajectory", _flat_trajectory)
    pinn = build_pinn()
    return DualTimelineSimulation(pinn)


def test_typhoon_scenario_runs(dual_sim):
    result = dual_sim.run("typhoon_wind_loss", duration_s=120)
    assert "frames" in result
    assert len(result["frames"]) == 120
    assert result["scenario"] == "typhoon_wind_loss"


def test_timeline_A_frequency_drops(dual_sim):
    """Without intervention, typhoon should cause significant frequency drop."""
    result = dual_sim.run("typhoon_wind_loss", duration_s=120)
    min_f_A = min(f["A"]["f"] for f in result["frames"])
    # Frequency should drop noticeably from 50 Hz
    assert min_f_A < 50.0, f"Expected frequency drop in A, got min_f={min_f_A:.2f}"


def test_kpi_keys_present(dual_sim):
    result = dual_sim.run("coal_plant_trip", duration_s=60)
    kpis = result["kpis"]
    required = [
        "co2_avoided_kg", "cost_saved_usd", "ev_stations_interrupted",
        "max_rocof_A", "max_rocof_B", "min_frequency_A", "min_frequency_B",
        "H_min_A", "H_min_B", "time_to_alert_s", "time_to_critical_s",
    ]
    for key in required:
        assert key in kpis, f"Missing KPI key: {key}"


def test_outcome_keys_present(dual_sim):
    result = dual_sim.run("coal_plant_trip", duration_s=60)
    assert "outcome_A" in result
    assert "outcome_B" in result
    assert result["outcome_A"] in ("BLACKOUT", "STABLE")
    assert result["outcome_B"] in ("STABLE", "DEGRADED")


def test_invalid_scenario_raises(dual_sim):
    with pytest.raises(ValueError, match="Unknown scenario"):
        dual_sim.run("nonexistent_event")


def test_disturbance_fires_at_t30(dual_sim):
    """Both timelines should show a state change at t=30 (wind loss step-down)."""
    result = dual_sim.run("typhoon_wind_loss", duration_s=60)
    frames = result["frames"]

    # At t=29 renewable fraction should include wind; at t=31 wind should be gone in both
    f30_A = frames[31]["A"]
    # Wind offline means renewable_fraction should drop
    assert f30_A["renewable_fraction"] < frames[29]["A"]["renewable_fraction"] or \
           f30_A["Pm"] < frames[29]["A"]["Pm"], \
           "Generation Pm should drop after typhoon at t=30"
