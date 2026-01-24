"""Simple diagnostic backtest for screener validation."""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import pandas as pd
import numpy as np

from config.settings import (
    BACKTEST_LOOKBACK_YEARS,
    HOLD_DAYS,
    BACKTEST_MIN_CONFIDENCE,
    LOOKBACK_DAYS,
)
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol


logger = logging.getLogger(__name__)


class Trade:
    """Represents a single trade: entry, exit, return."""

    def __init__(
        self,
        symbol: str,
        entry_date: pd.Timestamp,
        entry_price: float,
        exit_date: pd.Timestamp,
        exit_price: float,
        confidence: int,
    ):
        """
        Initialize Trade.

        Args:
            symbol: Stock ticker
            entry_date: Date entered position
            entry_price: Price at entry
            exit_date: Date exited position
            exit_price: Price at exit
            confidence: Confidence score when entered
        """
        self.symbol = symbol
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.exit_date = exit_date
        self.exit_price = exit_price
        self.confidence = confidence
        self.return_pct = (exit_price - entry_price) / entry_price

    def __repr__(self) -> str:
        return (
            f"Trade({self.symbol}, {self.entry_date.date()}, "
            f"conf={self.confidence}, ret={self.return_pct:.2%})"
        )


def run_backtest(symbols: List[str]) -> List[Trade]:
    """
    Run historical backtest on symbols.

    For each symbol and each historical date:
    - Load data up to that date
    - Compute features
    - Score confidence
    - If score >= BACKTEST_MIN_CONFIDENCE: simulate trade

    Args:
        symbols: List of stock tickers

    Returns:
        List of Trade objects
    """
    logger.info("=" * 90)
    logger.info(f"Running backtest ({BACKTEST_LOOKBACK_YEARS}Y, hold {HOLD_DAYS}D, conf >= {BACKTEST_MIN_CONFIDENCE})")
    logger.info("=" * 90)

    trades: List[Trade] = []

    # Calculate start date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * BACKTEST_LOOKBACK_YEARS)

    logger.info(f"\nBacktest period: {start_date.date()} to {end_date.date()}")
    logger.info(f"Testing {len(symbols)} symbols...")

    for i, symbol in enumerate(symbols):
        logger.debug(f"[{i+1}/{len(symbols)}] {symbol}")

        try:
            # Load full history for the symbol
            full_df = load_price_data(symbol, lookback_days=LOOKBACK_DAYS + 365 * BACKTEST_LOOKBACK_YEARS)
            if full_df is None or len(full_df) == 0:
                logger.debug(f"{symbol}: No data available")
                continue

            # Generate list of trade dates within backtest period
            trade_dates = [d for d in full_df.index if start_date <= d <= end_date]

            if not trade_dates:
                logger.debug(f"{symbol}: No dates in backtest period")
                continue

            # Track open positions
            open_positions: Dict = {}  # symbol -> {'entry_date': date, 'entry_price': price, 'confidence': conf}

            # Walk through each date
            for trade_date in trade_dates:
                # Get data up to and including this date (no lookahead bias)
                data_up_to_date = full_df.loc[:trade_date].copy()

                if len(data_up_to_date) < LOOKBACK_DAYS:
                    continue

                # Compute features
                features_df = compute_features(data_up_to_date)
                if features_df is None or len(features_df) == 0:
                    continue

                latest_row = features_df.iloc[-1].copy()

                if latest_row.isna().any():
                    continue

                # Score
                confidence = score_symbol(latest_row)
                if confidence is None:
                    continue

                # Check for exit: if position open and hold period expired
                if symbol in open_positions:
                    entry_date = open_positions[symbol]["entry_date"]
                    exit_check_date = entry_date + timedelta(days=HOLD_DAYS)

                    if trade_date >= exit_check_date:
                        # Exit position: use open price if available, else close
                        exit_price = full_df.loc[trade_date, "Open"] if "Open" in full_df.columns else full_df.loc[trade_date, "Close"]

                        trade = Trade(
                            symbol=symbol,
                            entry_date=open_positions[symbol]["entry_date"],
                            entry_price=open_positions[symbol]["entry_price"],
                            exit_date=trade_date,
                            exit_price=exit_price,
                            confidence=open_positions[symbol]["confidence"],
                        )
                        trades.append(trade)
                        del open_positions[symbol]

                # Check for entry: if no open position and score >= MIN_CONFIDENCE
                if symbol not in open_positions and confidence >= BACKTEST_MIN_CONFIDENCE:
                    # Get next day's open price if available, else use close
                    trade_dates_list = list(full_df.index)
                    current_idx = trade_dates_list.index(trade_date)

                    if current_idx + 1 < len(trade_dates_list):
                        next_date = trade_dates_list[current_idx + 1]
                        entry_price = (
                            full_df.loc[next_date, "Open"]
                            if "Open" in full_df.columns
                            else full_df.loc[next_date, "Close"]
                        )
                    else:
                        # No next date, use current close
                        entry_price = full_df.loc[trade_date, "Close"]

                    open_positions[symbol] = {
                        "entry_date": trade_date,
                        "entry_price": entry_price,
                        "confidence": confidence,
                    }

        except Exception as e:
            logger.debug(f"{symbol}: {type(e).__name__}: {e}")
            continue

    logger.info(f"\nBacktest complete: {len(trades)} trades generated")

    return trades
