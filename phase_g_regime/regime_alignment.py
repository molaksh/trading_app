"""
Phase G Regime Alignment: Helper functions for cross-asset comparison,
historical duration analysis, and volatility shift detection.

Used by regime_validator and regime_drift_detector.
"""

from typing import List, Optional


# Natural ordering: risk_on(0) → neutral(1) → risk_off(2) → panic(3)
REGIME_ORDER = {"risk_on": 0, "neutral": 1, "risk_off": 2, "panic": 3}

# Volatility band boundaries (annualized %)
_VOL_BANDS = [(20.0, "low"), (50.0, "medium"), (80.0, "high")]


def regime_distance(a: Optional[str], b: Optional[str]) -> int:
    """Distance between two regimes (0-3). Unknown regimes treated as neutral."""
    if a is None or b is None:
        return 2  # Assume moderate distance for unknown
    return abs(REGIME_ORDER.get(a, 1) - REGIME_ORDER.get(b, 1))


def regime_agreement_score(a: Optional[str], b: Optional[str]) -> float:
    """
    Agreement score between two regimes.
    1.0 = identical, 0.6 = adjacent, 0.3 = two steps, 0.1 = maximally different.
    """
    dist = regime_distance(a, b)
    return {0: 1.0, 1: 0.6, 2: 0.3, 3: 0.1}.get(dist, 0.5)


def duration_percentile(current_hours: float, history: List[float]) -> float:
    """
    Percentile rank of current duration vs historical durations.
    Returns 0-100. Higher = current regime has lasted longer than most.
    """
    if not history or len(history) < 3:
        return 50.0  # Insufficient history, assume median
    below = sum(1 for d in history if d <= current_hours)
    return (below / len(history)) * 100.0


def volatility_band(vol: float) -> str:
    """Categorize annualized volatility into bands."""
    for threshold, label in _VOL_BANDS:
        if vol < threshold:
            return label
    return "extreme"


def volatility_shift_detected(entry_vol: float, current_vol: float) -> bool:
    """Detect if volatility has shifted to a different band since regime entry."""
    if entry_vol <= 0 or current_vol <= 0:
        return False
    return volatility_band(entry_vol) != volatility_band(current_vol)
