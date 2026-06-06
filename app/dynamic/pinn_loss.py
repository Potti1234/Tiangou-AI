"""PINN loss helpers.

The main app does not train during startup. This module keeps the moved PINN
boundary available for explicit future training workflows without coupling the
API to prototype datasets.
"""

from __future__ import annotations


def physics_residual_loss(*args, **kwargs):
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("torch is required for PINN training losses") from exc
    return torch.tensor(0.0, dtype=torch.float32)

