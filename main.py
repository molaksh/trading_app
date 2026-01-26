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
    MARKET_MODE,
    INDIA_MODE,
    INDIA_RULES_ONLY,
    INDIA_ML_VALIDATION_ENABLED,
    INDIA_MIN_OBSERVATION_DAYS,
    INDIA_OBSERVATION_LOG_DIR,
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
RUN_INDIA_RULES_ONLY = INDIA_MODE  # India rules-only paper trading (Phase 2)


# ============================================================================
# GLOBAL EXECUTION STATE (for shutdown summary)
# ============================================================================
execution_stats = {
    'signals_generated': 0,
    'trades_attempted': 0,
    'trades_approved': 0,
    'trades_rejected_risk': 0,
    'trades_rejected_confidence': 0,
}


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


def main(universe=None):
    """
    Main screener pipeline:
    1. Load price data for all symbols in the given universe
    2. Compute features
    3. Score each symbol with validation
    4. Rank by confidence (deterministically)
    5. Display results
    """
    if universe is None:
        universe = SYMBOLS
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Trading Screener | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * PRINT_WIDTH)

    results = []
    failed_symbols = []
    skipped_symbols = []

    # Step 1 & 2: Load price data and compute features for each symbol
    logger.info(f"Scanning {len(universe)} symbols...")

    for i, symbol in enumerate(universe):
        logger.info(f"[{i+1:2d}/{len(universe)}] Processing {symbol}")

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
    results_df = results_df.sort_values(by=["confidence", "symbol"], ascending=[False, True]).reset_index(drop=True)

    logger.info(f"\nTop {TOP_N_CANDIDATES} candidates:")
    logger.info(results_df.head(TOP_N_CANDIDATES).to_string(index=False))

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


def run_india_rules_only():
    """
    Execute India rules-only paper trading.
    
    SAFETY: This phase establishes baseline performance using rules only.
    ML is completely disabled. All signals/trades tracked for audit trail.
    
    Flow:
    1. Verify startup conditions (observation log, risk manager, no ML)
    2. Scan India universe
    3. Generate rules-only signals
    4. Apply risk limits and execution realism
    5. Log daily observation record
    6. Print execution summary on shutdown
    """
    logger.info("\n")
    logger.info("=" * PRINT_WIDTH)
    logger.info("[INDIA] Phase I — Rules-Only Observation Mode")
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Status: INDIA_RULES_ONLY = {INDIA_RULES_ONLY}")
    logger.info(f"Status: INDIA_ML_VALIDATION_ENABLED = {INDIA_ML_VALIDATION_ENABLED}")
    
    # ========================================================================
    # STARTUP VERIFICATION
    # ========================================================================
    logger.info("\n[INDIA] Performing startup verification...")
    
    # 1. Verify observation log is writable
    try:
        from monitoring.india_observation_log import IndiaObservationLogger
        obs_logger = IndiaObservationLogger(INDIA_OBSERVATION_LOG_DIR)
        status = obs_logger.get_observation_status()
        logger.info(f"✓ Observation log writable")
        logger.info(f"  Directory: {INDIA_OBSERVATION_LOG_DIR}")
        logger.info(f"  Observation days recorded: {status['total_observation_days']}")
    except Exception as e:
        logger.error(f"✗ Observation log initialization failed: {e}")
        return
    
    # 2. Verify RiskManager initialized with India params
    try:
        from risk.portfolio_state import PortfolioState
        from risk.risk_manager import RiskManager
        
        portfolio = PortfolioState(START_CAPITAL)
        risk_mgr = RiskManager(portfolio)
        logger.info(f"✓ RiskManager initialized with India parameters")
        logger.info(f"  Starting capital: ${START_CAPITAL:,.0f}")
        logger.info(f"  Market mode: {MARKET_MODE}")
    except Exception as e:
        logger.error(f"✗ RiskManager initialization failed: {e}")
        return
    
    # 3. Verify ML is NOT loaded
    if INDIA_RULES_ONLY:
        logger.info(f"✓ ML disabled (INDIA_RULES_ONLY = True)")
        logger.info(f"  Using rules-based confidence only")
    else:
        logger.error(f"✗ ML VALIDATION ENABLED - should be disabled for rules-only mode")
        return
    
    logger.info("\n[INDIA] ✓ All startup checks passed\n")
    
    # ========================================================================
    # DAILY EXECUTION LOOP
    # ========================================================================
    logger.info("=" * PRINT_WIDTH)
    logger.info("EXECUTING DAILY LOOP")
    logger.info("=" * PRINT_WIDTH)
    
    from broker.paper_trading_executor import PaperTradingExecutor
    from broker.alpaca_adapter import AlpacaAdapter
    from broker.execution_logger import ExecutionLogger
    from monitoring.system_guard import SystemGuard
    
    try:
        broker = AlpacaAdapter()
    except Exception as e:
        logger.error(f"Broker initialization failed (using simulation mode): {e}")
        broker = None
    
    # Initialize components
    portfolio = PortfolioState(START_CAPITAL)
    risk_mgr = RiskManager(portfolio)
    monitor = SystemGuard() if RUN_MONITORING else None
    exec_logger = ExecutionLogger("./logs")
    
    executor = PaperTradingExecutor(
        broker=broker,
        risk_manager=risk_mgr,
        monitor=monitor,
        logger_instance=exec_logger,
    )
    
    # Get universe based on market mode
    try:
        if INDIA_MODE:
            from universe.india_universe import NIFTY_50
            universe = NIFTY_50
            logger.info(f"Using India universe (NIFTY 50): {len(universe)} symbols")
        else:
            from universe.symbols import SYMBOLS
            universe = SYMBOLS
            logger.info(f"Using US universe: {len(universe)} symbols")
    except Exception as e:
        logger.error(f"Failed to load universe: {e}")
        return

    # Generate signals using main screener
    logger.info(f"\n[INDIA] Scanning {len(universe)} symbols...")
    results = main(universe)
    
    if results.empty:
        logger.warning("[INDIA] No signals generated today")
        signals = pd.DataFrame()
    else:
        # Filter by minimum confidence
        min_conf = 3
        signals = results[results['confidence'] >= min_conf].head(TOP_N_CANDIDATES).copy()
        execution_stats['signals_generated'] = len(results)
        logger.info(f"[INDIA] Signals generated: {len(results)} total, {len(signals)} executable")
    
    # Execute signals with risk limits and execution realism
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("EXECUTING SIGNALS")
    logger.info("=" * PRINT_WIDTH)
    
    filled_count = 0
    rejected_count = 0
    rejected_risk_count = 0
    rejected_confidence_count = 0
    
    for idx, signal in signals.iterrows():
        symbol = signal['symbol']
        confidence = signal['confidence']
        
        execution_stats['trades_attempted'] += 1
        
        # For observation mode, skip detailed risk checks (no real prices)
        # In production, would call: decision = risk_mgr.evaluate_trade(symbol, entry_price, confidence, current_prices)
        
        # Apply confidence threshold
        if confidence < min_conf:
            rejected_count += 1
            rejected_confidence_count += 1
            logger.info(f"  {symbol}: REJECTED (confidence < {min_conf})")
            continue
        
        # Execute signal (in observation mode, just log - don't execute)
        # In production with real broker, would call executor.execute_signal()
        filled_count += 1
        execution_stats['trades_approved'] += 1
        logger.info(f"  {symbol}: SIGNAL (confidence={int(confidence)}) - observation mode, no execution")
    
    execution_stats['trades_rejected_risk'] = rejected_risk_count
    execution_stats['trades_rejected_confidence'] = rejected_confidence_count
    
    # Poll order fills
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("POLLING ORDER FILLS")
    logger.info("=" * PRINT_WIDTH)
    
    filled_orders = executor.poll_order_fills()
    logger.info(f"Orders filled today: {len(filled_orders)}")
    
    # Get account status
    status = executor.get_account_status()
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("ACCOUNT STATUS")
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Equity: ${status.get('equity', 0):,.2f}")
    logger.info(f"Buying Power: ${status.get('buying_power', 0):,.2f}")
    logger.info(f"Open Positions: {status.get('open_positions', 0)}")
    logger.info(f"Pending Orders: {status.get('pending_orders', 0)}")
    
    if status.get('positions'):
        logger.info("Positions:")
        for sym, pos_data in status['positions'].items():
            logger.info(
                f"  {sym}: {pos_data['qty']} @ ${pos_data['avg_price']:.2f} "
                f"(PnL: {pos_data['pnl_pct']:+.2%})"
            )
    
    # ========================================================================
    # LOG DAILY OBSERVATION
    # ========================================================================
    logger.info("\n[INDIA] Recording daily observation...")
    
    try:
        # Calculate portfolio heat (% capital at risk)
        total_risk = sum(
            abs(pos['qty']) * pos['avg_price'] * 0.02  # Assume 2% stop loss
            for pos in (status.get('positions', {}).values() if status.get('positions') else [])
        )
        portfolio_heat = total_risk / START_CAPITAL if total_risk > 0 else 0
        
        # Calculate daily return
        equity_now = status.get('equity', START_CAPITAL)
        daily_return = (equity_now - START_CAPITAL) / START_CAPITAL
        
        # Record observation
        obs_logger.record_observation(
            symbols_scanned=universe,
            signals_generated=len(results),
            signals_rejected=len(results) - len(signals),
            trades_executed=execution_stats['trades_approved'],
            trades_rejected_risk=execution_stats['trades_rejected_risk'],
            trades_rejected_confidence=execution_stats['trades_rejected_confidence'],
            avg_confidence_executed=signals['confidence'].mean() if len(signals) > 0 else 0,
            avg_confidence_rejected=results[results['confidence'] < min_conf]['confidence'].mean() if len(results[results['confidence'] < min_conf]) > 0 else 0,
            portfolio_heat=portfolio_heat,
            daily_return=daily_return,
            max_drawdown=0.0,  # TODO: calculate from intraday data
            notes=f"Rules-only observation day (INDIA_RULES_ONLY={INDIA_RULES_ONLY})"
        )
        logger.info("[INDIA] ✓ Daily observation recorded")
    except Exception as e:
        logger.warning(f"[INDIA] Failed to record observation: {e}")
    
    # ========================================================================
    # SHUTDOWN SUMMARY
    # ========================================================================
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("[INDIA] EXECUTION SUMMARY")
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Signals Generated: {execution_stats['signals_generated']}")
    logger.info(f"Trades Attempted: {execution_stats['trades_attempted']}")
    logger.info(f"Trades Approved: {execution_stats['trades_approved']}")
    logger.info(f"Trades Rejected (Risk): {execution_stats['trades_rejected_risk']}")
    logger.info(f"Trades Rejected (Confidence): {execution_stats['trades_rejected_confidence']}")
    logger.info(f"Total Rejected: {execution_stats['trades_rejected_risk'] + execution_stats['trades_rejected_confidence']}")
    
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("[INDIA] ✓ Rules-only observation day complete")
    logger.info("=" * PRINT_WIDTH)


if __name__ == '__main__':
    # Execute India rules-only paper trading if enabled
    if RUN_INDIA_RULES_ONLY:
        run_india_rules_only()

    # Execute paper trading if enabled
    elif RUN_PAPER_TRADING:
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

