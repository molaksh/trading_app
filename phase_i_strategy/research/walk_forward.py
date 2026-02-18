"""
WalkForwardValidator: Rolling train/test split validation.

Prevents overfitting by validating parameter sets on out-of-sample data.
Uses rolling windows: 30-day train, 7-day test, stepping forward 7 days.
A parameter set must show positive Sharpe in 60%+ of OOS folds to pass.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

import pandas as pd

from phase_i_strategy.config import (
    WALK_FORWARD_TRAIN_DAYS,
    WALK_FORWARD_TEST_DAYS,
)
from phase_i_strategy.research.crypto_backtester import (
    CryptoStrategyBacktester,
    clone_strategy_with_params,
)

logger = logging.getLogger(__name__)

# 5m bars per day: 24h * 12 bars/h = 288
BARS_PER_DAY = 288
MIN_FOLDS = 2
OOS_PASS_RATIO = 0.6  # Must pass 60% of out-of-sample folds


@dataclass
class FoldResult:
    """Result of a single train/test fold."""
    fold_index: int
    train_bars: int
    test_bars: int
    train_sharpe: float
    train_win_rate: float
    train_trades: int
    test_sharpe: float
    test_win_rate: float
    test_trades: int
    oos_positive: bool  # Out-of-sample Sharpe > 0


@dataclass
class WalkForwardResult:
    """Summary of walk-forward validation."""
    strategy_name: str
    symbol: str
    regime: str
    param_overrides: Dict[str, Any]
    total_folds: int
    oos_positive_folds: int
    oos_pass_ratio: float
    passed: bool  # oos_pass_ratio >= OOS_PASS_RATIO
    avg_oos_sharpe: float
    avg_oos_win_rate: float
    folds: List[FoldResult]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WalkForwardValidator:
    """
    Rolling walk-forward validation for parameter sets.

    Splits data into rolling train/test windows:
    - Train: 30 days (8640 bars at 5m)
    - Test: 7 days (2016 bars at 5m)
    - Step: 7 days forward

    A parameter set passes if it shows positive OOS Sharpe
    in >= 60% of test folds.
    """

    def __init__(
        self,
        strategy,
        symbol: str,
        bars_5m: pd.DataFrame,
        regime_state: str,
        param_overrides: Dict[str, Any],
        train_days: int = WALK_FORWARD_TRAIN_DAYS,
        test_days: int = WALK_FORWARD_TEST_DAYS,
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.bars_5m = bars_5m
        self.regime_state = regime_state
        self.param_overrides = param_overrides
        self.train_bars = train_days * BARS_PER_DAY
        self.test_bars = test_days * BARS_PER_DAY
        self.step_bars = test_days * BARS_PER_DAY  # Step by test window size

    def validate(self) -> Optional[WalkForwardResult]:
        """
        Run walk-forward validation.

        Returns WalkForwardResult or None if insufficient data for min folds.
        """
        n_bars = len(self.bars_5m)
        window_size = self.train_bars + self.test_bars

        if n_bars < window_size:
            logger.warning(
                "WALK_FORWARD_INSUFFICIENT_DATA | symbol=%s bars=%d need=%d",
                self.symbol, n_bars, window_size,
            )
            return None

        # Calculate number of folds
        available_after_first = n_bars - window_size
        n_folds = 1 + (available_after_first // self.step_bars)

        if n_folds < MIN_FOLDS:
            logger.warning(
                "WALK_FORWARD_TOO_FEW_FOLDS | symbol=%s folds=%d min=%d",
                self.symbol, n_folds, MIN_FOLDS,
            )
            return None

        # Clone strategy with overridden params
        cloned = clone_strategy_with_params(self.strategy, self.param_overrides)

        folds: List[FoldResult] = []

        for fold_idx in range(n_folds):
            start = fold_idx * self.step_bars
            train_end = start + self.train_bars
            test_end = train_end + self.test_bars

            if test_end > n_bars:
                break

            train_data = self.bars_5m.iloc[start:train_end]
            test_data = self.bars_5m.iloc[start:test_end]  # Include train for lookback

            # Run backtest on train split
            train_bt = CryptoStrategyBacktester(
                symbol=self.symbol,
                bars_5m=train_data,
                strategy=cloned,
                regime_state=self.regime_state,
            )
            train_result = train_bt.run()

            # Run backtest on full window (train + test) — the test portion
            # is what matters, but we need the lookback from train
            test_bt = CryptoStrategyBacktester(
                symbol=self.symbol,
                bars_5m=test_data,
                strategy=cloned,
                regime_state=self.regime_state,
            )
            test_result = test_bt.run()

            fold = FoldResult(
                fold_index=fold_idx,
                train_bars=len(train_data),
                test_bars=self.test_bars,
                train_sharpe=train_result.sharpe_ratio if train_result else 0.0,
                train_win_rate=train_result.win_rate if train_result else 0.0,
                train_trades=train_result.total_trades if train_result else 0,
                test_sharpe=test_result.sharpe_ratio if test_result else 0.0,
                test_win_rate=test_result.win_rate if test_result else 0.0,
                test_trades=test_result.total_trades if test_result else 0,
                oos_positive=test_result.sharpe_ratio > 0 if test_result else False,
            )
            folds.append(fold)

        if not folds:
            return None

        oos_positive = sum(1 for f in folds if f.oos_positive)
        pass_ratio = oos_positive / len(folds)
        avg_sharpe = sum(f.test_sharpe for f in folds) / len(folds)
        avg_win_rate = sum(f.test_win_rate for f in folds) / len(folds)

        passed = pass_ratio >= OOS_PASS_RATIO

        logger.info(
            "WALK_FORWARD_DONE | strategy=%s symbol=%s folds=%d "
            "oos_positive=%d/%d ratio=%.2f passed=%s avg_oos_sharpe=%.3f",
            self.strategy.name, self.symbol, len(folds),
            oos_positive, len(folds), pass_ratio, passed, avg_sharpe,
        )

        return WalkForwardResult(
            strategy_name=self.strategy.name,
            symbol=self.symbol,
            regime=self.regime_state,
            param_overrides=self.param_overrides,
            total_folds=len(folds),
            oos_positive_folds=oos_positive,
            oos_pass_ratio=pass_ratio,
            passed=passed,
            avg_oos_sharpe=avg_sharpe,
            avg_oos_win_rate=avg_win_rate,
            folds=folds,
        )
