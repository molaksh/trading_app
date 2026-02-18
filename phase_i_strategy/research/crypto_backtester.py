"""
CryptoStrategyBacktester: Replay historical 5m candles through a strategy.

Reuses build_execution_features() for feature computation to ensure
backtest/live fidelity. Slides a window through historical data, generates
signals, and tracks simulated entries/exits/P&L.
"""

import logging
import math
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional

import pandas as pd

from crypto.features.execution_features import build_execution_features
from phase_i_strategy.config import BACKTEST_BUDGET, BACKTEST_MAX_HOLD_BARS, BACKTEST_MIN_CANDLES

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """A single simulated trade."""
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: str  # "LONG" or "SHORT"
    pnl_pct: float
    hold_bars: int
    exit_reason: str  # "signal", "max_hold", "end_of_data"


@dataclass
class BacktestResult:
    """Summary metrics from a backtest run."""
    strategy_name: str
    symbol: str
    regime: str
    param_overrides: Dict[str, Any]
    total_bars: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_pnl_pct: float
    total_pnl_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    trades: List[BacktestTrade] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["trades"] = [asdict(t) for t in self.trades]
        return d


def clone_strategy_with_params(strategy, param_overrides: Dict[str, Any]):
    """
    Clone a strategy instance with overridden config parameters.

    Creates a new instance of the same class, then overrides specific
    config keys. Does NOT modify the original strategy.
    """
    cloned = strategy.__class__()
    for key, value in param_overrides.items():
        if key in cloned.config:
            cloned.config[key] = value
        else:
            logger.warning(
                "BACKTEST_UNKNOWN_PARAM | strategy=%s param=%s",
                cloned.name, key,
            )
    return cloned


class CryptoStrategyBacktester:
    """
    Replay historical 5m candles through a strategy, track simulated P&L.

    Usage:
        backtester = CryptoStrategyBacktester(
            symbol="BTC/USD",
            bars_5m=df,
            strategy=mean_reversion_strategy,
            regime_state="neutral",
        )
        result = backtester.run()
    """

    def __init__(
        self,
        symbol: str,
        bars_5m: pd.DataFrame,
        strategy,
        regime_state: str,
        budget: float = BACKTEST_BUDGET,
        max_hold_bars: int = BACKTEST_MAX_HOLD_BARS,
        lookback: int = 200,
    ):
        self.symbol = symbol
        self.bars_5m = bars_5m
        self.strategy = strategy
        self.regime_state = regime_state
        self.budget = budget
        self.max_hold_bars = max_hold_bars
        self.lookback = lookback

    def run(self) -> Optional[BacktestResult]:
        """
        Run the backtest over all available bars.

        Returns BacktestResult or None if insufficient data.
        """
        n_bars = len(self.bars_5m)
        if n_bars < BACKTEST_MIN_CANDLES:
            logger.warning(
                "BACKTEST_INSUFFICIENT_DATA | symbol=%s bars=%d min=%d",
                self.symbol, n_bars, BACKTEST_MIN_CANDLES,
            )
            return None

        trades: List[BacktestTrade] = []
        position: Optional[Dict[str, Any]] = None  # {direction, entry_price, entry_bar}

        # Slide window: start after lookback period
        for i in range(self.lookback, n_bars):
            window = self.bars_5m.iloc[max(0, i - self.lookback) : i + 1]

            # Build features using the same function as live trading
            try:
                ctx = build_execution_features(self.symbol, window, lookback_periods=self.lookback)
                feature_dict = asdict(ctx)
            except Exception:
                continue

            # Generate signal
            try:
                signal = self.strategy.generate_signal(
                    feature_context=feature_dict,
                    portfolio_state={},
                    budget=self.budget,
                    regime_state=self.regime_state,
                )
            except Exception:
                continue

            current_price = feature_dict.get("close", 0)
            if current_price <= 0:
                continue

            # Position management
            if position is not None:
                hold_bars = i - position["entry_bar"]
                should_exit = False
                exit_reason = ""

                # Exit on opposing or flat signal
                if position["direction"] == "LONG" and signal.intent in ("SHORT", "FLAT"):
                    should_exit = True
                    exit_reason = "signal"
                elif position["direction"] == "SHORT" and signal.intent in ("LONG", "FLAT"):
                    should_exit = True
                    exit_reason = "signal"
                # Exit on max hold
                elif hold_bars >= self.max_hold_bars:
                    should_exit = True
                    exit_reason = "max_hold"

                if should_exit:
                    pnl_pct = self._calc_pnl(position, current_price)
                    trades.append(BacktestTrade(
                        entry_bar=position["entry_bar"],
                        exit_bar=i,
                        entry_price=position["entry_price"],
                        exit_price=current_price,
                        direction=position["direction"],
                        pnl_pct=pnl_pct,
                        hold_bars=hold_bars,
                        exit_reason=exit_reason,
                    ))
                    position = None

            # Enter new position (only if flat)
            if position is None and signal.intent in ("LONG", "SHORT"):
                position = {
                    "direction": signal.intent,
                    "entry_price": current_price,
                    "entry_bar": i,
                }

        # Close any remaining position at end of data
        if position is not None:
            last_price = self.bars_5m.iloc[-1]["Close"]
            hold_bars = n_bars - 1 - position["entry_bar"]
            pnl_pct = self._calc_pnl(position, last_price)
            trades.append(BacktestTrade(
                entry_bar=position["entry_bar"],
                exit_bar=n_bars - 1,
                entry_price=position["entry_price"],
                exit_price=last_price,
                direction=position["direction"],
                pnl_pct=pnl_pct,
                hold_bars=hold_bars,
                exit_reason="end_of_data",
            ))

        return self._build_result(trades, n_bars - self.lookback)

    def _calc_pnl(self, position: Dict[str, Any], exit_price: float) -> float:
        """Calculate PnL percentage for a trade."""
        entry = position["entry_price"]
        if entry <= 0:
            return 0.0
        if position["direction"] == "LONG":
            return (exit_price - entry) / entry * 100
        else:  # SHORT
            return (entry - exit_price) / entry * 100

    def _build_result(self, trades: List[BacktestTrade], test_bars: int) -> BacktestResult:
        """Build BacktestResult from list of trades."""
        total = len(trades)
        if total == 0:
            return BacktestResult(
                strategy_name=self.strategy.name,
                symbol=self.symbol,
                regime=self.regime_state,
                param_overrides={},
                total_bars=test_bars,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                avg_pnl_pct=0.0,
                total_pnl_pct=0.0,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                trades=[],
            )

        pnls = [t.pnl_pct for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        avg_pnl = sum(pnls) / total
        total_pnl = sum(pnls)

        # Sharpe ratio (annualized from 5m bars)
        sharpe = self._calc_sharpe(pnls)

        # Max drawdown from cumulative PnL curve
        max_dd = self._calc_max_drawdown(pnls)

        return BacktestResult(
            strategy_name=self.strategy.name,
            symbol=self.symbol,
            regime=self.regime_state,
            param_overrides={},
            total_bars=test_bars,
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=len(winners) / total if total > 0 else 0.0,
            avg_pnl_pct=avg_pnl,
            total_pnl_pct=total_pnl,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            trades=trades,
        )

    @staticmethod
    def _calc_sharpe(pnls: List[float]) -> float:
        """Calculate Sharpe ratio from trade PnL percentages."""
        if len(pnls) < 2:
            return 0.0
        mean = sum(pnls) / len(pnls)
        variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std == 0:
            return 0.0
        # Annualize: assume ~100 trades/year for crypto
        return (mean / std) * math.sqrt(min(len(pnls), 100))

    @staticmethod
    def _calc_max_drawdown(pnls: List[float]) -> float:
        """Calculate max drawdown from cumulative PnL curve."""
        if not pnls:
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        return max_dd
