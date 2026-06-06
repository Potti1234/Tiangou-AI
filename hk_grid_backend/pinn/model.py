"""
GridPINN: Physics-Informed Neural Network for grid frequency dynamics.

Input:  [t, Pm, Pe, renewable_fraction, H_prior]  (5 features)
Output: f(t)  predicted frequency [Hz]

H is a learnable scalar (log-parameterized) refined during training.
"""

import torch
import torch.nn as nn


class GridPINN(nn.Module):

    def __init__(self, hidden_dim: int = 64, n_layers: int = 4):
        super().__init__()

        layers = [nn.Linear(5, hidden_dim), nn.Tanh()]
        for _ in range(n_layers - 1):
            layers += [nn.Linear(hidden_dim, hidden_dim), nn.Tanh()]
        layers += [nn.Linear(hidden_dim, 1)]
        self.net = nn.Sequential(*layers)

        # log-parameterized so H > 0 always
        # init: log(1.567) ≈ 0.449 — HK grid pre-disturbance inertia
        self.log_H = nn.Parameter(torch.tensor([0.449]))

    @property
    def H(self) -> torch.Tensor:
        return torch.exp(self.log_H)

    def forward(
        self,
        t: torch.Tensor,
        Pm: torch.Tensor,
        Pe: torch.Tensor,
        renewable_frac: torch.Tensor,
        H_prior: torch.Tensor,
    ) -> torch.Tensor:
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
        """Single-sample inference returning a Python float."""
        self.eval()
        with torch.no_grad():
            t_t      = torch.tensor([t],              dtype=torch.float32)
            Pm_t     = torch.tensor([Pm],             dtype=torch.float32)
            Pe_t     = torch.tensor([Pe],             dtype=torch.float32)
            rf_t     = torch.tensor([renewable_frac], dtype=torch.float32)
            Hp_t     = torch.tensor([H_prior],        dtype=torch.float32)
            f_pred   = self.forward(t_t, Pm_t, Pe_t, rf_t, Hp_t)
        return f_pred.item()

    def get_H_estimate(self) -> float:
        return self.H.item()


def build_pinn(hidden_dim: int = 64, n_layers: int = 4) -> GridPINN:
    return GridPINN(hidden_dim=hidden_dim, n_layers=n_layers)
