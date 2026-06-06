"""
GridPINN: Physics-Informed Neural Network for power grid frequency dynamics.

Architecture:
  Input:  [t_norm, Pm_norm, Pe_norm, renewable_frac_norm]  (4 features)
  Output: f(t)  – predicted grid frequency (normalised)

H (system inertia constant, seconds) is a learnable scalar embedded as
log_H so that H = exp(log_H) > 0 always.  It is initialised to the
Spain pre-event value of ~1.14 s.
"""

import sys
sys.path.insert(0, '/mnt/data/hackathon/venv_pkgs')

import torch
import torch.nn as nn
import math


class GridPINN(nn.Module):
    """
    Standard PINN for grid frequency dynamics with learnable inertia H.

    The swing equation is enforced as a physics residual loss during training:
        df/dt = (f0 / (2 * H * S_base)) * (Pm - Pe)

    H is parameterised via log_H so optimisation is unconstrained while H
    stays strictly positive.
    """

    def __init__(
        self,
        hidden_dim: int = 64,
        n_hidden: int = 3,
        H_init: float = 1.14,       # Spain pre-event inertia (seconds)
        freeze_H: bool = True,      # Phase 1: freeze H while data loss settles
    ):
        super().__init__()

        layers = [nn.Linear(4, hidden_dim), nn.Tanh()]
        for _ in range(n_hidden - 1):
            layers += [nn.Linear(hidden_dim, hidden_dim), nn.Tanh()]
        layers.append(nn.Linear(hidden_dim, 1))
        self.net = nn.Sequential(*layers)

        # log_H parameterisation: H = exp(log_H)
        self.log_H = nn.Parameter(
            torch.tensor([math.log(H_init)], dtype=torch.float32),
            requires_grad=(not freeze_H),
        )

        self._init_weights()

    def _init_weights(self):
        for m in self.net.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                nn.init.zeros_(m.bias)

    @property
    def H(self) -> torch.Tensor:
        """System inertia constant H in seconds (always positive)."""
        return torch.exp(self.log_H)

    def freeze_H(self):
        self.log_H.requires_grad_(False)

    def unfreeze_H(self):
        self.log_H.requires_grad_(True)

    def forward(
        self,
        t: torch.Tensor,
        Pm: torch.Tensor,
        Pe: torch.Tensor,
        renewable_frac: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            t, Pm, Pe, renewable_frac: shape [N] – all normalised to [0,1]
        Returns:
            f_pred: shape [N, 1] – predicted normalised frequency
        """
        x = torch.stack([t, Pm, Pe, renewable_frac], dim=1)
        return self.net(x)


def build_model(H_init: float = 1.14, freeze_H: bool = True) -> GridPINN:
    return GridPINN(hidden_dim=64, n_hidden=3, H_init=H_init, freeze_H=freeze_H)


if __name__ == '__main__':
    model = build_model()
    print(f'H_init = {model.H.item():.4f} s')
    print(f'log_H  = {model.log_H.item():.4f}')
    print(f'H frozen: {not model.log_H.requires_grad}')

    N = 8
    t  = torch.rand(N)
    Pm = torch.rand(N)
    Pe = torch.rand(N)
    rf = torch.rand(N)
    f  = model(t, Pm, Pe, rf)
    print(f'Forward output shape: {f.shape}')
    total_params = sum(p.numel() for p in model.parameters())
    print(f'Total parameters: {total_params}')
