"""Explicit PINN training entry points for the main app package.

Training is intentionally not invoked by FastAPI startup. The integrated API
uses a checkpoint when present and otherwise falls back to documented defaults.
"""

from __future__ import annotations

from app.dynamic.pinn_model import build_pinn


def train_pinn(*args, **kwargs):
    raise RuntimeError("Dynamic PINN training is not wired to API startup. Provide a main-app training dataset before calling train_pinn.")


def initialized_pinn():
    return build_pinn()

