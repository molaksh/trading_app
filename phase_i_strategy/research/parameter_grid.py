"""
ParameterGridSearch: Grid search over strategy parameter space.

For each parameter combination, runs a backtest and collects results.
Returns top N parameter sets ranked by Sharpe ratio.
"""

import itertools
import logging
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

import pandas as pd

from phase_i_strategy.config import (
    GRID_SEARCH_TOP_N,
    PARAMETER_SEARCH_SPACES,
    MAX_RESEARCH_CYCLE_SECONDS,
)
from phase_i_strategy.research.crypto_backtester import (
    BacktestResult,
    CryptoStrategyBacktester,
    clone_strategy_with_params,
)

logger = logging.getLogger(__name__)


@dataclass
class GridSearchResult:
    """Result of a full grid search for one strategy."""
    strategy_name: str
    symbol: str
    regime: str
    total_combinations: int
    completed_combinations: int
    top_results: List[Dict[str, Any]]  # Top N by Sharpe
    current_params: Dict[str, Any]
    current_result: Optional[Dict[str, Any]]  # Backtest with current params
    elapsed_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ParameterGridSearch:
    """
    Grid search over parameter combinations for a strategy.

    Uses CryptoStrategyBacktester for each parameter set.
    Returns top N results ranked by Sharpe ratio.
    """

    def __init__(
        self,
        strategy,
        symbol: str,
        bars_5m: pd.DataFrame,
        regime_state: str,
        search_space: Optional[Dict[str, List]] = None,
        top_n: int = GRID_SEARCH_TOP_N,
        timeout_seconds: float = MAX_RESEARCH_CYCLE_SECONDS,
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.bars_5m = bars_5m
        self.regime_state = regime_state
        self.top_n = top_n
        self.timeout_seconds = timeout_seconds

        # Use provided search space or fall back to defaults
        if search_space is not None:
            self.search_space = search_space
        else:
            self.search_space = PARAMETER_SEARCH_SPACES.get(strategy.name, {})

    def run(self) -> Optional[GridSearchResult]:
        """
        Run grid search over all parameter combinations.

        Returns GridSearchResult with top N parameter sets, or None if
        no search space is defined for this strategy.
        """
        if not self.search_space:
            logger.info(
                "GRID_SEARCH_NO_SPACE | strategy=%s",
                self.strategy.name,
            )
            return None

        start = time.monotonic()

        # Generate all parameter combinations
        param_names = list(self.search_space.keys())
        param_values = list(self.search_space.values())
        combinations = list(itertools.product(*param_values))
        total = len(combinations)

        logger.info(
            "GRID_SEARCH_START | strategy=%s symbol=%s combinations=%d",
            self.strategy.name, self.symbol, total,
        )

        # First, run backtest with current params as baseline
        current_params = {k: self.strategy.config.get(k) for k in param_names}
        current_result = self._run_single_backtest(current_params)

        # Run all combinations
        results: List[Dict[str, Any]] = []
        completed = 0

        for combo in combinations:
            # Timeout check
            elapsed = time.monotonic() - start
            if elapsed > self.timeout_seconds:
                logger.warning(
                    "GRID_SEARCH_TIMEOUT | strategy=%s completed=%d/%d elapsed=%.0fs",
                    self.strategy.name, completed, total, elapsed,
                )
                break

            overrides = dict(zip(param_names, combo))
            bt_result = self._run_single_backtest(overrides)
            completed += 1

            if bt_result is not None and bt_result.total_trades > 0:
                entry = {
                    "params": overrides,
                    "sharpe": bt_result.sharpe_ratio,
                    "win_rate": bt_result.win_rate,
                    "avg_pnl_pct": bt_result.avg_pnl_pct,
                    "total_pnl_pct": bt_result.total_pnl_pct,
                    "total_trades": bt_result.total_trades,
                    "max_drawdown_pct": bt_result.max_drawdown_pct,
                }
                results.append(entry)

        # Sort by Sharpe and take top N
        results.sort(key=lambda x: x["sharpe"], reverse=True)
        top_results = results[: self.top_n]

        elapsed = time.monotonic() - start
        logger.info(
            "GRID_SEARCH_DONE | strategy=%s completed=%d/%d top_sharpe=%.3f elapsed=%.1fs",
            self.strategy.name,
            completed,
            total,
            top_results[0]["sharpe"] if top_results else 0.0,
            elapsed,
        )

        return GridSearchResult(
            strategy_name=self.strategy.name,
            symbol=self.symbol,
            regime=self.regime_state,
            total_combinations=total,
            completed_combinations=completed,
            top_results=top_results,
            current_params=current_params,
            current_result=current_result.to_dict() if current_result else None,
            elapsed_seconds=elapsed,
        )

    def _run_single_backtest(self, param_overrides: Dict[str, Any]) -> Optional[BacktestResult]:
        """Run a single backtest with given parameter overrides."""
        try:
            cloned = clone_strategy_with_params(self.strategy, param_overrides)
            backtester = CryptoStrategyBacktester(
                symbol=self.symbol,
                bars_5m=self.bars_5m,
                strategy=cloned,
                regime_state=self.regime_state,
            )
            result = backtester.run()
            if result is not None:
                result.param_overrides = param_overrides
            return result
        except Exception as e:
            logger.warning(
                "GRID_SEARCH_BACKTEST_FAILED | strategy=%s params=%s error=%s",
                self.strategy.name, param_overrides, e,
            )
            return None
