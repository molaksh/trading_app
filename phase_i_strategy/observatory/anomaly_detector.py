"""
Strategy Anomaly Detector (Phase I-A).

Checks for:
- ZERO_SIGNAL: Strategy produces 0 non-FLAT signals for >4 hours
- ALL_FLAT: Strategy returns FLAT for >48 consecutive cycles
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from phase_i_strategy.config import (
    ZERO_SIGNAL_THRESHOLD_HOURS,
    ALL_FLAT_CYCLE_THRESHOLD,
)
from phase_i_strategy.persistence import PhaseIPersistence

logger = logging.getLogger(__name__)


class StrategyAnomalyDetector:
    """
    Detects strategy anomalies from recorded signal history.

    Reads signals.jsonl and checks for known failure patterns.
    """

    def __init__(self, persistence: PhaseIPersistence):
        self.persistence = persistence

    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """
        Scan recent signals for anomalies.

        Returns:
            List of anomaly records.
        """
        signals = self.persistence.load_recent_signals(max_lines=5000)
        if not signals:
            logger.debug("No signals to analyze for anomalies")
            return []

        anomalies = []
        anomalies.extend(self._check_zero_signal(signals))
        anomalies.extend(self._check_all_flat(signals))
        return anomalies

    def _check_zero_signal(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Check for strategies with 0 non-FLAT signals in the threshold window.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=ZERO_SIGNAL_THRESHOLD_HOURS)
        anomalies = []

        # Group signals by strategy
        strategy_signals: Dict[str, List[Dict]] = defaultdict(list)
        for sig in signals:
            ts_str = sig.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if ts >= cutoff:
                strategy_signals[sig.get("strategy_name", "unknown")].append(sig)

        # For each strategy that has signals in the window, check if all are FLAT
        for strategy_name, sigs in strategy_signals.items():
            non_flat = [s for s in sigs if s.get("intent") != "FLAT"]
            if len(sigs) > 0 and len(non_flat) == 0:
                # Calculate how long it's been since last non-FLAT
                last_non_flat = self._find_last_non_flat(signals, strategy_name)
                hours_silent = ZERO_SIGNAL_THRESHOLD_HOURS
                if last_non_flat:
                    try:
                        lnf_ts = datetime.fromisoformat(last_non_flat)
                        if lnf_ts.tzinfo is None:
                            lnf_ts = lnf_ts.replace(tzinfo=timezone.utc)
                        hours_silent = (now - lnf_ts).total_seconds() / 3600
                    except (ValueError, TypeError):
                        pass

                anomalies.append({
                    "timestamp": now.isoformat(),
                    "anomaly_type": "ZERO_SIGNAL",
                    "strategy_name": strategy_name,
                    "detail": f"0 non-FLAT signals in last {ZERO_SIGNAL_THRESHOLD_HOURS}h ({len(sigs)} total signals, all FLAT)",
                    "hours_silent": round(hours_silent, 1),
                    "total_signals_in_window": len(sigs),
                    "last_non_flat": last_non_flat,
                })

        return anomalies

    def _check_all_flat(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Check for strategies that have returned FLAT for >N consecutive cycles.
        """
        anomalies = []
        now = datetime.now(timezone.utc)

        # Group by strategy, check tail for consecutive FLATs
        strategy_signals: Dict[str, List[Dict]] = defaultdict(list)
        for sig in signals:
            strategy_signals[sig.get("strategy_name", "unknown")].append(sig)

        for strategy_name, sigs in strategy_signals.items():
            # Count consecutive FLAT from the end
            consecutive_flat = 0
            for sig in reversed(sigs):
                if sig.get("intent") == "FLAT":
                    consecutive_flat += 1
                else:
                    break

            if consecutive_flat >= ALL_FLAT_CYCLE_THRESHOLD:
                anomalies.append({
                    "timestamp": now.isoformat(),
                    "anomaly_type": "ALL_FLAT",
                    "strategy_name": strategy_name,
                    "detail": f"{consecutive_flat} consecutive FLAT signals (threshold: {ALL_FLAT_CYCLE_THRESHOLD})",
                    "consecutive_flat_count": consecutive_flat,
                })

        return anomalies

    @staticmethod
    def _find_last_non_flat(signals: List[Dict[str, Any]], strategy_name: str) -> str:
        """Find timestamp of last non-FLAT signal for a strategy."""
        for sig in reversed(signals):
            if sig.get("strategy_name") == strategy_name and sig.get("intent") != "FLAT":
                return sig.get("timestamp", "")
        return ""
