"""
Shared runtime assembly for paper trading flows.
Creates broker, risk stack, executor, and log resolver once so long-running
processes (scheduler/containers) can reuse state across tasks.
"""

from dataclasses import dataclass
from typing import Optional

from config.settings import START_CAPITAL, RUN_MONITORING
from config.log_paths import LogPathResolver
from broker.alpaca_adapter import AlpacaAdapter
from broker.paper_trading_executor import PaperTradingExecutor
from broker.execution_logger import ExecutionLogger
from broker.trade_ledger import TradeLedger
from broker.account_reconciliation import AccountReconciler
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager
from monitoring.system_guard import SystemGuard
from strategy.exit_evaluator import ExitEvaluator


@dataclass
class PaperTradingRuntime:
    broker: AlpacaAdapter
    risk_manager: RiskManager
    trade_ledger: TradeLedger
    executor: PaperTradingExecutor
    monitor: Optional[SystemGuard]
    exit_evaluator: ExitEvaluator
    log_resolver: LogPathResolver


def build_paper_trading_runtime() -> PaperTradingRuntime:
    """Assemble runtime dependencies once for reuse across scheduler ticks."""
    resolver = LogPathResolver()
    broker = AlpacaAdapter()
    portfolio_state = PortfolioState(START_CAPITAL)
    risk_manager = RiskManager(portfolio_state)
    trade_ledger = TradeLedger()
    monitor = SystemGuard() if RUN_MONITORING else None
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

    exec_logger = ExecutionLogger(str(resolver.get_base_directory()))
    
    # Initialize ML trainer (optional, lazy-loaded by scheduler)
    # We just create an empty trainer placeholder here
    ml_trainer = None
    try:
        from ml.offline_trainer import OfflineTrainer
        ml_model_dir = resolver.get_base_directory() / "ml_models"
        ml_trainer = OfflineTrainer(ml_model_dir, None)  # dataset_builder set later
    except Exception as e:
        logger.debug(f"Could not initialize ML trainer: {e}")
    
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
        broker=broker,
        risk_manager=risk_manager,
        trade_ledger=trade_ledger,
        executor=executor,
        monitor=monitor,
        exit_evaluator=exit_evaluator,
        log_resolver=resolver,
    )


def reconcile_runtime(runtime: PaperTradingRuntime) -> dict:
    """Run account reconciliation and push flags into executor."""
    reconciler = AccountReconciler(runtime.broker, runtime.trade_ledger, runtime.risk_manager)
    reconciliation_result = reconciler.reconcile_on_startup()
    runtime.executor.safe_mode_enabled = reconciliation_result.get("safe_mode", False)
    runtime.executor.startup_status = reconciliation_result.get("status", "UNKNOWN")
    runtime.executor.external_symbols = reconciler.external_symbols  # Track symbols to block duplicates
    return reconciliation_result
