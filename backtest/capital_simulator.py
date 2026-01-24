"""Capital simulation with confidence-based position sizing."""

import logging
from typing import List, Dict, Tuple

import pandas as pd
import numpy as np

from config.settings import (
    STARTING_CAPITAL,
    BASE_RISK_PCT,
    CONFIDENCE_RISK_MAP,
)
from backtest.simple_backtest import Trade


logger = logging.getLogger(__name__)


class CapitalSimulator:
    """Simulates portfolio capital growth from backtest trades."""

    def __init__(self, starting_capital: float = STARTING_CAPITAL):
        """
        Initialize capital simulator.

        Args:
            starting_capital: Starting account equity
        """
        self.starting_capital = starting_capital
        self.equity = starting_capital
        self.peak_equity = starting_capital
        self.equity_curve = [starting_capital]
        self.dates = []
        self.trades_executed = 0
        self.winning_trades = 0
        self.total_pnl = 0

    def _calculate_position_size(self, entry_price: float, confidence: int) -> float:
        """
        Calculate position size based on confidence level.

        Position size = (account_equity * BASE_RISK_PCT * confidence_multiplier) / entry_price

        Args:
            entry_price: Entry price of the trade
            confidence: Confidence level (1-5)

        Returns:
            Position size in units
        """
        confidence_multiplier = CONFIDENCE_RISK_MAP.get(confidence, CONFIDENCE_RISK_MAP[3])
        risk_capital = self.equity * BASE_RISK_PCT * confidence_multiplier

        position_size = risk_capital / entry_price

        return position_size

    def execute_trade(self, trade: Trade) -> Tuple[float, float]:
        """
        Execute a single trade and update equity.

        Args:
            trade: Trade object with entry/exit prices

        Returns:
            Tuple of (position_size, pnl)
        """
        position_size = self._calculate_position_size(trade.entry_price, trade.confidence)
        pnl = position_size * (trade.exit_price - trade.entry_price)

        self.equity += pnl
        self.total_pnl += pnl
        self.trades_executed += 1

        if pnl > 0:
            self.winning_trades += 1

        # Track peak for drawdown calculation
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        self.equity_curve.append(self.equity)
        self.dates.append(trade.exit_date)

        return position_size, pnl

    def simulate(self, trades: List[Trade]) -> None:
        """
        Simulate portfolio growth from trades.

        Args:
            trades: List of Trade objects sorted chronologically
        """
        # Sort trades by exit date to maintain chronological order
        sorted_trades = sorted(trades, key=lambda t: t.exit_date)

        for trade in sorted_trades:
            self.execute_trade(trade)

    def get_equity_curve(self) -> pd.DataFrame:
        """
        Get equity curve as DataFrame.

        Returns:
            DataFrame with date and equity columns
        """
        if not self.dates:
            return pd.DataFrame({"date": [], "equity": []})

        df = pd.DataFrame({
            "date": self.dates,
            "equity": self.equity_curve[1:],  # Skip initial capital
        })

        return df

    def get_metrics(self) -> Dict[str, float]:
        """
        Calculate portfolio metrics.

        Returns:
            Dictionary with metrics
        """
        if len(self.equity_curve) < 2:
            return {
                "final_equity": self.starting_capital,
                "total_pnl": 0,
                "total_return": 0,
                "win_rate": 0,
                "max_drawdown": 0,
                "max_drawdown_pct": 0,
            }

        # Final equity and returns
        final_equity = self.equity_curve[-1]
        total_return = (final_equity - self.starting_capital) / self.starting_capital

        # Win rate
        win_rate = (
            self.winning_trades / self.trades_executed
            if self.trades_executed > 0
            else 0
        )

        # Maximum drawdown
        peak = self.starting_capital
        max_drawdown = 0
        max_drawdown_pct = 0

        for equity in self.equity_curve:
            if equity > peak:
                peak = equity

            drawdown = peak - equity
            drawdown_pct = drawdown / peak if peak > 0 else 0

            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct

        return {
            "final_equity": final_equity,
            "total_pnl": self.total_pnl,
            "total_return": total_return,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
        }


def simulate_capital_growth(trades: List[Trade]) -> Tuple[Dict, pd.DataFrame]:
    """
    Simulate capital growth from backtest trades.

    Args:
        trades: List of Trade objects

    Returns:
        Tuple of (metrics dict, equity curve DataFrame)
    """
    simulator = CapitalSimulator(STARTING_CAPITAL)
    simulator.simulate(trades)

    metrics = simulator.get_metrics()
    equity_curve = simulator.get_equity_curve()

    return metrics, equity_curve
