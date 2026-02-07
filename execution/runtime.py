"""
Shared runtime assembly for paper trading flows.
Creates broker, risk stack, executor, and log resolver once so long-running
processes (scheduler/containers) can reuse state across tasks.

Phase 0: SCOPE-driven, broker-agnostic, strategy-isolated.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List

from config.settings import START_CAPITAL, RUN_MONITORING
from config.scope import get_scope, Scope
from config.scope_paths import get_scope_paths, get_scope_path
from broker.broker_factory import get_broker_adapter
from broker.adapter import BrokerAdapter  # Abstract base
from broker.trading_executor import TradingExecutor
from broker.execution_logger import ExecutionLogger
from broker.trade_ledger import TradeLedger
from broker.account_reconciliation import AccountReconciler
from broker.crypto_reconciliation import CryptoAccountReconciler
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager
from monitoring.system_guard import SystemGuard
from strategy.exit_evaluator import ExitEvaluator
from strategies.registry import instantiate_strategies_for_scope
from strategies.base import Strategy
from crypto.scope_guard import enforce_crypto_scope_guard
from crypto.universe import CryptoUniverse
from runtime.trade_permission import get_trade_permission

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingRuntime:
    """Phase 0: Scope-aware runtime assembly."""
    scope: Scope
    broker: BrokerAdapter
    risk_manager: RiskManager
    trade_ledger: TradeLedger
    executor: TradingExecutor
    monitor: Optional[SystemGuard]
    exit_evaluator: ExitEvaluator
    strategies: List[Strategy]  # Scope-filtered strategies
    scope_paths: "ScopePathResolver"  # Persistent paths under PERSISTENCE_ROOT/<scope>/


def build_paper_trading_runtime() -> PaperTradingRuntime:
    """
    Assemble runtime dependencies once for reuse across scheduler ticks.
    
    Phase 0: SCOPE-driven assembly
    - Broker selected via BrokerFactory from scope.broker
    - Strategies filtered and instantiated for scope via StrategyRegistry
    - Storage paths resolved via ScopePathResolver (all under PERSISTENCE_ROOT/<scope>/)
    - ML state managed via MLStateManager (idempotent training, model version tracking)
    """
    # Get SCOPE from environment (set at container startup)
    scope = get_scope()
    logger.info(f"Building runtime for SCOPE: {scope}")
    
    # Get scope-aware path resolver
    scope_paths = get_scope_paths(scope)
    logger.info(f"Storage paths: {scope_paths.get_scope_summary()}")
    
    # Select broker via factory (no hardcoded Alpaca)
    broker = get_broker_adapter(scope)
    logger.info(f"Broker: {broker.__class__.__name__}")

    # Crypto scope guardrails (fail fast on contamination)
    enforce_crypto_scope_guard(scope, broker, scope_paths)
    
    # Run Kraken preflight checks for live crypto trading
    if scope.broker.lower() == "kraken" and scope.env.lower() == "live":
        try:
            import os
            dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
            if not dry_run:
                from broker.kraken_preflight import run_preflight_checks
                logger.info("Running Kraken preflight checks...")
                checks = run_preflight_checks(dry_run=False)
                logger.info(f"Preflight checks passed: {checks}")
        except Exception as e:
            logger.error(f"Kraken preflight check failed: {e}")
            raise
    
    # Load scope-filtered strategies
    strategies = instantiate_strategies_for_scope(scope)
    strategy_names = [s.name for s in strategies]
    logger.info(f"Strategies for {scope}: {strategy_names}")
    
    if not strategies:
        raise ValueError(f"No strategies available for scope: {scope}")
    
    # Build risk stack
    portfolio_state = PortfolioState(START_CAPITAL)
    risk_manager = RiskManager(portfolio_state)
    
    # Build trade ledger and execution logger
    trade_ledger = TradeLedger()
    exec_logger = ExecutionLogger(str(get_scope_path(scope, "logs")))
    
    # Optional monitoring
    monitor = SystemGuard() if RUN_MONITORING else None
    
    # Exit evaluator (strategy-specific)
    exit_evaluator = ExitEvaluator(
        swing_config={
            "max_holding_days": 20,
            "profit_target_pct": 0.10,
            "use_trend_invalidation": True,
        },
        emergency_config={
            "max_position_loss_pct": 0.03,
            "atr_multiplier": 4.0,
            "enable_volatility_check": True,
        },
    )
    
    # ML trainer (optional, lazy-loaded by scheduler)
    ml_trainer = None
    try:
        from ml.offline_trainer import OfflineTrainer
        ml_models_dir = get_scope_path(scope, "models")
        ml_trainer = OfflineTrainer(ml_models_dir, None)  # dataset_builder set later
    except Exception as e:
        logger.debug(f"Could not initialize ML trainer: {e}")
    
    # Build paper trading executor
    executor = TradingExecutor(
        broker=broker,
        risk_manager=risk_manager,
        monitor=monitor,
        logger_instance=exec_logger,
        exit_evaluator=exit_evaluator,
        trade_ledger=trade_ledger,
        ml_trainer=ml_trainer,
        ml_risk_threshold=0.5,  # 50% probability threshold
    )

    return PaperTradingRuntime(
        scope=scope,
        broker=broker,
        risk_manager=risk_manager,
        trade_ledger=trade_ledger,
        executor=executor,
        monitor=monitor,
        exit_evaluator=exit_evaluator,
        strategies=strategies,
        scope_paths=scope_paths,
    )

def reconcile_runtime(runtime: PaperTradingRuntime) -> dict:
    """
    Run account reconciliation and push flags into executor.
    
    Phase 0: Uses scope-aware broker from runtime.
    """
    if runtime.scope.mode.lower() == "crypto" or runtime.scope.broker.lower() == "kraken":
        reconciler = CryptoAccountReconciler(runtime.broker, runtime.trade_ledger, runtime.risk_manager)
    else:
        # Get state directory for AlpacaReconciliationEngine (required for alpaca_v2)
        state_dir = runtime.scope_paths.get_state_dir()
        reconciler = AccountReconciler(
            runtime.broker,
            runtime.trade_ledger,
            runtime.risk_manager,
            state_dir=state_dir
        )
    reconciliation_result = reconciler.reconcile_on_startup()
    runtime.executor.safe_mode_enabled = reconciliation_result.get("safe_mode", False)
    runtime.executor.startup_status = reconciliation_result.get("status", "UNKNOWN")
    runtime.executor.external_symbols = reconciler.unreconciled_broker_symbols  # Track unreconciled symbols to block duplicates

    # Runtime reconciliation guard (live only): block trading on mismatch
    if runtime.scope.env.lower() == "live" and runtime.scope.broker.lower() == "kraken":
        permission = get_trade_permission()
        broker_positions = runtime.broker.get_positions()
        broker_symbols = set()
        if isinstance(broker_positions, dict):
            for key, value in broker_positions.items():
                symbol = None
                if isinstance(value, dict):
                    symbol = value.get("symbol") or value.get("pair") or value.get("pairname")
                if symbol is None:
                    symbol = key
                try:
                    symbol = CryptoUniverse().get_canonical_symbol(symbol)
                except Exception:
                    pass
                broker_symbols.add(symbol)
        elif isinstance(broker_positions, list):
            for pos in broker_positions:
                symbol = getattr(pos, "symbol", None)
                if symbol:
                    broker_symbols.add(symbol)

        ledger_symbols = set(getattr(runtime.trade_ledger, "_open_positions", {}).keys())
        external_only = broker_symbols - ledger_symbols
        ledger_only = ledger_symbols - broker_symbols

        if external_only or ledger_only:
            reason = f"external_only={sorted(external_only)} ledger_only={sorted(ledger_only)}"
            permission.set_block("RECONCILIATION_BLOCKED", reason)
        else:
            permission.clear_block("RECONCILIATION_BLOCKED", "broker/ledger match")

    return reconciliation_result
