"""
Two-phase training loop for GridPINN.

Phase 1 (epochs 0 – PHASE1_EPOCHS):
  Train on Pre_Event_15min data with H frozen.
  Goal: network learns the slow inertia-decline dynamics and data loss
  drops below the threshold (default 0.05) before H is unfrozen.

Phase 2 (epochs PHASE1_EPOCHS – TOTAL_EPOCHS):
  Fine-tune on Second_by_Second collapse data with H trainable.
  Goal: H converges to ~1.14 s and physics residual < 0.01.

Run:
  python train.py [--epochs 1500] [--phase1 500] [--lr 1e-3]
"""

import sys
import os
sys.path.insert(0, '/mnt/data/hackathon/venv_pkgs')

import argparse
import time
import torch
import torch.optim as optim
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# local imports
sys.path.insert(0, os.path.dirname(__file__))
from data_loader import load_all
from model import build_model
from loss import compute_loss_phase1, compute_loss_phase2

OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), '../outputs')
os.makedirs(OUTPUTS_DIR, exist_ok=True)

CHECKPOINT_PATH = os.path.join(OUTPUTS_DIR, 'pinn_grid_spain_trained.pt')
CURVES_PATH     = os.path.join(OUTPUTS_DIR, 'training_curves.png')


def save_checkpoint(model, epoch, histories):
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'H_final': model.H.item(),
        'training_loss_history': histories['total'],
        'physics_loss_history':  histories['physics'],
        'data_loss_history':     histories['data'],
        'H_history':             histories['H'],
    }, CHECKPOINT_PATH)


def plot_curves(histories, save_path=CURVES_PATH):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle('GridPINN Training Curves — Spain Blackout 28 Apr 2025', fontsize=13)

    epochs = range(len(histories['total']))

    axes[0, 0].semilogy(epochs, histories['total'], color='#2c7bb6')
    axes[0, 0].set_title('Total Loss')
    axes[0, 0].set_xlabel('Epoch')

    axes[0, 1].semilogy(epochs, histories['physics'], color='#d7191c', label='physics')
    axes[0, 1].semilogy(epochs, histories['data'],    color='#1a9641', label='data')
    axes[0, 1].set_title('Physics vs Data Loss')
    axes[0, 1].set_xlabel('Epoch')
    axes[0, 1].legend()

    axes[1, 0].plot(epochs, histories['H'], color='#fdae61', linewidth=2)
    axes[1, 0].axhline(1.14, color='k', linestyle='--', label='Spain pre-event (1.14 s)')
    axes[1, 0].set_title('Estimated Inertia H (s)')
    axes[1, 0].set_xlabel('Epoch')
    axes[1, 0].legend()

    if 'phase_boundary' in histories:
        pb = histories['phase_boundary']
        for ax in axes.flat:
            ax.axvline(pb, color='purple', linestyle=':', alpha=0.6, label='Phase 1→2')

    axes[1, 1].axis('off')
    final_H = histories['H'][-1] if histories['H'] else float('nan')
    final_phys = histories['physics'][-1] if histories['physics'] else float('nan')
    summary = (
        f"Final H = {final_H:.4f} s\n"
        f"Target  = 1.14 s\n"
        f"Error   = {abs(final_H - 1.14):.4f} s\n\n"
        f"Final physics residual: {final_phys:.6f}\n"
        f"Target: < 0.01\n"
        f"Pass: {'✓' if final_phys < 0.01 else '✗'}"
    )
    axes[1, 1].text(0.1, 0.5, summary, transform=axes[1, 1].transAxes,
                    fontsize=12, verticalalignment='center',
                    fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='#f0f0f0'))

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f'[plot] Saved training curves → {save_path}')


def train(
    total_epochs: int = 1500,
    phase1_epochs: int = 500,
    lr: float = 1e-3,
    phase1_data_threshold: float = 0.05,
    log_every: int = 50,
    lambda_physics: float = 10.0,
):
    print('=' * 60)
    print(' GridPINN Training — Spain Blackout 28 Apr 2025')
    print('=' * 60)

    # ---- load data ----
    print('[data] Loading dataset …')
    bundle = load_all()
    print(f'[data] Phase-1 samples (15min): {bundle.t15_norm.shape[0]}')
    print(f'[data] Phase-2 samples (1s):    {bundle.t1s_norm.shape[0]}')

    # ---- build model ----
    model = build_model(H_init=1.14, freeze_H=True)
    print(f'[model] H initialised = {model.H.item():.4f} s  (frozen)')

    optimizer = optim.Adam(
        [p for p in model.parameters() if p.requires_grad],
        lr=lr,
    )
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_epochs, eta_min=1e-5)

    histories = {'total': [], 'physics': [], 'data': [], 'H': []}
    best_physics_loss = float('inf')
    phase2_started = False

    start_time = time.time()

    for epoch in range(1, total_epochs + 1):

        # ---- Phase 1 → Phase 2 transition ----
        if epoch == phase1_epochs + 1 and not phase2_started:
            model.unfreeze_H()
            # rebuild optimiser to include log_H
            optimizer = optim.Adam(model.parameters(), lr=lr * 0.1)
            scheduler = optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=total_epochs - phase1_epochs, eta_min=1e-6)
            phase2_started = True
            histories['phase_boundary'] = epoch
            print(f'\n[train] === Phase 2 START (epoch {epoch}) — H unfrozen ===')
            print(f'         Data loss at transition: {histories["data"][-1]:.5f}')

        # ---- forward + loss ----
        model.train()
        optimizer.zero_grad()

        if epoch <= phase1_epochs:
            loss, l_data, l_phys, H_val = compute_loss_phase1(
                model, bundle, lambda_physics=lambda_physics)
        else:
            loss, l_data, l_phys, H_val = compute_loss_phase2(
                model, bundle, lambda_physics=lambda_physics)

        loss.backward()
        # gradient clipping for stability
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        histories['total'].append(loss.item())
        histories['physics'].append(l_phys)
        histories['data'].append(l_data)
        histories['H'].append(H_val)

        # ---- logging ----
        if epoch % log_every == 0 or epoch == 1:
            elapsed = time.time() - start_time
            phase = '1' if epoch <= phase1_epochs else '2'
            print(
                f'[epoch {epoch:5d}/{total_epochs}  phase={phase}] '
                f'loss={loss.item():.5f}  data={l_data:.5f}  '
                f'phys={l_phys:.5f}  H={H_val:.4f}s  '
                f't={elapsed:.0f}s'
            )

        # ---- save best checkpoint (by physics loss in phase 2) ----
        if epoch > phase1_epochs and l_phys < best_physics_loss:
            best_physics_loss = l_phys
            save_checkpoint(model, epoch, histories)

    # always save final checkpoint
    save_checkpoint(model, total_epochs, histories)
    print(f'\n[train] Training complete.')
    print(f'  Final H          = {model.H.item():.4f} s  (target ~1.14 s)')
    print(f'  Final phys loss  = {histories["physics"][-1]:.6f}  (target < 0.01)')
    print(f'  Best phys loss   = {best_physics_loss:.6f}')

    plot_curves(histories)
    return model, histories


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs',  type=int,   default=1500)
    parser.add_argument('--phase1',  type=int,   default=500)
    parser.add_argument('--lr',      type=float, default=1e-3)
    parser.add_argument('--lambda-physics', type=float, default=10.0,
                        dest='lambda_physics')
    args = parser.parse_args()

    train(
        total_epochs  = args.epochs,
        phase1_epochs = args.phase1,
        lr            = args.lr,
        lambda_physics= args.lambda_physics,
    )
