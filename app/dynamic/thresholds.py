"""Risk thresholds and frequency band definitions for dynamic simulation."""

F0 = 50.0
S_BASE = 12000.0

H_THRESHOLDS = {
    "NORMAL": 3.0,
    "WATCH": 1.5,
    "ALERT": 1.0,
    "CRITICAL": 0.0,
}

ROCOF_CASCADE = 0.5
FREQ_NORMAL_HI = 50.2
FREQ_NORMAL_LO = 49.8
FREQ_ALERT_LO = 49.5
FREQ_UFLS_LO = 49.0


def freq_band(f: float) -> str:
    if FREQ_NORMAL_LO <= f <= FREQ_NORMAL_HI:
        return "NORMAL"
    if FREQ_ALERT_LO <= f < FREQ_NORMAL_LO:
        return "ALERT"
    if FREQ_UFLS_LO <= f < FREQ_ALERT_LO:
        return "UFLS"
    return "BLACKOUT"


def compute_risk_score(H: float, rocof: float, f: float) -> float:
    h_score = max(0.0, min(1.0, 1.0 - H / H_THRESHOLDS["NORMAL"]))
    rocof_score = min(1.0, abs(rocof) / ROCOF_CASCADE)
    freq_score = min(1.0, abs(f - F0) / 1.0)
    return 0.4 * h_score + 0.4 * rocof_score + 0.2 * freq_score


def risk_level_from_score(score: float) -> str:
    if score >= 0.6:
        return "CRITICAL"
    if score >= 0.3:
        return "ALERT"
    if score >= 0.1:
        return "WATCH"
    return "NORMAL"

