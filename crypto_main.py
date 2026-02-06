"""
Crypto daemon entry point: runs 24/7 scheduler with trading + ML.

This wraps main.py's run_paper_trading() in a CryptoScheduler that:
- Runs continuously (not batch)
- Pauses trading during daily downtime window (UTC, configurable)
- Executes ML training/validation only during downtime (paper/live)
- Persists scheduler state so tasks don't rerun after restarts

Use instead of main.py for continuous crypto trading:
  python crypto_main.py          # Run daemon (blocking)
  python crypto_main.py --help   # Show options

Environment variables (passed from docker run -e):
  CRYPTO_DOWNTIME_START_UTC     Default: "03:00"
  CRYPTO_DOWNTIME_END_UTC       Default: "05:00"
  CRYPTO_SCHEDULER_TICK_SECONDS Default: 60
  CRYPTO_TRADING_TICK_INTERVAL_MINUTES Default: 1
"""

import logging
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT
from config.scope import get_scope
from config.crypto_scheduler_settings import (
    CRYPTO_DOWNTIME_START_UTC,
    CRYPTO_DOWNTIME_END_UTC,
    CRYPTO_SCHEDULER_TICK_SECONDS,
    CRYPTO_TRADING_TICK_INTERVAL_MINUTES,
    CRYPTO_RUN_STARTUP_RECONCILIATION,
)
from execution.crypto_scheduler import CryptoScheduler, CryptoSchedulerTask
from execution.runtime import build_paper_trading_runtime, reconcile_runtime
from main import run_paper_trading
from crypto.scheduling import TradingState

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def _setup_logging():
    """Configure logging for the application."""
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


def _task_trading_tick(runtime=None):
    """
    Execute trading pipeline once (scan/score/execute).
    
    Called periodically outside downtime window.
    """
    logger.info("-" * 80)
    logger.info("TRADING TICK")
    logger.info("-" * 80)
    
    try:
        # Reuse runtime across ticks so orders/ledger persist
        runtime = run_paper_trading(mode='trade', runtime=runtime)
        return runtime
    except Exception as e:
        logger.error(f"Trading tick failed: {e}", exc_info=True)
        return runtime


def _task_monitor(runtime=None):
    """
    Monitor existing positions and execute exits (emergency + EOD).
    
    Called periodically, including during downtime.
    """
    logger.info("-" * 80)
    logger.info("MONITOR (Exits Only)")
    logger.info("-" * 80)
    
    try:
        runtime = run_paper_trading(mode='monitor', runtime=runtime)
        return runtime
    except Exception as e:
        logger.error(f"Monitor task failed: {e}", exc_info=True)
        return runtime


def _task_ml_training(runtime=None):
    """
    Run ML training cycle (paper only, during downtime).
    
    CRITICAL SAFETY: ML training is gated by trade eligibility.
    Only executes when:
    1. Environment is PAPER (not live trading)
    2. At least one closed trade exists in ledger
    3. ML orchestrator is available and implemented
    
    If any gate fails, logs the reason and returns cleanly (no work, no fake completion logs).
    
    Called once per day during downtime window.
    Live trading: blocked by environment guard.
    """
    logger.info("-" * 80)
    logger.info("ML TRAINING (Paper Only)")
    logger.info("-" * 80)
    
    try:
        from runtime.environment_guard import get_environment_guard, TradingEnvironment
        guard = get_environment_guard()
        
        # GATE 1: Paper-only
        if guard.environment != TradingEnvironment.PAPER:
            logger.warning("ML training disabled in live mode")
            return runtime
        
        if runtime is None:
            runtime = build_paper_trading_runtime()
        
        # GATE 2: Trade eligibility check
        trades = runtime.trade_ledger.get_all_trades()
        if not trades:
            logger.info(
                f"event=ML_TRAINING_SKIPPED | reason=no_trades_available | "
                f"trade_count=0 | status=NORMAL"
            )
            return runtime
        
        # GATE 3: ML orchestrator availability
        try:
            ml_orchestrator = runtime._get_ml_orchestrator()
            if not ml_orchestrator:
                logger.info(
                    f"event=ML_TRAINING_SKIPPED | reason=ml_orchestrator_unavailable | "
                    f"trade_count={len(trades)} | status=NOT_IMPLEMENTED"
                )
                return runtime
        except (AttributeError, NotImplementedError):
            logger.info(
                f"event=ML_TRAINING_SKIPPED | reason=ml_orchestrator_not_implemented | "
                f"trade_count={len(trades)} | status=NOT_IMPLEMENTED"
            )
            return runtime
        
        # All gates passed — log start and execute
        logger.info(
            f"event=ML_TRAINING_START | trade_count={len(trades)} | "
            f"status=RUNNING"
        )
        
        model_info = ml_orchestrator.run_offline_ml_cycle()
        
        if model_info and model_info.get("model_version"):
            logger.info(
                f"event=ML_TRAINING_COMPLETED | model_version={model_info['model_version']} | "
                f"trade_count={len(trades)} | status=SUCCESS"
            )
        else:
            logger.info(
                f"event=ML_TRAINING_COMPLETED | model_version=None | "
                f"trade_count={len(trades)} | status=NO_IMPROVEMENT"
            )
        
        return runtime
    except Exception as e:
        logger.error(
            f"event=ML_TRAINING_FAILED | reason=exception | error={str(e)} | status=ERROR",
            exc_info=True
        )
        return runtime


def _task_reconciliation(runtime=None):
    """
    Reconcile account state with broker (once per hour).
    
    Can run anytime (not time-restricted).
    """
    logger.info("-" * 80)
    logger.info("RECONCILIATION")
    logger.info("-" * 80)
    
    try:
        if runtime is None:
            runtime = build_paper_trading_runtime()
        
        result = reconcile_runtime(runtime)
        logger.info(
            f"Reconciliation status={result.get('status')} "
            f"safe_mode={result.get('safe_mode')} "
            f"positions={result.get('positions_count')}"
        )
        return runtime
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}", exc_info=True)
        return runtime


def run_daemon():
    """
    Start crypto scheduler daemon (24/7 continuous).
    
    This is the main entry point for production crypto trading.
    """
    logger.info("=" * 80)
    logger.info("CRYPTO DAEMON STARTUP")
    logger.info("=" * 80)
    logger.info(f"Scope: {get_scope()}")
    logger.info(f"Downtime: {CRYPTO_DOWNTIME_START_UTC}-{CRYPTO_DOWNTIME_END_UTC} UTC")
    logger.info(f"Tick interval: {CRYPTO_SCHEDULER_TICK_SECONDS}s")
    logger.info(f"Trading interval: {CRYPTO_TRADING_TICK_INTERVAL_MINUTES} min")
    logger.info("=" * 80)
    
    # Initialize scheduler
    scheduler = CryptoScheduler(
        downtime_start_utc=CRYPTO_DOWNTIME_START_UTC,
        downtime_end_utc=CRYPTO_DOWNTIME_END_UTC,
        loop_interval_seconds=CRYPTO_SCHEDULER_TICK_SECONDS,
    )
    
    # Build persistent runtime (shared across ticks)
    logger.info("Building persistent trading runtime...")
    runtime = build_paper_trading_runtime()
    
    # Optional startup reconciliation
    if CRYPTO_RUN_STARTUP_RECONCILIATION:
        logger.info("Running startup reconciliation...")
        reconcile_runtime(runtime)
    
    # Register tasks
    # Each task closure captures runtime and updates it after execution
    def make_trading_tick():
        nonlocal runtime
        runtime = _task_trading_tick(runtime)
    
    def make_monitor():
        nonlocal runtime
        runtime = _task_monitor(runtime)
    
    def make_ml_training():
        nonlocal runtime
        runtime = _task_ml_training(runtime)
    
    def make_reconciliation():
        nonlocal runtime
        runtime = _task_reconciliation(runtime)
    
    scheduler.register_task(CryptoSchedulerTask(
        name="trading_tick",
        func=make_trading_tick,
        interval_minutes=CRYPTO_TRADING_TICK_INTERVAL_MINUTES,
        allowed_state=TradingState.TRADING,  # Only outside downtime
    ))
    
    scheduler.register_task(CryptoSchedulerTask(
        name="monitor",
        func=make_monitor,
        interval_minutes=15,  # Every 15 minutes
        allowed_state=TradingState.TRADING,  # Anytime, but mainly during trading
    ))
    
    scheduler.register_task(CryptoSchedulerTask(
        name="ml_training",
        func=make_ml_training,
        daily=True,
        allowed_state=TradingState.DOWNTIME,  # Only during downtime
    ))
    
    scheduler.register_task(CryptoSchedulerTask(
        name="reconciliation",
        func=make_reconciliation,
        interval_minutes=60,  # Every 60 minutes
        # No state restriction: can run anytime
    ))
    
    # Run daemon loop
    logger.info("Starting daemon loop (Ctrl+C to stop)...")
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crypto 24/7 daemon with ML downtime window",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run daemon (blocks until Ctrl+C):
  python3 crypto_main.py
  
  # In Docker:
  docker run ... python crypto_main.py
        """
    )
    parser.add_argument(
        "--help-config",
        action="store_true",
        help="Show configuration environment variables"
    )
    
    args = parser.parse_args()
    
    if args.help_config:
        print("""
CRYPTO DAEMON CONFIGURATION
===========================

Environment variables (set via docker run -e):

  CRYPTO_DOWNTIME_START_UTC     Start time of ML downtime (HH:MM UTC)
                                Default: "03:00"
  
  CRYPTO_DOWNTIME_END_UTC       End time of ML downtime (HH:MM UTC)
                                Default: "05:00"
  
  CRYPTO_SCHEDULER_TICK_SECONDS How often scheduler checks tasks (seconds)
                                Default: 60
  
  CRYPTO_TRADING_TICK_INTERVAL_MINUTES How often to run trading pipeline (min)
                                        Default: 1
  
  CRYPTO_RECONCILIATION_INTERVAL_MINUTES  Default: 60
  CRYPTO_RUN_STARTUP_RECONCILIATION       Default: true
  CRYPTO_RUN_HEALTH_CHECK_ON_BOOT         Default: true

EXAMPLE DOCKER COMMAND
======================
docker run \\
  -e CRYPTO_DOWNTIME_START_UTC="03:00" \\
  -e CRYPTO_DOWNTIME_END_UTC="05:00" \\
  -e CRYPTO_SCHEDULER_TICK_SECONDS=60 \\
  -e CRYPTO_TRADING_TICK_INTERVAL_MINUTES=1 \\
  -v /data/artifacts/crypto:/app/persist \\
  trading-app python crypto_main.py
        """)
        sys.exit(0)
    
    run_daemon()
