"""Demo backtest using synthetic data (no network required)."""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List

from config.settings import (
    BACKTEST_LOOKBACK_YEARS,
    HOLD_DAYS,
    BACKTEST_MIN_CONFIDENCE,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
)
from universe.symbols import SYMBOLS
from backtest.simple_backtest import Trade
from backtest.metrics import print_metrics


# Setup logging
def _setup_logging():
    """Configure logging."""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    handler = logging.StreamHandler()
    handler.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handler.setFormatter(formatter)
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger


logger = _setup_logging()


def generate_demo_trades(n_trades: int = 300) -> List[Trade]:
    """
    Generate synthetic trades for demonstration.
    
    Args:
        n_trades: Number of demo trades to generate
        
    Returns:
        List of Trade objects with realistic returns
    """
    trades: List[Trade] = []
    base_date = datetime.now() - timedelta(days=365 * BACKTEST_LOOKBACK_YEARS)
    
    confidence_counts = {5: 50, 4: 100, 3: 100, 2: 30, 1: 20}
    confidence_returns = {
        5: {"mean": 0.025, "std": 0.015},    # Avg 2.5%, more consistent
        4: {"mean": 0.012, "std": 0.020},    # Avg 1.2%, moderate volatility
        3: {"mean": 0.003, "std": 0.025},    # Avg 0.3%, high volatility
        2: {"mean": -0.002, "std": 0.030},   # Avg -0.2%, high volatility
        1: {"mean": -0.008, "std": 0.035},   # Avg -0.8%, very inconsistent
    }
    
    symbol_idx = 0
    
    for conf in [5, 4, 3, 2, 1]:
        for _ in range(confidence_counts[conf]):
            symbol = SYMBOLS[symbol_idx % len(SYMBOLS)]
            symbol_idx += 1
            
            entry_date = base_date + timedelta(days=int(np.random.uniform(0, 365 * BACKTEST_LOOKBACK_YEARS)))
            
            # Generate return from confidence distribution
            ret_dist = confidence_returns[conf]
            return_pct = np.random.normal(ret_dist["mean"], ret_dist["std"])
            
            entry_price = 100.0
            exit_price = entry_price * (1 + return_pct)
            exit_date = entry_date + timedelta(days=HOLD_DAYS)
            
            trade = Trade(
                symbol=symbol,
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=exit_price,
                confidence=conf,
            )
            trades.append(trade)
    
    return trades


def main_demo():
    """Run demo backtest."""
    logger.info("=" * 90)
    logger.info(f"Demo Backtest - Synthetic Trades ({BACKTEST_LOOKBACK_YEARS}Y lookback)")
    logger.info("=" * 90)
    
    logger.info(f"\nGenerating synthetic trades...")
    trades = generate_demo_trades()
    
    logger.info(f"Generated {len(trades)} trades for {len(SYMBOLS)} symbols")
    
    print_metrics(trades)


if __name__ == '__main__':
    main_demo()
