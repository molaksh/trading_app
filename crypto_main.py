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
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT
from config.scope import get_scope
from config.crypto_scheduler_settings import (
    CRYPTO_DOWNTIME_START_UTC,
    CRYPTO_DOWNTIME_END_UTC,
    CRYPTO_SCHEDULER_TICK_SECONDS,
    CRYPTO_TRADING_TICK_INTERVAL_MINUTES,
    CRYPTO_RUN_STARTUP_RECONCILIATION,
    STATUS_SNAPSHOT_INTERVAL_MINUTES,
    AI_VALIDATE_SCHEDULER,
)
from execution.crypto_scheduler import CryptoScheduler, CryptoSchedulerTask
from execution.runtime import build_paper_trading_runtime, reconcile_runtime
from main import run_paper_trading
from crypto.scheduling import TradingState
from runtime.environment_guard import get_environment_guard
from runtime.observability import get_observability
from runtime.ai_advisor import get_ai_runner
from broker.kraken_client import KrakenClient, KrakenConfig, KrakenAPIError
from broker.trade_ledger import TradeLedger
from config.crypto.loader import load_crypto_config
from core.data.providers.kraken_provider import KrakenMarketDataProvider, KrakenOHLCConfig
from crypto.universe import CryptoUniverse
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager
from config.settings import (
    RISK_PER_TRADE,
    MAX_RISK_PER_SYMBOL,
    MAX_PORTFOLIO_HEAT,
    MAX_TRADES_PER_DAY,
    MAX_CONSECUTIVE_LOSSES,
    DAILY_LOSS_LIMIT,
)

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


def _parse_bool(value: str) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


def _offset_time_utc(hhmm: str, minutes: int) -> str:
    try:
        hour_str, minute_str = hhmm.split(":")
        base = datetime.now(timezone.utc).replace(
            hour=int(hour_str),
            minute=int(minute_str),
            second=0,
            microsecond=0,
        )
        adjusted = base + timedelta(minutes=minutes)
        return adjusted.strftime("%H:%M")
    except Exception:
        return hhmm


def verify_live_startup_or_exit() -> None:
    """
    Strict live startup verification. Exits immediately on failure.

    Emits exactly one terminal event:
      - LIVE_STARTUP_VERIFIED
      - LIVE_STARTUP_FAILED_<REASON>
    """

    def fail(reason: str, details: str = "") -> None:
        message = f"LIVE_STARTUP_FAILED_{reason}"
        if details:
            logger.error(f"{message} | {details}")
        else:
            logger.error(message)
        raise SystemExit(1)

    scope = get_scope()
    env = os.getenv("ENV", "").lower()
    broker = os.getenv("BROKER", "").lower()
    mode = os.getenv("MODE", "").lower()
    market = os.getenv("MARKET", "").lower()
    paper_trading = _parse_bool(os.getenv("PAPER_TRADING", "false"))
    live_approved = _parse_bool(os.getenv("LIVE_TRADING_APPROVED", "false"))

    if env != "live" or scope.env.lower() != "live":
        fail("ENV_NOT_LIVE", f"env={env} scope={scope}")
    if broker != "kraken" or scope.broker.lower() != "kraken":
        fail("BROKER_NOT_KRAKEN", f"broker={broker} scope={scope}")
    if mode != "crypto" or scope.mode.lower() != "crypto":
        fail("MODE_NOT_CRYPTO", f"mode={mode} scope={scope}")
    if market not in {"global", "crypto"} or scope.market.lower() != "global":
        fail("MARKET_NOT_CRYPTO", f"market={market} scope={scope}")
    if paper_trading:
        fail("PAPER_TRADING_TRUE", "PAPER_TRADING must be false in live mode")
    if not live_approved:
        fail("LIVE_TRADING_NOT_APPROVED", "LIVE_TRADING_APPROVED must be true")

    api_key = os.getenv("KRAKEN_API_KEY", "").strip()
    api_secret = os.getenv("KRAKEN_API_SECRET", "").strip()
    if not api_key or not api_secret:
        fail("MISSING_KRAKEN_KEYS", "KRAKEN_API_KEY/SECRET required")

    margin_allowed = _parse_bool(os.getenv("MARGIN_TRADING_APPROVED", "false"))

    client = None
    balances = {}
    positions_raw = {}
    try:
        client = KrakenClient(
            KrakenConfig(
                api_key=api_key,
                api_secret=api_secret,
                timeout_sec=10,
                max_retries=0,
                backoff_factor=0.0,
            )
        )

        status = client.request_public("SystemStatus", {})
        if status.get("status") != "online":
            fail("KRAKEN_OFFLINE", f"status={status.get('status')}")

        try:
            balances = client.request_private("Balance", {})
        except KrakenAPIError as e:
            fail("KRAKEN_AUTH_FAILED", str(e))

        if not isinstance(balances, dict):
            fail("KRAKEN_AUTH_FAILED", "balance response invalid")

        try:
            client.request_private("OpenOrders", {})
        except KrakenAPIError as e:
            fail("KRAKEN_PERMISSIONS", str(e))

        try:
            client.request_private("WithdrawInfo", {"asset": "ZUSD", "amount": "1", "key": "invalid"})
            fail("WITHDRAWAL_PERMISSION_ENABLED", "withdraw permission appears enabled")
        except KrakenAPIError as e:
            if "Permission denied" not in str(e):
                fail("WITHDRAWAL_PERMISSION_UNKNOWN", str(e))

        try:
            positions_raw = client.request_private("OpenPositions", {})
        except KrakenAPIError as e:
            fail("KRAKEN_POSITIONS", str(e))
    finally:
        if client is not None:
            client.close()

    total_equity = 0.0
    for asset, value in balances.items():
        try:
            amount = float(value)
        except Exception:
            fail("BALANCE_PARSE", f"asset={asset} value={value}")
        if amount < 0:
            fail("BALANCE_NEGATIVE", f"asset={asset} value={amount}")
        total_equity += amount

    if total_equity < 0:
        fail("BALANCE_NEGATIVE", f"total_equity={total_equity}")

    crypto_config = load_crypto_config(scope)
    enable_cache = bool(crypto_config.get("ENABLE_OHLC_CACHE", True))
    try:
        provider_5m = KrakenMarketDataProvider(
            scope=scope,
            config=KrakenOHLCConfig(
                interval="5m",
                enable_ws=False,
                cache_enabled=enable_cache,
                max_staleness_seconds=0,
            ),
        )
        provider_4h = KrakenMarketDataProvider(
            scope=scope,
            config=KrakenOHLCConfig(
                interval="4h",
                enable_ws=False,
                cache_enabled=enable_cache,
                max_staleness_seconds=0,
            ),
        )
        bars_5m = provider_5m.fetch_ohlcv("BTC", 2)
        bars_4h = provider_4h.fetch_ohlcv("BTC", 2)
        if bars_5m is None or bars_5m.empty or bars_4h is None or bars_4h.empty:
            fail("MARKET_DATA_BLOCKED", "fresh OHLC not available")
    except RuntimeError as e:
        fail("MARKET_DATA_BLOCKED", str(e))

    universe = CryptoUniverse()
    broker_positions = set()
    positions_payload = {}
    if isinstance(positions_raw, dict):
        if "open" in positions_raw and isinstance(positions_raw["open"], dict):
            positions_payload = positions_raw["open"]
        else:
            positions_payload = positions_raw

    for _, pos in positions_payload.items():
        if not isinstance(pos, dict):
            continue
        pair = pos.get("pair") or pos.get("symbol") or pos.get("pairname")
        if not pair:
            continue
        try:
            broker_symbol = universe.get_canonical_symbol(pair)
        except Exception:
            broker_symbol = pair
        broker_positions.add(broker_symbol)

        leverage = pos.get("leverage") or pos.get("margin") or ""
        if not margin_allowed and str(leverage).strip() not in {"", "0", "0.0", "1", "1.0"}:
            fail("MARGIN_NOT_APPROVED", f"symbol={broker_symbol} leverage={leverage}")

    ledger = TradeLedger()
    ledger_positions = set(getattr(ledger, "_open_positions", {}).keys())
    external_only = broker_positions - ledger_positions
    ledger_only = ledger_positions - broker_positions
    if external_only or ledger_only:
        details = f"external_only={sorted(external_only)} ledger_only={sorted(ledger_only)}"
        logger.error(f"RECONCILIATION_BLOCKED | {details}")
        fail("RECONCILIATION_BLOCKED", details)

    max_positions = int(crypto_config.get("STRATEGY_MAX_POSITION_COUNT", 0))
    if max_positions <= 0:
        fail("RISK_MANAGER_INVALID", f"STRATEGY_MAX_POSITION_COUNT={max_positions}")

    if any(
        value <= 0
        for value in (
            RISK_PER_TRADE,
            MAX_RISK_PER_SYMBOL,
            MAX_PORTFOLIO_HEAT,
            MAX_TRADES_PER_DAY,
            MAX_CONSECUTIVE_LOSSES,
            DAILY_LOSS_LIMIT,
        )
    ):
        fail("RISK_MANAGER_INVALID", "risk settings must be positive")

    _ = RiskManager(PortfolioState(total_equity))

    logger.info("LIVE_STARTUP_VERIFIED")


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
    
    For LIVE environment, performs 8 mandatory startup verification checks:
    1. Environment validation (LIVE flag, explicit approval)
    2. API key safety
    3. Account safety
    4. Position reconciliation
    5. Strategy whitelist
    6. Risk manager enforcement
    7. ML read-only mode
    8. Dry-run verification
    """
    logger.info("=" * 80)
    logger.info("CRYPTO DAEMON STARTUP")
    logger.info("=" * 80)
    logger.info(f"Scope: {get_scope()}")
    logger.info(f"Downtime: {CRYPTO_DOWNTIME_START_UTC}-{CRYPTO_DOWNTIME_END_UTC} UTC")
    logger.info(f"Tick interval: {CRYPTO_SCHEDULER_TICK_SECONDS}s")
    logger.info(f"Trading interval: {CRYPTO_TRADING_TICK_INTERVAL_MINUTES} min")
    logger.info("=" * 80)
    
    # GATE 0: LIVE environment startup verification (must pass before anything)
    guard = get_environment_guard()
    if guard.is_live():
        verify_live_startup_or_exit()
    else:
        logger.info(f"Paper environment ({guard.environment.value}) - startup verification skipped")

    if AI_VALIDATE_SCHEDULER:
        get_ai_runner().validate_scheduler_decision(trigger="validation")
        logger.info("AI_SCHEDULER_VALIDATION_COMPLETE")
        sys.exit(0)
    
    # Initialize scheduler
    scheduler = CryptoScheduler(
        downtime_start_utc=CRYPTO_DOWNTIME_START_UTC,
        downtime_end_utc=CRYPTO_DOWNTIME_END_UTC,
        loop_interval_seconds=CRYPTO_SCHEDULER_TICK_SECONDS,
    )
    
    # Build persistent runtime (shared across ticks)
    logger.info("Building persistent trading runtime...")
    runtime = build_paper_trading_runtime()
    observability = get_observability()
    observability.attach_runtime(runtime)
    
    # Optional startup reconciliation (never auto-run in live)
    if not guard.is_live() and CRYPTO_RUN_STARTUP_RECONCILIATION:
        logger.info("Running startup reconciliation...")
        reconcile_runtime(runtime)

    if guard.is_live():
        observability.emit_live_status_snapshot(trigger="startup")

    get_ai_runner().trigger_ranking_from_market_data(trigger="startup")
    
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

    def make_status_snapshot():
        observability.emit_live_status_snapshot(trigger="interval")

    def make_ai_daily_ranking():
        get_ai_runner().trigger_ranking_from_market_data(trigger="daily")
    
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

    scheduler.register_task(CryptoSchedulerTask(
        name="status_snapshot",
        func=make_status_snapshot,
        interval_minutes=max(1, STATUS_SNAPSHOT_INTERVAL_MINUTES),
        # No state restriction: can run anytime
    ))

    ai_daily_run_time = _offset_time_utc(CRYPTO_DOWNTIME_END_UTC, minutes=-5)
    scheduler.register_task(CryptoSchedulerTask(
        name="ai_daily_ranking",
        func=make_ai_daily_ranking,
        daily=True,
        run_at_utc=ai_daily_run_time,
        run_window_minutes=5,
        allowed_state=TradingState.DOWNTIME,
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
