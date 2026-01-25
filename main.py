"""
Main trading screener orchestration.
Loads data, computes features, scores symbols, and ranks candidates.
Production-grade with logging, error handling, and validation.
"""

import logging
import pandas as pd
from datetime import datetime

from config.settings import (
    LOOKBACK_DAYS,
    TOP_N_CANDIDATES,
    PRINT_WIDTH,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    START_CAPITAL,
)
from universe.symbols import SYMBOLS
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol

# ============================================================================
# EXECUTION MODE FLAGS
# ============================================================================
RUN_BACKTEST = False        # Set to True to run diagnostic backtest
BUILD_DATASET = False       # Set to True to build ML-ready dataset
RUN_ML_EXPERIMENT = False   # Set to True to train & compare ML model vs rules
RUN_RISK_GOVERNANCE = False # Set to True to run backtest with risk limits
RUN_EXECUTION_REALISM = False  # Set to True to show execution realism impact (Phase G)
RUN_MONITORING = False      # Set to True to enable monitoring & drift detection (Phase H)
RUN_PAPER_TRADING = True    # Set to True to execute trades via paper trading (Phase I)


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def _setup_logging():
    """Configure logging for the application."""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    
    # Console handler
    handler = logging.StreamHandler()
    handler.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handler.setFormatter(formatter)
    
    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()
    logger.addHandler(handler)
    
    return logger


logger = _setup_logging()


def main():
    """
    Main screener pipeline:
    1. Load price data for all symbols
    2. Compute features
    3. Score each symbol with validation
    4. Rank by confidence (deterministically)
    5. Display results
    """
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Trading Screener | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * PRINT_WIDTH)
    
    results = []
    failed_symbols = []
    skipped_symbols = []
    
    # Step 1 & 2: Load price data and compute features for each symbol
    logger.info(f"Scanning {len(SYMBOLS)} symbols...")
    
    for i, symbol in enumerate(SYMBOLS):
        logger.info(f"[{i+1:2d}/{len(SYMBOLS)}] Processing {symbol}")
        
        try:
            # Load data
            df = load_price_data(symbol, LOOKBACK_DAYS)
            if df is None or len(df) == 0:
                logger.warning(f"  {symbol}: Skipping (no data)")
                skipped_symbols.append((symbol, "no_data"))
                continue
            
            # Compute features
            features_df = compute_features(df)
            if features_df is None or len(features_df) == 0:
                logger.warning(f"  {symbol}: Skipping (insufficient history)")
                skipped_symbols.append((symbol, "insufficient_history"))
                continue
            
            # Take latest row only
            latest_row = features_df.iloc[-1].copy()
            
            # Validate latest row
            if latest_row.isna().any():
                logger.warning(f"  {symbol}: Skipping (NaN values in features)")
                skipped_symbols.append((symbol, "nan_values"))
                continue
            
            # Step 3: Score
            confidence = score_symbol(latest_row)
            
            if confidence is None:
                logger.warning(f"  {symbol}: Skipping (score computation failed)")
                skipped_symbols.append((symbol, "score_failed"))
                continue
            
            # Store result
            result_dict = {
                'symbol': symbol,
                'confidence': confidence,
                'close': latest_row['close'],
                'sma_20': latest_row['sma_20'],
                'sma_200': latest_row['sma_200'],
                'dist_20sma': latest_row['dist_20sma'],
                'dist_200sma': latest_row['dist_200sma'],
                'sma20_slope': latest_row['sma20_slope'],
                'atr_pct': latest_row['atr_pct'],
                'vol_ratio': latest_row['vol_ratio'],
                'pullback_depth': latest_row['pullback_depth'],
            }
            results.append(result_dict)
            logger.info(f"  {symbol}: OK (confidence={confidence})")
        
        except Exception as e:
            logger.error(f"  {symbol}: Unexpected error: {type(e).__name__}: {e}")
            failed_symbols.append((symbol, str(e)))
            continue
    
    # Step 4: Rank by confidence (deterministically)
    if len(results) == 0:
        logger.error("No valid candidates found. Cannot continue.")
        logger.info("=" * PRINT_WIDTH)
        return pd.DataFrame()
    
    results_df = pd.DataFrame(results)
    
    # Sort deterministically: confidence (descending), then symbol (ascending)
    results_df = results_df.sort_values(
        by=['confidence', 'symbol'],
        ascending=[False, True]
    ).reset_index(drop=True)
    
    results_df['rank'] = range(1, len(results_df) + 1)
    
    # Step 5: Display top candidates
    logger.info("=" * PRINT_WIDTH)
    logger.info("TOP CANDIDATES")
    logger.info("=" * PRINT_WIDTH)
    
    display_df = results_df.head(TOP_N_CANDIDATES)[[
        'rank', 'symbol', 'confidence',
        'dist_200sma', 'vol_ratio', 'atr_pct'
    ]].copy()
    
    # Pretty print
    logger.info(f"\n{'Rank':<6} {'Symbol':<8} {'Conf':<6} {'Dist200SMA':<12} {'VolRatio':<10} {'ATRPct':<10}")
    logger.info("-" * 65)
    
    for _, row in display_df.iterrows():
        logger.info(
            f"{int(row['rank']):<6} "
            f"{row['symbol']:<8} "
            f"{int(row['confidence']):<6} "
            f"{row['dist_200sma']:>11.2%} "
            f"{row['vol_ratio']:>9.2f} "
            f"{row['atr_pct']:>9.2%}"
        )
    
    # Summary
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("SUMMARY")
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Total symbols scanned: {len(SYMBOLS)}")
    logger.info(f"Successfully scored: {len(results_df)}")
    logger.info(f"Skipped: {len(skipped_symbols)}")
    logger.info(f"Failed: {len(failed_symbols)}")
    
    if skipped_symbols:
        logger.info(f"\nSkipped symbols:")
        for symbol, reason in skipped_symbols[:5]:
            logger.info(f"  {symbol}: {reason}")
        if len(skipped_symbols) > 5:
            logger.info(f"  ... and {len(skipped_symbols) - 5} more")
    
    if failed_symbols:
        logger.warning(f"\nFailed symbols:")
        for symbol, error in failed_symbols[:5]:
            logger.warning(f"  {symbol}: {error}")
        if len(failed_symbols) > 5:
            logger.warning(f"  ... and {len(failed_symbols) - 5} more")
    
    # Confidence distribution
    logger.info(f"\nConfidence distribution:")
    conf_counts = results_df['confidence'].value_counts().sort_index(ascending=False)
    for conf, count in conf_counts.items():
        pct = 100 * count / len(results_df)
        logger.info(f"  Confidence {int(conf)}: {count:3d} symbols ({pct:5.1f}%)")
    
    logger.info("=" * PRINT_WIDTH)
    
    return results_df


def run_paper_trading():
    """
    Execute paper trading flow.
    
    1. Generate signals
    2. Submit orders to broker
    3. Track fills
    4. Monitor degradation
    5. Log all activity
    """
    logger.info("\n")
    logger.info("=" * PRINT_WIDTH)
    logger.info("PAPER TRADING EXECUTION (Phase I)")
    logger.info("=" * PRINT_WIDTH)
    
    from broker.alpaca_adapter import AlpacaAdapter
    from broker.paper_trading_executor import PaperTradingExecutor
    from broker.execution_logger import ExecutionLogger
    from risk.portfolio_state import PortfolioState
    from risk.risk_manager import RiskManager
    from monitoring.system_guard import SystemGuard
    
    # Safety check: paper trading only
    try:
        broker = AlpacaAdapter()
    except Exception as e:
        logger.error(f"Failed to initialize broker: {e}")
        logger.error("Paper trading disabled")
        return
    
    # Initialize components
    portfolio_state = PortfolioState(START_CAPITAL)
    risk_manager = RiskManager(portfolio_state)
    
    # Initialize monitoring (Phase H)
    monitor = None
    if RUN_MONITORING:
        monitor = SystemGuard()
        logger.info("Monitoring enabled (Phase H)")
    
    # Initialize execution logging
    exec_logger = ExecutionLogger("./logs")
    
    # Initialize executor
    executor = PaperTradingExecutor(
        broker=broker,
        risk_manager=risk_manager,
        monitor=monitor,
        logger_instance=exec_logger,
    )
    
    # Generate signals
    logger.info("\nGenerating signals...")
    results = main()
    
    if results.empty:
        logger.warning("No signals generated. Cannot proceed.")
        return
    
    # Filter by minimum confidence
    min_conf = 3
    signals = results[results['confidence'] >= min_conf].head(TOP_N_CANDIDATES).copy()
    
    logger.info(f"\nSignals to execute: {len(signals)}")
    logger.info("=" * PRINT_WIDTH)
    
    # Execute each signal
    filled_count = 0
    rejected_count = 0
    
    for idx, signal in signals.iterrows():
        symbol = signal['symbol']
        confidence = signal['confidence']
        
        success, order_id = executor.execute_signal(
            symbol=symbol,
            confidence=int(confidence),
            signal_date=pd.Timestamp.now(),
            features=signal.to_dict(),
        )
        
        if success:
            filled_count += 1
        else:
            rejected_count += 1
    
    # Poll order fills
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("POLLING ORDER FILLS")
    logger.info("=" * PRINT_WIDTH)
    
    filled_orders = executor.poll_order_fills()
    logger.info(f"Newly filled: {len(filled_orders)}")
    
    # Print account status
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("ACCOUNT STATUS")
    logger.info("=" * PRINT_WIDTH)
    
    status = executor.get_account_status()
    logger.info(f"Equity: ${status.get('equity', 0):.2f}")
    logger.info(f"Buying Power: ${status.get('buying_power', 0):.2f}")
    logger.info(f"Open Positions: {status.get('open_positions', 0)}")
    logger.info(f"Pending Orders: {status.get('pending_orders', 0)}")
    
    if status.get('positions'):
        logger.info("\nPositions:")
        for sym, pos_data in status['positions'].items():
            logger.info(
                f"  {sym}: {pos_data['qty']} @ ${pos_data['avg_price']:.2f} "
                f"(PnL: {pos_data['pnl_pct']:+.2%})"
            )
    
    # Print summary
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * PRINT_WIDTH)
    
    summary = executor.get_execution_summary()
    logger.info(f"Signals Processed: {filled_count + rejected_count}")
    logger.info(f"Orders Submitted: {filled_count}")
    logger.info(f"Rejections: {rejected_count}")
    logger.info(f"Filled Orders: {summary['execution_logger']['filled']}")
    logger.info(f"Monitoring Alerts: {summary['execution_logger']['alerts']}")
    
    logger.info("=" * PRINT_WIDTH)
    logger.info("✓ Paper trading execution complete")
    logger.info("=" * PRINT_WIDTH)


if __name__ == '__main__':
    # Execute paper trading if enabled
    if RUN_PAPER_TRADING:
        run_paper_trading()
    
    # Execute dataset building if enabled
    elif BUILD_DATASET:
        logger.info("\n")
        from dataset.dataset_builder import build_dataset_pipeline
        
        filepath = build_dataset_pipeline(SYMBOLS, LOOKBACK_DAYS)
        if filepath:
            logger.info(f"\n✓ Dataset successfully built and saved to: {filepath}")
        else:
            logger.error("Dataset building failed")
    
    else:
        # Run regular screener
        results = main()
        
        # Optional: Run diagnostic backtest with capital simulation
        if RUN_BACKTEST:
            logger.info("\n")
            from backtest.simple_backtest import run_backtest
            from backtest.metrics import print_metrics, print_capital_metrics
            from backtest.capital_simulator import simulate_capital_growth
            
            trades = run_backtest(SYMBOLS)
            print_metrics(trades)
            
            # Run capital simulation
            metrics, equity_curve = simulate_capital_growth(trades)
            print_capital_metrics(metrics)
        
        # Optional: Run ML validation experiment
        if RUN_ML_EXPERIMENT:
            logger.info("\n")
            from pathlib import Path
            from ml.train_model import train_and_evaluate
            from ml.evaluate import evaluate_ml_vs_rules
            
            # Find latest dataset file
            data_dir = Path("./data")
            csv_files = sorted(data_dir.glob("ml_dataset_*.csv"))
            
            if not csv_files:
                logger.error("No ML dataset found. Set BUILD_DATASET=True first.")
            else:
                dataset_path = str(csv_files[-1])
                logger.info(f"Using dataset: {dataset_path}")
                
                # Train model (70% train, 30% test, no shuffling)
                result = train_and_evaluate(
                    dataset_path,
                    include_confidence=False,  # Don't use rule confidence as feature
                    train_ratio=0.7,
                )
                
                model = result["model"]
                scaler = result["scaler"]
                features = result["features"]
                
                # Compare rule-based vs ML-based backtests
                rule_metrics, ml_metrics = evaluate_ml_vs_rules(
                    SYMBOLS,
                    model,
                    scaler,
                    features,
                    include_confidence=False,
                )
        
        # Optional: Run risk-governed backtest
        if RUN_RISK_GOVERNANCE:
            logger.info("\n")
            from backtest.risk_backtest import run_risk_governed_backtest
            from backtest.metrics import print_metrics
            
            # Run backtest with risk limits enabled
            logger.info("Running risk-governed backtest (with risk limits)...")
            trades_with_risk = run_risk_governed_backtest(SYMBOLS, enforce_risk=True)
            print_metrics(trades_with_risk)
            
            # Run backtest without risk limits for comparison
            logger.info("\n")
            logger.info("Running research backtest (no risk limits)...")
            trades_no_risk = run_risk_governed_backtest(SYMBOLS, enforce_risk=False)
            print_metrics(trades_no_risk)
            
            # Print comparison
            logger.info("\n" + "=" * PRINT_WIDTH)
            logger.info("RISK GOVERNANCE IMPACT")
            logger.info("=" * PRINT_WIDTH)
            
            if trades_with_risk and trades_no_risk:
                win_rate_with_risk = sum(1 for t in trades_with_risk if t.return_pct >= 0) / len(trades_with_risk)
                win_rate_no_risk = sum(1 for t in trades_no_risk if t.return_pct >= 0) / len(trades_no_risk)
                
                return_with_risk = sum(t.return_pct for t in trades_with_risk) / len(trades_with_risk)
                return_no_risk = sum(t.return_pct for t in trades_no_risk) / len(trades_no_risk)
                
                logger.info(f"\n{'Metric':<30} {'With Risk Limits':<20} {'No Limits':<20}")
                logger.info("-" * 70)
                logger.info(f"{'Trade Count':<30} {len(trades_with_risk):<20} {len(trades_no_risk):<20}")
                logger.info(f"{'Win Rate':<30} {win_rate_with_risk:.1%}{'':13} {win_rate_no_risk:.1%}")
                logger.info(f"{'Avg Return':<30} {return_with_risk:.2%}{'':14} {return_no_risk:.2%}")
            
            logger.info("=" * PRINT_WIDTH)

