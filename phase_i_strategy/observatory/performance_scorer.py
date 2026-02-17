"""
Strategy Performance Scorer (Phase I-A).

Reads signal history + trade ledger, computes per-strategy rolling metrics:
- Win rate
- Average net PnL %
- Signal-to-trade ratio (how often signals convert to actual trades)
- Flat signal ratio (what fraction of signals are FLAT)
- Trade count
- Composite health score (0-100)
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from phase_i_strategy.config import PERFORMANCE_ROLLING_WINDOW_HOURS
from phase_i_strategy.persistence import PhaseIPersistence

logger = logging.getLogger(__name__)


class StrategyPerformanceScorer:
    """
    Computes per-strategy performance metrics from signal + trade history.

    Produces a snapshot dict per strategy with rolling-window metrics
    and a composite health score (0-100).
    """

    def __init__(self, persistence: PhaseIPersistence):
        self.persistence = persistence

    def score_all_strategies(self) -> Dict[str, Dict[str, Any]]:
        """
        Compute performance scores for all strategies found in signal history.

        Returns:
            Dict mapping strategy_name -> metrics dict with:
                win_rate, avg_net_pnl_pct, trade_count,
                signal_count, non_flat_signal_count, flat_ratio,
                signal_to_trade_ratio, health_score
        """
        signals = self.persistence.load_recent_signals(max_lines=10000)
        trades = self.persistence.load_trades_from_ledger()

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=PERFORMANCE_ROLLING_WINDOW_HOURS)

        # Filter signals to rolling window
        window_signals = self._filter_by_time(signals, cutoff, key="timestamp")

        # Filter trades to rolling window (use exit_timestamp)
        window_trades = self._filter_by_time(trades, cutoff, key="exit_timestamp")

        # Group by strategy
        signals_by_strategy = self._group_by_strategy(window_signals, key="strategy_name")
        trades_by_strategy = self._group_by_strategy(window_trades, key="strategy_name")

        # Get all strategy names from both sources
        all_strategies = set(signals_by_strategy.keys()) | set(trades_by_strategy.keys())

        results = {}
        for strategy_name in all_strategies:
            strat_signals = signals_by_strategy.get(strategy_name, [])
            strat_trades = trades_by_strategy.get(strategy_name, [])
            results[strategy_name] = self._compute_metrics(
                strategy_name, strat_signals, strat_trades
            )

        return results

    def _compute_metrics(
        self,
        strategy_name: str,
        signals: List[Dict],
        trades: List[Dict],
    ) -> Dict[str, Any]:
        """Compute metrics for a single strategy."""
        signal_count = len(signals)
        non_flat_count = sum(1 for s in signals if s.get("intent") != "FLAT")
        flat_count = signal_count - non_flat_count
        flat_ratio = flat_count / signal_count if signal_count > 0 else 1.0

        trade_count = len(trades)
        winners = [t for t in trades if (t.get("net_pnl") or 0) > 0]
        win_rate = len(winners) / trade_count if trade_count > 0 else 0.0

        pnl_values = [t.get("net_pnl_pct", 0.0) for t in trades]
        avg_net_pnl_pct = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

        # Signal-to-trade ratio: non-FLAT signals that became trades
        signal_to_trade_ratio = (
            trade_count / non_flat_count if non_flat_count > 0 else 0.0
        )

        # Composite health score (0-100)
        health_score = self._compute_health_score(
            win_rate=win_rate,
            avg_pnl_pct=avg_net_pnl_pct,
            flat_ratio=flat_ratio,
            trade_count=trade_count,
            signal_count=signal_count,
        )

        return {
            "strategy_name": strategy_name,
            "signal_count": signal_count,
            "non_flat_signal_count": non_flat_count,
            "flat_ratio": round(flat_ratio, 3),
            "trade_count": trade_count,
            "win_count": len(winners),
            "win_rate": round(win_rate, 3),
            "avg_net_pnl_pct": round(avg_net_pnl_pct, 3),
            "signal_to_trade_ratio": round(signal_to_trade_ratio, 3),
            "health_score": health_score,
        }

    @staticmethod
    def _compute_health_score(
        win_rate: float,
        avg_pnl_pct: float,
        flat_ratio: float,
        trade_count: int,
        signal_count: int,
    ) -> int:
        """
        Composite health score (0-100).

        Weights:
        - Win rate:          30 points (0% → 0, 50%+ → 30)
        - Avg PnL:           25 points (negative → 0, 2%+ → 25)
        - Activity:          25 points (all-FLAT → 0, generating signals → 25)
        - Trade volume:      20 points (0 trades → 0, 5+ trades → 20)
        """
        # Win rate component (0-30)
        win_score = min(30, int(win_rate * 60))

        # PnL component (0-25): 0 at 0%, 25 at 2%+
        if avg_pnl_pct <= 0:
            pnl_score = 0
        else:
            pnl_score = min(25, int(avg_pnl_pct * 12.5))

        # Activity component (0-25): penalize high flat ratio
        activity_score = int((1.0 - flat_ratio) * 25)

        # Trade volume component (0-20): ramp up to 5 trades
        volume_score = min(20, trade_count * 4)

        total = win_score + pnl_score + activity_score + volume_score
        return max(0, min(100, total))

    @staticmethod
    def _filter_by_time(
        records: List[Dict], cutoff: datetime, key: str
    ) -> List[Dict]:
        """Filter records to those with timestamp >= cutoff."""
        result = []
        for rec in records:
            ts_str = rec.get(key, "")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    result.append(rec)
            except (ValueError, TypeError):
                continue
        return result

    @staticmethod
    def _group_by_strategy(
        records: List[Dict], key: str = "strategy_name"
    ) -> Dict[str, List[Dict]]:
        """Group records by strategy name."""
        groups: Dict[str, List[Dict]] = defaultdict(list)
        for rec in records:
            name = rec.get(key, "unknown")
            if name:
                groups[name].append(rec)
        return groups
