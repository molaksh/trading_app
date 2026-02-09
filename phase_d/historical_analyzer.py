"""
Historical analyzer: Computes regime block statistics.
"""

import logging
import statistics
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass

from phase_d.persistence import PhaseDPersistence
from config.phase_d_settings import HISTORICAL_LOOKBACK_DAYS, HISTORICAL_MIN_BLOCKS

logger = logging.getLogger(__name__)


@dataclass
class BlockStatistics:
    """Statistics for regime blocks."""
    regime: str
    lookback_days: int
    count: int
    median_duration_seconds: Optional[int] = None
    p90_duration_seconds: Optional[int] = None
    p10_duration_seconds: Optional[int] = None
    min_duration_seconds: Optional[int] = None
    max_duration_seconds: Optional[int] = None


class HistoricalAnalyzer:
    """Analyzes historical block statistics."""

    def __init__(self, persistence: Optional[PhaseDPersistence] = None):
        self.persistence = persistence or PhaseDPersistence()

    def get_regime_block_stats(
        self,
        scope: str,
        regime: str,
        lookback_days: int = HISTORICAL_LOOKBACK_DAYS
    ) -> Optional[BlockStatistics]:
        """
        Compute statistics for regime blocks in the lookback period.

        Args:
            scope: Scope name
            regime: Regime name (e.g., "BTC_UNSUITABLE")
            lookback_days: How far back to look

        Returns:
            BlockStatistics or None if insufficient data
        """
        try:
            blocks = self.persistence.read_block_events(scope)
            if not blocks:
                return None

            # Filter to completed blocks in lookback period
            cutoff_ts = datetime.utcnow() - timedelta(days=lookback_days)
            completed = [
                b for b in blocks
                if b.block_end_ts
                and b.block_end_ts > cutoff_ts
                and b.regime == regime
                and b.event_type == "BLOCK_END"
            ]

            if len(completed) < HISTORICAL_MIN_BLOCKS:
                return None

            durations = [b.duration_seconds for b in completed if b.duration_seconds]
            if not durations:
                return None

            sorted_durations = sorted(durations)

            return BlockStatistics(
                regime=regime,
                lookback_days=lookback_days,
                count=len(completed),
                median_duration_seconds=int(statistics.median(sorted_durations)),
                p90_duration_seconds=int(self._percentile(sorted_durations, 90)),
                p10_duration_seconds=int(self._percentile(sorted_durations, 10)),
                min_duration_seconds=min(sorted_durations),
                max_duration_seconds=max(sorted_durations),
            )

        except Exception as e:
            logger.error(f"PHASE_D_HISTORICAL_ANALYSIS_FAILED | scope={scope} regime={regime} error={e}")
            return None

    @staticmethod
    def _percentile(data: List[int], percentile: int) -> float:
        """Compute percentile of a list."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        rank = (percentile / 100.0) * (len(sorted_data) - 1)
        lower = int(rank)
        upper = lower + 1

        if upper >= len(sorted_data):
            return float(sorted_data[-1])
        if lower == upper:
            return float(sorted_data[lower])

        return sorted_data[lower] + (rank - lower) * (sorted_data[upper] - sorted_data[lower])
