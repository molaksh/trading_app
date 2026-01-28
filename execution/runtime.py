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
from config.scope_paths import get_scope_paths
from broker.broker_factory import get_broker_adapter
from broker.adapter import BrokerAdapter  # Abstract base
from broker.paper_trading_executor import PaperTradingExecutor
from broker.execution_logger import ExecutionLogger
from broker.trade_ledger import TradeLedger
from broker.account_reconciliation import AccountReconciler
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager
from monitoring.system_guard import SystemGuard
from strategy.exit_evaluator import ExitEvaluator
from strategies.registry import instantiate_strategies_for_scope
from strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingRuntime:
    """Phase 0: Scope-aware runtime assembly."""
    scope: Scope
    broker: BrokerAdapter
    risk_manager: RiskManager
    trade_ledger: TradeLedger
    executor: PaperTradingExecutor
    monitor: Optional[SystemGuard]
    exit_evaluator: ExitEvaluator
    strategies: List[Strategy]  # Scope-filtered strategies
    scope_paths: "ScopePathResolver"  # Persistent paths under BASE_DIR/<scope>/


def build_paper_trading_runtime() -> PaperTradingRuntime:
    """
    Assemble runtime dependencies once for reuse across scheduler ticks.
    
    Phase 0: SCOPE-driven assembly
    - Broker selected via BrokerFactory from scope.broker
    - Strategies filtered and instantiated for scope via StrategyRegistry
    - Storage paths resolved via ScopePathResolver (all under BASE_DIR/<scope>/)
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
    exec_logger = ExecutionLogger(str(scope_paths.get_logs_dir()))
    
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
        ml_models_dir = scope_paths.get_models_dir()
        ml_trainer = OfflineTrainer(ml_models_dir, None)  # dataset_builder set later
    except Exception as e:
        logger.debug(f"Could not initialize ML trainer: {e}")
    
    # Build paper trading executor
    executor = PaperTradingExecutor(
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
    reconciler = AccountReconciler(runtime.broker, runtime.trade_ledger, runtime.risk_manager)
    reconciliation_result = reconciler.reconcile_on_startup()
    runtime.executor.safe_mode_enabled = reconciliation_result.get("safe_mode", False)
    runtime.executor.startup_status = reconciliation_result.get("status", "UNKNOWN")
    runtime.executor.external_symbols = reconciler.external_symbols  # Track symbols to block duplicates
    return reconciliation_result
