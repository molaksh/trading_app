"""
Compare rule-based vs ML-based confidence on identical backtest.

Runs the same backtest twice:
1. Using rule-based confidence scores
2. Using ML-derived confidence scores

Then compares performance metrics side-by-side.
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from datetime import datetime, timedelta

from config.settings import (
    BACKTEST_LOOKBACK_YEARS,
    HOLD_DAYS,
    BACKTEST_MIN_CONFIDENCE,
    LOOKBACK_DAYS,
)
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol
from backtest.simple_backtest import Trade
from ml.predict import predict_confidence_scores

logger = logging.getLogger(__name__)


def run_backtest_with_ml_confidence(
    symbols: List[str],
    model,
    scaler,
    feature_columns: list,
    include_confidence: bool = False,
) -> List[Trade]:
    """
    Run backtest using ML-derived confidence scores instead of rules.

    Identical to simple_backtest.run_backtest() except confidence
    is computed from ML model instead of rule_scorer.

    Args:
        symbols: List of stock tickers
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        feature_columns: List of ML feature column names
        include_confidence: Whether to include rule-based confidence as feature

    Returns:
        List of Trade objects
    """
    logger.info("=" * 90)
    logger.info(f"Running ML-based backtest ({BACKTEST_LOOKBACK_YEARS}Y, hold {HOLD_DAYS}D, conf >= {BACKTEST_MIN_CONFIDENCE})")
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
            open_positions: Dict = {}

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

                # Build feature vector for ML model
                features = feature_columns.copy()
                if include_confidence and "confidence" in features:
                    # Get rule-based confidence for context
                    rule_confidence = score_symbol(latest_row)
                    if rule_confidence is None:
                        continue
                    latest_row["confidence"] = rule_confidence
                
                try:
                    X = np.array([latest_row[f] for f in features]).reshape(1, -1)
                    ml_confidence = int(predict_confidence_scores(model, scaler, X)[0])
                except Exception as e:
                    logger.debug(f"{symbol} on {trade_date}: ML prediction failed: {e}")
                    continue

                # Check for exit: if position open and hold period expired
                if symbol in open_positions:
                    entry_date = open_positions[symbol]["entry_date"]
                    exit_check_date = entry_date + timedelta(days=HOLD_DAYS)

                    if trade_date >= exit_check_date:
                        # Exit position
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
                if symbol not in open_positions and ml_confidence >= BACKTEST_MIN_CONFIDENCE:
                    # Get next day's open price
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
                        entry_price = full_df.loc[trade_date, "Close"]

                    open_positions[symbol] = {
                        "entry_date": trade_date,
                        "entry_price": entry_price,
                        "confidence": ml_confidence,
                    }

        except Exception as e:
            logger.debug(f"{symbol}: {type(e).__name__}: {e}")
            continue

    logger.info(f"\nBacktest complete: {len(trades)} trades generated")

    return trades


def compute_backtest_metrics(trades: List[Trade]) -> Dict:
    """
    Compute performance metrics from trades list.

    Args:
        trades: List of Trade objects

    Returns:
        Dict with metrics
    """
    if not trades:
        return {
            "num_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "total_return": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_gain": 0.0,
            "max_loss": 0.0,
            "profit_factor": 0.0,
            "by_confidence": {},
        }
    
    returns = [t.return_pct for t in trades]
    
    winning_trades = [r for r in returns if r >= 0]
    losing_trades = [r for r in returns if r < 0]
    
    total_gain = sum(r for r in returns if r >= 0)
    total_loss = sum(abs(r) for r in returns if r < 0)
    
    profit_factor = total_gain / total_loss if total_loss > 0 else float('inf')
    
    metrics = {
        "num_trades": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": len(winning_trades) / len(trades) if trades else 0,
        "avg_return": np.mean(returns),
        "total_return": sum(returns),
        "avg_win": np.mean(winning_trades) if winning_trades else 0,
        "avg_loss": np.mean(losing_trades) if losing_trades else 0,
        "max_gain": max(returns) if returns else 0,
        "max_loss": min(returns) if returns else 0,
        "profit_factor": profit_factor,
    }
    
    # Metrics by confidence level
    by_confidence = {}
    for conf in range(1, 6):
        conf_trades = [t for t in trades if t.confidence == conf]
        if conf_trades:
            conf_returns = [t.return_pct for t in conf_trades]
            by_confidence[conf] = {
                "count": len(conf_trades),
                "win_rate": sum(1 for r in conf_returns if r >= 0) / len(conf_trades),
                "avg_return": np.mean(conf_returns),
            }
    metrics["by_confidence"] = by_confidence
    
    return metrics


def print_comparison_table(
    rule_metrics: Dict,
    ml_metrics: Dict,
) -> None:
    """
    Print clean comparison table of rule-based vs ML metrics.

    Args:
        rule_metrics: Metrics from rule-based backtest
        ml_metrics: Metrics from ML-based backtest
    """
    logger.info("\n" + "=" * 100)
    logger.info("BACKTEST COMPARISON: RULE-BASED vs ML-DERIVED CONFIDENCE")
    logger.info("=" * 100)
    
    # Main metrics table
    logger.info(f"\n{'Metric':<35} {'Rules':<20} {'ML':<20} {'Δ':<10}")
    logger.info("-" * 85)
    
    metrics_to_show = [
        ("Number of Trades", "num_trades", "{:.0f}"),
        ("Winning Trades", "winning_trades", "{:.0f}"),
        ("Losing Trades", "losing_trades", "{:.0f}"),
        ("Win Rate", "win_rate", "{:.1%}"),
        ("Avg Return per Trade", "avg_return", "{:.2%}"),
        ("Total Return", "total_return", "{:.2%}"),
        ("Max Gain", "max_gain", "{:.2%}"),
        ("Max Loss", "max_loss", "{:.2%}"),
        ("Avg Win", "avg_win", "{:.2%}"),
        ("Avg Loss", "avg_loss", "{:.2%}"),
        ("Profit Factor", "profit_factor", "{:.2f}"),
    ]
    
    for label, key, fmt in metrics_to_show:
        rule_val = rule_metrics[key]
        ml_val = ml_metrics[key]
        
        if fmt.endswith("%"):
            rule_str = f"{rule_val:.1%}"
            ml_str = f"{ml_val:.1%}"
            if rule_val != 0:
                delta = (ml_val - rule_val) / abs(rule_val)
                delta_str = f"{delta:+.1%}"
            else:
                delta_str = "N/A"
        elif fmt.endswith("f"):
            rule_str = f"{rule_val:.2f}"
            ml_str = f"{ml_val:.2f}"
            if rule_val != 0:
                delta = (ml_val - rule_val) / abs(rule_val)
                delta_str = f"{delta:+.1%}"
            else:
                delta_str = "N/A"
        else:
            rule_str = f"{rule_val:.0f}"
            ml_str = f"{ml_val:.0f}"
            if rule_val != 0:
                delta = (ml_val - rule_val) / rule_val
                delta_str = f"{delta:+.1%}"
            else:
                delta_str = "N/A"
        
        logger.info(f"{label:<35} {rule_str:>19} {ml_str:>19} {delta_str:>9}")
    
    # Confidence distribution
    logger.info("\n" + "-" * 85)
    logger.info("Performance by Confidence Level (Rules)")
    logger.info("-" * 85)
    
    for conf in range(5, 0, -1):
        if conf in rule_metrics["by_confidence"]:
            data = rule_metrics["by_confidence"][conf]
            logger.info(
                f"  Confidence {conf}: {data['count']:3d} trades, "
                f"WR={data['win_rate']:.1%}, "
                f"Avg Return={data['avg_return']:+.2%}"
            )
    
    logger.info("\n" + "-" * 85)
    logger.info("Performance by Confidence Level (ML)")
    logger.info("-" * 85)
    
    for conf in range(5, 0, -1):
        if conf in ml_metrics["by_confidence"]:
            data = ml_metrics["by_confidence"][conf]
            logger.info(
                f"  Confidence {conf}: {data['count']:3d} trades, "
                f"WR={data['win_rate']:.1%}, "
                f"Avg Return={data['avg_return']:+.2%}"
            )
    
    logger.info("\n" + "=" * 100)


def evaluate_ml_vs_rules(
    symbols: List[str],
    model,
    scaler,
    feature_columns: list,
    include_confidence: bool = False,
) -> Tuple[Dict, Dict]:
    """
    Run complete evaluation: backtest rules, backtest ML, compare.

    Args:
        symbols: List of stock tickers
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        feature_columns: List of ML feature column names
        include_confidence: Whether to include rule-based confidence as feature

    Returns:
        Tuple of (rule_metrics, ml_metrics)
    """
    logger.info("\n" + "=" * 100)
    logger.info("ML VALIDATION EXPERIMENT")
    logger.info("=" * 100)
    
    # Import here to avoid circular dependency
    from backtest.simple_backtest import run_backtest
    
    # Run rule-based backtest
    logger.info("\n[1/2] Running rule-based backtest...")
    rule_trades = run_backtest(symbols)
    rule_metrics = compute_backtest_metrics(rule_trades)
    
    # Run ML-based backtest
    logger.info("\n[2/2] Running ML-based backtest...")
    ml_trades = run_backtest_with_ml_confidence(
        symbols, model, scaler, feature_columns, include_confidence
    )
    ml_metrics = compute_backtest_metrics(ml_trades)
    
    # Print comparison
    print_comparison_table(rule_metrics, ml_metrics)
    
    return rule_metrics, ml_metrics
