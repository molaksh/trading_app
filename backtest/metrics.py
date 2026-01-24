"""Calculate backtest metrics grouped by confidence level."""

import logging
from typing import List

import pandas as pd
import numpy as np

from backtest.simple_backtest import Trade


logger = logging.getLogger(__name__)


def calculate_metrics(trades: List[Trade]) -> pd.DataFrame:
    """
    Calculate backtest metrics grouped by confidence level.

    For each confidence level (5, 4, 3, 2, 1):
    - Trade count
    - Win rate (% profitable)
    - Average return
    - Median return
    - Max drawdown

    Args:
        trades: List of Trade objects

    Returns:
        DataFrame with metrics by confidence level
    """
    if not trades:
        logger.warning("No trades to analyze")
        return pd.DataFrame()

    # Convert to DataFrame for easy grouping
    trade_data = []
    for trade in trades:
        trade_data.append({
            "confidence": trade.confidence,
            "return": trade.return_pct,
            "symbol": trade.symbol,
            "entry_date": trade.entry_date,
            "exit_date": trade.exit_date,
        })

    df = pd.DataFrame(trade_data)

    # Group by confidence
    results = []

    for conf in sorted(df["confidence"].unique(), reverse=True):
        conf_trades = df[df["confidence"] == conf]

        if len(conf_trades) == 0:
            continue

        returns = conf_trades["return"].values
        win_count = (returns > 0).sum()
        win_rate = win_count / len(returns)

        avg_return = returns.mean()
        median_return = np.median(returns)
        max_loss = returns.min()

        results.append({
            "Confidence": int(conf),
            "Trades": len(conf_trades),
            "WinRate": win_rate,
            "AvgReturn": avg_return,
            "MedianReturn": median_return,
            "MaxLoss": max_loss,
        })

    results_df = pd.DataFrame(results)

    return results_df


def print_metrics(trades: List[Trade]) -> None:
    """
    Print backtest metrics in clean table format.

    Args:
        trades: List of Trade objects
    """
    metrics_df = calculate_metrics(trades)

    if metrics_df.empty:
        logger.warning("No metrics to display")
        return

    logger.info("")
    logger.info("=" * 100)
    logger.info("BACKTEST RESULTS BY CONFIDENCE LEVEL")
    logger.info("=" * 100)
    logger.info("")

    # Format and print
    header = f"{'Conf':<6} {'Trades':<8} {'WinRate':<10} {'AvgReturn':<12} {'MedianRet':<12} {'MaxLoss':<12}"
    logger.info(header)
    logger.info("-" * 100)

    for _, row in metrics_df.iterrows():
        conf = int(row["Confidence"])
        trades_count = int(row["Trades"])
        win_rate = row["WinRate"]
        avg_return = row["AvgReturn"]
        median_return = row["MedianReturn"]
        max_loss = row["MaxLoss"]

        logger.info(
            f"{conf:<6} {trades_count:<8} {win_rate:>9.1%} "
            f"{avg_return:>11.2%} {median_return:>11.2%} {max_loss:>11.2%}"
        )

    logger.info("")
    logger.info(f"Total trades: {len(trades)}")
    logger.info(f"Confidence groups: {len(metrics_df)}")
    logger.info("=" * 100)


def print_capital_metrics(metrics: dict) -> None:
    """
    Print capital simulation metrics.

    Args:
        metrics: Dictionary with capital metrics from CapitalSimulator
    """
    logger.info("")
    logger.info("=" * 100)
    logger.info("CAPITAL SIMULATION RESULTS")
    logger.info("=" * 100)
    logger.info("")

    from config.settings import STARTING_CAPITAL

    starting_capital = STARTING_CAPITAL
    final_equity = metrics["final_equity"]
    total_pnl = metrics["total_pnl"]
    total_return = metrics["total_return"]
    win_rate = metrics["win_rate"]
    max_drawdown = metrics["max_drawdown"]
    max_drawdown_pct = metrics["max_drawdown_pct"]

    logger.info(f"Starting Capital:     ${starting_capital:>15,.0f}")
    logger.info(f"Final Equity:         ${final_equity:>15,.0f}")
    logger.info(f"Total P&L:            ${total_pnl:>15,.0f}")
    logger.info(f"Total Return:         {total_return:>15.2%}")
    logger.info("")
    logger.info(f"Win Rate:             {win_rate:>15.1%}")
    logger.info(f"Max Drawdown:         ${max_drawdown:>15,.0f}")
    logger.info(f"Max Drawdown %:       {max_drawdown_pct:>15.2%}")
    logger.info("=" * 100)
