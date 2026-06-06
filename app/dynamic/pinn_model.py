from __future__ import annotations

from typing import Any

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover - exercised when torch is unavailable
    torch = None
    nn = None


class FallbackPINN:
    """Small fallback used when torch/checkpoints are unavailable."""

    checkpoint_loaded = False

    def __init__(self, h_estimate: float = 2.5):
        self.h_estimate = h_estimate
        self.log_H = _FallbackScalar(h_estimate)

    def eval(self) -> None:
        return None

    def parameters(self) -> list[Any]:
        return []

    def get_H_estimate(self) -> float:
        return float(self.h_estimate)


class _FallbackScalar:
    def __init__(self, value: float):
        self._value = value

    def item(self) -> float:
        return self._value


if torch is not None:

    class GridPINN(nn.Module):
        def __init__(self, hidden_dim: int = 64, n_layers: int = 4):
            super().__init__()
            layers: list[Any] = [nn.Linear(5, hidden_dim), nn.Tanh()]
            for _ in range(n_layers - 1):
                layers += [nn.Linear(hidden_dim, hidden_dim), nn.Tanh()]
            layers += [nn.Linear(hidden_dim, 1)]
            self.net = nn.Sequential(*layers)
            self.log_H = nn.Parameter(torch.tensor([0.449]))
            self.checkpoint_loaded = False

        @property
        def H(self):
            return torch.exp(self.log_H)

        def forward(self, t, Pm, Pe, renewable_frac, H_prior):
            x = torch.stack([t, Pm, Pe, renewable_frac, H_prior], dim=-1)
            return self.net(x)

        def predict_frequency(
            self,
            t: float,
            Pm: float,
            Pe: float,
            renewable_frac: float,
            H_prior: float,
        ) -> float:
            self.eval()
            with torch.no_grad():
                f_pred = self.forward(
                    torch.tensor([t], dtype=torch.float32),
                    torch.tensor([Pm], dtype=torch.float32),
                    torch.tensor([Pe], dtype=torch.float32),
                    torch.tensor([renewable_frac], dtype=torch.float32),
                    torch.tensor([H_prior], dtype=torch.float32),
                )
            return f_pred.item()

        def get_H_estimate(self) -> float:
            return self.H.item()

else:
    GridPINN = FallbackPINN


def build_pinn(hidden_dim: int = 64, n_layers: int = 4):
    if torch is None:
        return FallbackPINN()
    return GridPINN(hidden_dim=hidden_dim, n_layers=n_layers)


def load_pinn_checkpoint(path: str):
    model = build_pinn()
    if torch is None:
        return model, False, "torch_unavailable"
    try:
        state = torch.load(path, map_location="cpu")
        if isinstance(state, dict) and "model_state_dict" in state:
            state = state["model_state_dict"]
        model.load_state_dict(state)
        model.checkpoint_loaded = True
        return model, True, None
    except FileNotFoundError:
        return model, False, "checkpoint_missing"
    except Exception as exc:
        return model, False, f"checkpoint_unusable:{exc.__class__.__name__}"

