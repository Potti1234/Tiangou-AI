"""
Data loading and preprocessing for Spain April 2025 blackout dataset.

Loads three sheets from the Excel file and produces normalised tensors
ready for PINN training.
"""

import sys
import os

sys.path.insert(0, '/mnt/data/hackathon/venv_pkgs')

import numpy as np
import pandas as pd
import torch
from dataclasses import dataclass
from typing import Tuple, Dict

EXCEL_PATH = os.path.join(os.path.dirname(__file__), '../data/Spain_Blackout_28Apr2025_Dataset.xlsx')

F0 = 50.0          # nominal frequency (Hz)
S_BASE = 32_000.0  # Spain system MVA base at event time


@dataclass
class DataBundle:
    """Holds all normalised tensors and the scalers needed to invert them."""
    # Phase-1 tensors (from Pre_Event_15min, slow time scale)
    t15_norm: torch.Tensor        # [N1] normalised time
    pm15_norm: torch.Tensor       # [N1] mechanical power
    pe15_norm: torch.Tensor       # [N1] electrical demand
    rf15_norm: torch.Tensor       # [N1] renewable fraction
    f15_norm: torch.Tensor        # [N1] frequency
    h15_norm: torch.Tensor        # [N1] inertia (supervision signal only)

    # Phase-2 tensors (from Second_by_Second, 1-second resolution)
    t1s_norm: torch.Tensor        # [N2]
    pm1s_norm: torch.Tensor       # [N2]
    pe1s_norm: torch.Tensor       # [N2]
    rf1s_norm: torch.Tensor       # [N2]
    f1s_norm: torch.Tensor        # [N2]
    dfdt1s_norm: torch.Tensor     # [N2] df/dt ground truth

    # Scalers (min/max of raw physical quantities)
    scalers: Dict[str, Tuple[float, float]]

    # Raw DataFrames (for inspection/plotting)
    df_15min: pd.DataFrame
    df_1s: pd.DataFrame
    df_hourly: pd.DataFrame


def _minmax(arr: np.ndarray) -> Tuple[np.ndarray, float, float]:
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-10:
        hi = lo + 1.0
    return (arr - lo) / (hi - lo), lo, hi


def _apply_minmax(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return (arr - lo) / (hi - lo)


def load_hourly(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name='Hourly_Demand_Generation',
                       header=4, usecols='A:K', engine='openpyxl')
    df.columns = ['hour', 'demand', 'solar', 'wind', 'hydro',
                  'nuclear', 'ccgt', 'other', 'total_gen', 'exports', 'balance']
    df = df.dropna(subset=['demand'])
    # Hour 13 onwards is post-blackout garbage — keep only 00-12
    df = df[df['demand'] > 10_000].copy()
    df['renewable_frac'] = (df['solar'] + df['wind']) / df['total_gen'].clip(lower=1)
    df['sync_gen'] = df['hydro'] + df['nuclear'] + df['ccgt']
    return df.reset_index(drop=True)


def load_pre_event_15min(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name='Pre_Event_15min',
                       header=3, usecols='A:H', engine='openpyxl')
    df.columns = ['time', 'demand', 'total_gen', 'renewable_frac',
                  'sync_gen', 'H_est', 'frequency', 'notes']
    df = df.dropna(subset=['demand'])

    # Build elapsed time in seconds from 11:00
    def parse_minutes(t):
        if isinstance(t, str):
            h, m = map(int, t.split(':'))
        else:
            h, m = t.hour, t.minute
        return (h - 11) * 60 + m
    df['t_s'] = df['time'].apply(parse_minutes) * 60.0

    df['Pm'] = df['total_gen'].astype(float)      # proxy: generation ≈ mechanical power
    df['Pe'] = df['demand'].astype(float)
    df['renewable_frac'] = df['renewable_frac'].astype(float)
    df['frequency'] = df['frequency'].astype(float)
    df['H_est'] = df['H_est'].astype(float)
    df['delta_P'] = df['Pm'] - df['Pe']
    return df.reset_index(drop=True)


def load_second_by_second(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name='Second_by_Second',
                       header=4, usecols='A:I', engine='openpyxl')
    df.columns = ['time', 't_s', 'Pe', 'Pm', 'delta_P',
                  'H', 'dfdt', 'frequency', 'event_marker']
    df = df.dropna(subset=['t_s'])
    df['t_s'] = df['t_s'].astype(float)
    df['Pe'] = df['Pe'].astype(float)
    df['Pm'] = df['Pm'].astype(float)
    df['delta_P'] = df['delta_P'].astype(float)
    df['H'] = df['H'].astype(float)
    df['dfdt'] = df['dfdt'].astype(float)
    df['frequency'] = df['frequency'].astype(float)

    # Renewable fraction is not in this sheet — estimate from H and S_base.
    # At t=0, renewable_frac ≈ 0.72 (from 12:30 row in Pre_Event_15min).
    # It rises during cascade as sync gen trips. Linear proxy:
    rf_start, rf_end = 0.72, 0.95
    t_max = df['t_s'].max()
    df['renewable_frac'] = rf_start + (rf_end - rf_start) * df['t_s'] / t_max

    return df.reset_index(drop=True)


def load_all(path: str = None) -> DataBundle:
    if path is None:
        path = EXCEL_PATH

    df_h = load_hourly(path)
    df_15 = load_pre_event_15min(path)
    df_1s = load_second_by_second(path)

    # ---- build shared scalers from the union of both training sets ----
    all_Pm = np.concatenate([df_15['Pm'].values, df_1s['Pm'].values])
    all_Pe = np.concatenate([df_15['Pe'].values, df_1s['Pe'].values])
    all_rf = np.concatenate([df_15['renewable_frac'].values, df_1s['renewable_frac'].values])
    all_f  = np.concatenate([df_15['frequency'].values, df_1s['frequency'].values])

    _, Pm_lo, Pm_hi = _minmax(all_Pm)
    _, Pe_lo, Pe_hi = _minmax(all_Pe)
    _, rf_lo, rf_hi = _minmax(all_rf)
    _, f_lo,  f_hi  = _minmax(all_f)

    # time is normalised independently per phase so gradients are well-scaled
    t15_raw = df_15['t_s'].values.astype(float)
    _, t15_lo, t15_hi = _minmax(t15_raw)

    t1s_raw = df_1s['t_s'].values.astype(float)
    _, t1s_lo, t1s_hi = _minmax(t1s_raw)

    dfdt_raw = df_1s['dfdt'].values.astype(float)
    _, dfdt_lo, dfdt_hi = _minmax(dfdt_raw)

    scalers = {
        'Pm':   (Pm_lo,   Pm_hi),
        'Pe':   (Pe_lo,   Pe_hi),
        'rf':   (rf_lo,   rf_hi),
        'f':    (f_lo,    f_hi),
        't15':  (t15_lo,  t15_hi),
        't1s':  (t1s_lo,  t1s_hi),
        'dfdt': (dfdt_lo, dfdt_hi),
    }

    def T(arr): return torch.tensor(arr, dtype=torch.float32)

    bundle = DataBundle(
        # Phase 1 – 15-min data
        t15_norm  = T(_apply_minmax(t15_raw, t15_lo, t15_hi)),
        pm15_norm = T(_apply_minmax(df_15['Pm'].values, Pm_lo, Pm_hi)),
        pe15_norm = T(_apply_minmax(df_15['Pe'].values, Pe_lo, Pe_hi)),
        rf15_norm = T(_apply_minmax(df_15['renewable_frac'].values, rf_lo, rf_hi)),
        f15_norm  = T(_apply_minmax(df_15['frequency'].values, f_lo, f_hi)),
        h15_norm  = T(df_15['H_est'].values.astype(float)),  # kept in physical units

        # Phase 2 – 1-second data
        t1s_norm    = T(_apply_minmax(t1s_raw, t1s_lo, t1s_hi)),
        pm1s_norm   = T(_apply_minmax(df_1s['Pm'].values, Pm_lo, Pm_hi)),
        pe1s_norm   = T(_apply_minmax(df_1s['Pe'].values, Pe_lo, Pe_hi)),
        rf1s_norm   = T(_apply_minmax(df_1s['renewable_frac'].values, rf_lo, rf_hi)),
        f1s_norm    = T(_apply_minmax(df_1s['frequency'].values, f_lo, f_hi)),
        dfdt1s_norm = T(_apply_minmax(dfdt_raw, dfdt_lo, dfdt_hi)),

        scalers   = scalers,
        df_15min  = df_15,
        df_1s     = df_1s,
        df_hourly = df_h,
    )
    return bundle


def denorm_frequency(f_norm: np.ndarray, scalers: Dict) -> np.ndarray:
    lo, hi = scalers['f']
    return f_norm * (hi - lo) + lo


def denorm_dfdt(dfdt_norm: np.ndarray, scalers: Dict) -> np.ndarray:
    lo, hi = scalers['dfdt']
    return dfdt_norm * (hi - lo) + lo


if __name__ == '__main__':
    bundle = load_all()
    print('Phase-1 (15min) samples:', bundle.t15_norm.shape)
    print('Phase-2 (1s)    samples:', bundle.t1s_norm.shape)
    print('H estimates (15min):', bundle.h15_norm.numpy())
    print('Frequency range (raw Hz):',
          bundle.scalers['f'][0], '–', bundle.scalers['f'][1])
