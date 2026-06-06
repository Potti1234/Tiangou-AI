"""Risk thresholds and frequency band definitions."""

F0 = 50.0        # nominal frequency [Hz]
S_BASE = 12000.0  # HK grid base [MVA]

# Inertia constant H risk bands [seconds]
H_THRESHOLDS = {
    "NORMAL":   3.0,   # H > 3.0: thermal-dominated, safe
    "WATCH":    1.5,   # 1.5 < H < 3.0: elevated renewable share
    "ALERT":    1.0,   # 1.0 < H < 1.5: vulnerable, pre-dispatch
    "CRITICAL": 0.0,   # H < 1.0: imminent risk
}

def h_risk_level(H: float) -> str:
    if H > H_THRESHOLDS["NORMAL"]:
        return "NORMAL"
    elif H > H_THRESHOLDS["WATCH"]:
        return "WATCH"
    elif H > H_THRESHOLDS["ALERT"]:
        return "ALERT"
    else:
        return "CRITICAL"

# RoCoF thresholds [Hz/s]
ROCOF_SAFE     = 0.1   # |df/dt| < 0.1: safe
ROCOF_RELAY    = 0.3   # |df/dt| > 0.3: protection relay zone
ROCOF_CASCADE  = 0.5   # |df/dt| > 0.5: cascade likely

# Frequency bands [Hz]
FREQ_NORMAL_HI  = 50.2
FREQ_NORMAL_LO  = 49.8
FREQ_ALERT_LO   = 49.5
FREQ_UFLS_LO    = 49.0  # under-frequency load shedding activates
FREQ_BLACKOUT   = 49.0  # cascade / blackout imminent

def freq_band(f: float) -> str:
    if FREQ_NORMAL_LO <= f <= FREQ_NORMAL_HI:
        return "NORMAL"
    elif FREQ_ALERT_LO <= f < FREQ_NORMAL_LO:
        return "ALERT"
    elif FREQ_UFLS_LO <= f < FREQ_ALERT_LO:
        return "UFLS"
    else:
        return "BLACKOUT"

def compute_risk_score(H: float, rocof: float, f: float) -> float:
    """
    Composite risk score in [0, 1].
    Combines inertia risk, RoCoF risk, and frequency deviation.
    """
    # H score: 0 at H=3.0, 1 at H=0
    h_score = max(0.0, min(1.0, 1.0 - H / H_THRESHOLDS["NORMAL"]))

    # RoCoF score
    rocof_score = min(1.0, abs(rocof) / ROCOF_CASCADE)

    # Frequency deviation score
    freq_dev = abs(f - F0)
    freq_score = min(1.0, freq_dev / 1.0)  # normalized to 1 Hz deviation

    # Weighted composite
    return 0.4 * h_score + 0.4 * rocof_score + 0.2 * freq_score

def risk_level_from_score(score: float) -> str:
    if score >= 0.6:
        return "CRITICAL"
    elif score >= 0.3:
        return "ALERT"
    elif score >= 0.1:
        return "WATCH"
    else:
        return "NORMAL"
