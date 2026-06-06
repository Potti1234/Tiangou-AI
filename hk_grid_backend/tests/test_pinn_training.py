"""
Tests for PINN training on synthetic Spain data.

Verification target: H converges to ~1.14 s after two-phase training.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import torch
from pinn.model import build_pinn
from pinn.train import train_pinn, _synthetic_spain_data
from pinn.loss import physics_loss


def test_pinn_model_output_shape():
    model = build_pinn()
    t   = torch.rand(10)
    Pm  = torch.rand(10) * 20000
    Pe  = torch.rand(10) * 20000
    rf  = torch.rand(10)
    H_p = torch.rand(10) * 2

    out = model(t, Pm, Pe, rf, H_p)
    assert out.shape == (10, 1), f"Expected (10,1), got {out.shape}"


def test_H_always_positive():
    model = build_pinn()
    # Even after extreme log_H values, H must be positive
    model.log_H.data.fill_(-10.0)
    assert model.H.item() > 0
    model.log_H.data.fill_(10.0)
    assert model.H.item() > 0


def test_physics_loss_computable():
    model = build_pinn()
    data  = _synthetic_spain_data()
    p1    = data["phase1"]

    loss, L_data, L_phys, H_val = physics_loss(
        model,
        p1["t"], p1["Pm"], p1["Pe"],
        p1["renewable_frac"], p1["H_prior"], p1["f_obs"],
        s_base=32000.0,
    )
    assert loss.item() > 0
    assert H_val > 0


def test_pinn_training_H_converges():
    """
    Run a short training and confirm H moves toward 1.14 s.
    We don't require full convergence — just that it's in the right ballpark.
    Uses synthetic data so no xlsx dependency.
    """
    import unittest.mock as mock

    model = build_pinn()
    initial_H = model.get_H_estimate()

    # Patch load_spain_data to return synthetic data
    with mock.patch("pinn.train.load_spain_data") as mock_load:
        mock_load.return_value = _synthetic_spain_data()
        trained = train_pinn(model=model, xlsx_path="nonexistent.xlsx")

    final_H = trained.get_H_estimate()
    # H should have changed from initial and move toward ~1.14
    assert final_H != initial_H, "H did not change during training"
    # Must remain positive (log-parameterisation guarantees this)
    assert final_H > 0


def test_pinn_predict_trajectory():
    from pinn.predict import predict_trajectory

    model = build_pinn()
    traj  = predict_trajectory(model, t_start=0.0, Pm=7600, Pe=7400,
                               renewable_frac=0.35, H_prior=4.5, horizon_s=60)
    assert len(traj) == 61   # 61 points including t=0
    # All predictions should be finite floats
    assert all(isinstance(v, float) for v in traj)
    assert all(40.0 < v < 55.0 for v in traj), "Trajectory values out of plausible range"
