"""
Analyze historical data to provide context for regime durations and conditions.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, List

from ops_agent.summary_reader import SummaryReader

logger = logging.getLogger(__name__)


class HistoricalAnalyzer:
    """Provide historical context for expectation framing."""

    def __init__(self, logs_root: str):
        """
        Initialize historical analyzer.

        Args:
            logs_root: Root directory for observability logs
        """
        self.logs_root = logs_root
        self.summary_reader = SummaryReader(logs_root)

    def get_regime_statistics(
        self, scope: str, lookback_days: int = 30
    ) -> Dict[str, Dict]:
        """
        Calculate regime duration statistics from historical data.

        Args:
            scope: Scope name
            lookback_days: How many days to look back

        Returns:
            {regime: {median_hours, occurrences}}
        """
        summaries = self.summary_reader.get_summaries(scope, lookback_days=lookback_days)

        if not summaries:
            return {}

        # Group regimes
        regime_counts: Dict[str, int] = {}
        for summary in summaries:
            regime = summary.regime
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        # Estimate duration (1 daily entry = ~24 hours)
        stats = {}
        for regime, count in regime_counts.items():
            stats[regime] = {
                "median_hours": 24,  # Each day counts as 24h
                "occurrences": count,
                "days_observed": count,
            }

        logger.debug(f"Regime statistics for {scope}: {stats}")

        return stats

    def frame_expectation(
        self, scope: str, regime: str, duration_hours: float
    ) -> Optional[str]:
        """
        Add historical context to regime duration.

        Args:
            scope: Scope name
            regime: Current regime
            duration_hours: Current regime duration in hours

        Returns:
            Historical framing string, or None if no historical data
        """
        stats = self.get_regime_statistics(scope)

        if regime not in stats:
            return None

        median = stats[regime].get("median_hours", 24)
        occurrences = stats[regime].get("occurrences", 0)

        if occurrences < 2:
            return None  # Not enough data

        if duration_hours > median * 2:
            return f"(unusual: typical {regime} ~{int(median)}h)"
        elif duration_hours > median:
            return f"(extended: typical {regime} ~{int(median)}h)"
        else:
            return f"(typical: median {regime} ~{int(median)}h)"

    def has_happened_before(
        self, scope: str, condition: str, lookback_days: int = 90
    ) -> bool:
        """
        Check if a condition has occurred historically.

        Args:
            scope: Scope name
            condition: Condition to check (no_trades, panic_regime, etc.)
            lookback_days: How far back to look

        Returns:
            True if condition has occurred, False otherwise
        """
        summaries = self.summary_reader.get_summaries(scope, lookback_days=lookback_days)

        if not summaries:
            return False

        if condition == "no_trades":
            return any(s.trades_executed == 0 for s in summaries)
        elif condition == "panic_regime":
            return any(s.regime == "PANIC" for s in summaries)
        elif condition == "risk_off_regime":
            return any(s.regime == "RISK_OFF" for s in summaries)
        elif condition == "data_issues":
            return any(s.data_issues > 0 for s in summaries)
        elif condition == "high_drawdown":
            return any(s.max_drawdown < -0.05 for s in summaries)  # > 5% drawdown

        return False

    def get_typical_pattern(self, scope: str, regime: str) -> Optional[str]:
        """
        Get typical pattern for a regime.

        Args:
            scope: Scope name
            regime: Regime name

        Returns:
            Description of typical pattern, or None
        """
        stats = self.get_regime_statistics(scope)

        if regime not in stats:
            return None

        occurrences = stats[regime].get("occurrences", 0)

        if occurrences == 0:
            return None
        elif occurrences < 3:
            return f"rare ({occurrences} occurrences in 30 days)"
        elif occurrences < 7:
            return f"uncommon ({occurrences} occurrences in 30 days)"
        else:
            return f"common ({occurrences} occurrences in 30 days)"

    def get_regime_transitions(self, scope: str) -> Dict[str, int]:
        """
        Get transition counts between regimes.

        Args:
            scope: Scope name

        Returns:
            {prev_regime->next_regime: count}
        """
        summaries = self.summary_reader.get_summaries(scope, lookback_days=30)

        if not summaries:
            return {}

        # Summaries are newest first, reverse to get chronological order
        summaries_chrono = list(reversed(summaries))

        transitions: Dict[str, int] = {}
        for i in range(len(summaries_chrono) - 1):
            prev = summaries_chrono[i].regime
            next_regime = summaries_chrono[i + 1].regime

            if prev != next_regime:
                key = f"{prev}->{next_regime}"
                transitions[key] = transitions.get(key, 0) + 1

        return transitions

    def is_common_transition(self, scope: str, from_regime: str, to_regime: str) -> bool:
        """
        Check if a transition is common.

        Args:
            scope: Scope name
            from_regime: Source regime
            to_regime: Target regime

        Returns:
            True if transition has occurred at least twice
        """
        transitions = self.get_regime_transitions(scope)
        key = f"{from_regime}->{to_regime}"
        return transitions.get(key, 0) >= 2
