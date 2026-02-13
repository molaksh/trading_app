from runtime.trade_permission import get_trade_permission
"""
Main trading screener orchestration.
Loads data, computes features, scores symbols, and ranks candidates.
Production-grade with logging, error handling, and validation.

Loads environment variables from a local .env (if present) so broker
credentials are picked up automatically without exporting shell env.
"""

import logging
import os
import sys
import argparse
from typing import Optional
import pandas as pd
from datetime import datetime

# Load .env early so downstream modules see credentials
def _load_dotenv_if_present():
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        return
    except Exception:
        pass
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key and val and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            # Non-fatal: fallback is existing environment
            pass


_load_dotenv_if_present()

from config.settings import (
    LOOKBACK_DAYS,
    TOP_N_CANDIDATES,
    PRINT_WIDTH,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    START_CAPITAL,
)
from config.scope import get_scope
from execution.runtime import (
    PaperTradingRuntime,
    build_paper_trading_runtime,
    reconcile_runtime,
)
from crypto.scope_guard import validate_crypto_universe_symbols
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


def _is_crypto_scope(scope) -> bool:
    return scope.mode.lower() == "crypto" or scope.broker.lower() == "kraken"


def _get_symbols_for_scope(scope):
    # Phase G: If enabled, load active universe from persistence
    from universe.governance.config import PHASE_G_ENABLED
    if PHASE_G_ENABLED:
        from universe.governance.persistence import UniverseGovernancePersistence
        persistence = UniverseGovernancePersistence(str(scope))
        active = persistence.load_active_universe()
        if active:
            logger.info("PHASE_G_UNIVERSE_LOADED | symbols=%s", active)
            if _is_crypto_scope(scope):
                return validate_crypto_universe_symbols(active)
            return active
        logger.info("PHASE_G_UNIVERSE_FALLBACK | no active universe, using default")

    if _is_crypto_scope(scope):
        from config.crypto.loader import load_crypto_config
        from crypto.universe import CryptoUniverse

        crypto_config = load_crypto_config(scope)
        symbols = crypto_config.get("CRYPTO_UNIVERSE", ["BTC", "ETH", "SOL"])
        canonical = validate_crypto_universe_symbols(symbols)
        universe = CryptoUniverse(symbols=canonical)
        logger.info("crypto_universe symbols=%s", universe.all_canonical_symbols())
        return universe.all_canonical_symbols()

    from universe.symbols import SYMBOLS
    return SYMBOLS


def _load_price_data_for_scope(scope, symbol: str, lookback_days: int):
    if _is_crypto_scope(scope):
        from data.crypto_price_loader import load_crypto_price_data

        return load_crypto_price_data(symbol, lookback_days)

    from data.price_loader import load_price_data

    return load_price_data(symbol, lookback_days)


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
    
    scope = get_scope()
    results = []
    failed_symbols = []
    skipped_symbols = []

    symbols = _get_symbols_for_scope(scope)
    logger.info(f"Scanning {len(symbols)} symbols...")
    
    # Step 1 & 2: Load price data and compute features for each symbol
    for i, symbol in enumerate(symbols):
        logger.info(f"[{i+1:2d}/{len(symbols)}] Processing {symbol}")
        try:
            # Load data
            df = _load_price_data_for_scope(scope, symbol, LOOKBACK_DAYS)
            if df is None or len(df) == 0:
                logger.warning(f"  {symbol}: Skipping (no data)")
                skipped_symbols.append((symbol, "no_data"))
                if scope.market.lower() == "india":
                    raise RuntimeError(f"NSE returned empty data for {symbol}")
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
            if scope.market.lower() == "india":
                raise
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
    logger.info("=" * PRINT_WIDTH)
    logger.info("SUMMARY")
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Total symbols scanned: {len(symbols)}")
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


def run_paper_trading(mode='trade', runtime: Optional[PaperTradingRuntime] = None) -> PaperTradingRuntime:
    """
    Execute paper trading flow.
    
    Modes:
    - 'trade': Full trading (generate signals, submit buys, evaluate exits)
              Run once daily after market close
    - 'monitor': Exit monitoring only (no new signals/buys, only check exits)
                 Run periodically during market hours for emergency exits
    
    Args:
        mode: 'trade' or 'monitor'
    """
    logger.info("\n")
    logger.info("=" * PRINT_WIDTH)
    if mode == 'monitor':
        logger.info("MONITORING MODE - Exit Evaluation Only")
    else:
        logger.info("TRADING MODE - Full Signal Generation & Execution")
    logger.info("=" * PRINT_WIDTH)
    
    # Build or reuse long-lived runtime so pending orders and ledger persist across tasks
    if runtime is None:
        try:
            runtime = build_paper_trading_runtime()
        except Exception as e:
            logger.error(f"Failed to initialize trading runtime: {e}")
            logger.error("Paper trading disabled")
            raise
    
    broker = runtime.broker
    risk_manager = runtime.risk_manager
    trade_ledger = runtime.trade_ledger
    executor = runtime.executor
    scope = runtime.scope
    run_id = None
    if _is_crypto_scope(scope):
        from crypto.pipeline.logging import log_pipeline_stage
        import uuid

        run_id = str(uuid.uuid4())
    
    # ========================================================================
    # STARTUP RECONCILIATION (MANDATORY)
    # ========================================================================
    reconciliation_result = reconcile_runtime(runtime)
    startup_status = reconciliation_result["status"]
    safe_mode = reconciliation_result["safe_mode"]

    if _is_crypto_scope(scope):
        log_pipeline_stage(
            stage="RECONCILIATION_SUMMARY",
            scope=str(scope),
            run_id=run_id,
            symbols=_get_symbols_for_scope(scope),
            extra={
                "status": reconciliation_result.get("status"),
                "safe_mode": reconciliation_result.get("safe_mode"),
            },
        )

    # Runtime trade permission snapshot (visibility)
    snapshot = get_trade_permission().snapshot()
    logger.info(
        "RUNTIME_TRADE_PERMISSION | ENV=%s BROKER=%s TRADING_ALLOWED=%s "
        "BLOCK_STATE=%s BLOCK_REASON=%s LAST_BLOCK_CHANGE=%s",
        snapshot.get("ENV"),
        snapshot.get("BROKER"),
        snapshot.get("TRADING_ALLOWED"),
        snapshot.get("BLOCK_STATE"),
        snapshot.get("BLOCK_REASON"),
        snapshot.get("LAST_BLOCK_CHANGE"),
    )
    
    # Check if we can proceed with trading
    if startup_status == "FAILED":
        logger.error("CRITICAL: Startup validation failed. NO TRADING.")
        return runtime
    elif startup_status == "EXIT_ONLY":
        logger.warning("Risk validation failed. Entering EXIT_ONLY mode.")
    elif startup_status == "SAFE_MODE":
        logger.warning("Startup warnings detected. Entering SAFE_MODE.")
    
    # TRADE MODE: Generate signals and submit orders
    if mode == 'trade':
        # Check if safe mode blocks new entries
        if safe_mode and startup_status != "READY":
            logger.warning(f"Safe mode active ({startup_status}). New entries blocked.")
            # Skip signal generation and go straight to exit evaluation
            results = pd.DataFrame()
        else:
            logger.info("\n🔵 TRADE MODE: Generating signals and submitting orders...")
            if _is_crypto_scope(scope):
                from crypto.pipeline import run_crypto_pipeline

                results = run_crypto_pipeline(runtime=runtime, run_id=run_id)
            else:
                results = main()
        
        if results.empty:
            logger.warning("No signals generated. Proceeding to exit evaluation only.")
            filled_count = 0
            rejected_count = 0
        else:
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

                if _is_crypto_scope(scope):
                    regime_value = None
                    if hasattr(runtime, "crypto_state") and runtime.crypto_state:
                        history = runtime.crypto_state.get("regime_history", [])
                        regime_value = history[-1] if history else None
                    log_pipeline_stage(
                        stage="RISK_DECISION",
                        scope=str(scope),
                        run_id=run_id,
                        symbols=[symbol],
                        extra={"confidence": int(confidence), "regime": regime_value},
                    )

                success, order_id = executor.execute_signal(
                    symbol=symbol,
                    confidence=int(confidence),
                    signal_date=pd.Timestamp.now(),
                    features=signal.to_dict(),
                )

                if _is_crypto_scope(scope):
                    regime_value = None
                    if hasattr(runtime, "crypto_state") and runtime.crypto_state:
                        history = runtime.crypto_state.get("regime_history", [])
                        regime_value = history[-1] if history else None
                    log_pipeline_stage(
                        stage="EXECUTION_DECISION",
                        scope=str(scope),
                        run_id=run_id,
                        symbols=[symbol],
                        extra={"success": success, "order_id": order_id, "regime": regime_value},
                    )
                
                if success:
                    filled_count += 1
                else:
                    rejected_count += 1
    else:
        # MONITOR MODE: Skip signal generation
        logger.info("\n👁️  MONITOR MODE: Skipping signal generation (exits only)")
        filled_count = 0
        rejected_count = 0
    
    # Poll order fills (both modes)
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("POLLING ORDER FILLS")
    logger.info("=" * PRINT_WIDTH)
    
    filled_orders = executor.poll_order_fills()
    logger.info(f"Newly filled: {len(filled_orders)}")
    
    # Evaluate exit signals for existing positions
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("EVALUATING EXIT SIGNALS")
    logger.info("=" * PRINT_WIDTH)
    
    # Check emergency exits (intraday risk protection)
    emergency_exits = executor.evaluate_exits_emergency()
    if emergency_exits:
        logger.warning(f"🚨 {len(emergency_exits)} EMERGENCY EXIT(S) triggered!")
        for exit_signal in emergency_exits:
            logger.warning(f"  {exit_signal.symbol}: {exit_signal.reason}")
            # Execute emergency exit immediately
            executor.execute_exit(exit_signal)
    else:
        logger.info("✓ No emergency exits (normal market conditions)")
    
    # Check swing exits (EOD strategy exits)
    # Note: In production, run this AFTER market close with EOD data
    swing_exits = executor.evaluate_exits_eod()
    if swing_exits:
        logger.info(f"📊 {len(swing_exits)} swing exit signal(s) generated")
        for exit_signal in swing_exits:
            logger.info(f"  {exit_signal.symbol}: {exit_signal.reason}")
            # In production: execute these at next market open
            # For now, execute immediately for demo
            executor.execute_exit(exit_signal)
    else:
        logger.info("✓ No swing exits (positions within targets)")
    
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
    env_value = getattr(runtime, "env", None)
    if env_value is None and hasattr(runtime, "scope"):
        env_value = runtime.scope.env
    env_label = "Paper trading" if str(env_value).lower() == "paper" else "Live trading"
    logger.info(f"✓ {env_label} execution complete")
    logger.info("=" * PRINT_WIDTH)

    if _is_crypto_scope(scope):
        log_pipeline_stage(
            stage="CYCLE_SUMMARY",
            scope=str(scope),
            run_id=run_id,
            symbols=_get_symbols_for_scope(scope),
            extra={
                "signals_processed": filled_count + rejected_count,
                "orders_submitted": filled_count,
                "rejections": rejected_count,
            },
        )
    
    return runtime


if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Swing Trading System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full trading mode (run after market close):
  python3 main.py --trade
  
  # Monitor mode (run during market hours for emergency exits only):
  python3 main.py --monitor
  
  # Default behavior (if no args):
  python3 main.py
        """
    )
    parser.add_argument(
        '--trade',
        action='store_true',
        help='Trading mode: generate signals and submit orders (run after market close)'
    )
    parser.add_argument(
        '--monitor',
        action='store_true',
        help='Monitor mode: check exits only, no new signals (run during market hours)'
    )
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Run continuous scheduler (intraday monitoring + daily entries)'
    )
    
    args = parser.parse_args()
    
    # Determine mode
    if args.schedule:
        trading_mode = 'schedule'
    elif args.monitor:
        trading_mode = 'monitor'
    elif args.trade:
        trading_mode = 'trade'
    else:
        # Default: if RUN_PAPER_TRADING is on and no explicit mode, use trade mode
        trading_mode = 'trade' if RUN_PAPER_TRADING else None
    
    # Execute paper trading if enabled
    if RUN_PAPER_TRADING and trading_mode:
        if trading_mode == 'schedule':
            from execution.scheduler import TradingScheduler
            
            scheduler = TradingScheduler()
            scheduler.run_forever()
        else:
            run_paper_trading(mode=trading_mode)
    
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

