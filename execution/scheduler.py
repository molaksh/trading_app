"""
Long-running scheduler to orchestrate trading tasks for a continuous container.
- Intraday emergency exits and order polling
- Hourly reconciliation/health checks
- Daily entries near close and swing exits after close
- Offline ML training after market close
All tasks run with a shared runtime so pending orders and ledgers persist.

Phase 0: SCOPE-driven, uses MLStateManager for idempotent training.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional, Dict

from config.scheduler_settings import (
    MARKET_TIMEZONE,
    RECONCILIATION_INTERVAL_MINUTES,
    EMERGENCY_EXIT_INTERVAL_MINUTES,
    ORDER_POLL_INTERVAL_MINUTES,
    HEALTH_CHECK_INTERVAL_MINUTES,
    ENTRY_WINDOW_MINUTES_BEFORE_CLOSE,
    SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE,
    SCHEDULER_TICK_SECONDS,
    RUN_STARTUP_RECONCILIATION,
    RUN_HEALTH_CHECK_ON_BOOT,
)
from config.settings import RUN_PAPER_TRADING
from config.scope import get_scope
from config.scope_paths import get_scope_path
from execution.runtime import (
    PaperTradingRuntime,
    build_paper_trading_runtime,
    reconcile_runtime,
)
from ml.ml_state import MLStateManager
from startup.validator import validate_startup

logger = logging.getLogger(__name__)


class SchedulerState:
    """Persist lightweight last-run timestamps across restarts."""

    def __init__(self, path: Path):
        self.path = path
        self.state: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                self.state = json.loads(self.path.read_text())
        except Exception as e:
            logger.warning(f"Could not load scheduler state: {e}")
            self.state = {}

    def last_run(self, key: str) -> Optional[datetime]:
        raw = self.state.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    def last_run_date(self, key: str) -> Optional[datetime.date]:
        last = self.last_run(key)
        return last.date() if last else None

    def update(self, key: str, when: datetime) -> None:
        self.state[key] = when.isoformat()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.state, indent=2))
        except Exception as e:
            logger.warning(f"Failed to persist scheduler state: {e}")


class TradingScheduler:
    def __init__(self, runtime: Optional[PaperTradingRuntime] = None):
        # Phase 0: Validate startup configuration before doing anything
        logger.info("=" * 80)
        logger.info("TRADING SCHEDULER STARTUP (Phase 0)")
        logger.info("=" * 80)
        
        validate_startup()  # Fails fast if config invalid
        
        self.tz = ZoneInfo(MARKET_TIMEZONE)
        self.runtime = runtime or build_paper_trading_runtime()
        scope = get_scope()
        self.scope_paths = self.runtime.scope_paths
        
        # Use scope-aware paths
        self.state = SchedulerState(get_scope_path(scope, "state") / "scheduler_state.json")
        self.tick_seconds = max(15, SCHEDULER_TICK_SECONDS)
        self.observation_only = os.getenv("OBSERVATION_ONLY", "false").lower() == "true"
        if self.observation_only:
            logger.warning("OBSERVATION_ONLY enabled: trading cycles will be skipped")
        
        # Cache for market clock (fallback when API fails)
        self._last_good_clock: Optional[Dict[str, Optional[datetime]]] = None
        self._clock_fetch_failures = 0
        
        # ML state manager for idempotent training
        self._ml_state_manager = MLStateManager()
        self._ml_orchestrator = None

        # Optional boot tasks
        now = self._now()
        if RUN_STARTUP_RECONCILIATION:
            self._run_reconciliation(now, force=True)
        if RUN_HEALTH_CHECK_ON_BOOT:
            self._run_health_check(now)
        
        # PHASE 0: Load active ML model (DO NOT TRAIN at startup)
        self._load_ml_model()
    
    def _get_ml_orchestrator(self):
        """Lazy-load ML orchestrator."""
        if self._ml_orchestrator is None:
            try:
                from ml.dataset_builder import DatasetBuilder
                from ml.offline_trainer import OfflineTrainer
                from ml.offline_evaluator import OfflineEvaluator
                from ml.model_registry import ModelRegistry
                from ml.ml_orchestrator import OfflineMLOrchestrator
                
                scope = get_scope()
                dataset_dir = get_scope_path(scope, "features")
                model_dir = get_scope_path(scope, "models")
                
                builder = DatasetBuilder(dataset_dir, self.runtime.trade_ledger)
                trainer = OfflineTrainer(model_dir, builder)
                evaluator = OfflineEvaluator(builder, trainer)
                registry = ModelRegistry(model_dir)
                
                self._ml_orchestrator = OfflineMLOrchestrator(builder, trainer, evaluator, registry)
            except Exception as e:
                logger.warning(f"Could not initialize ML orchestrator: {e}")
                return None
        
        return self._ml_orchestrator
    
    def _load_ml_model(self) -> None:
        """Load active ML model at startup (DO NOT TRAIN)."""
        try:
            active_version = self._ml_state_manager.get_active_model_version()
            if active_version:
                logger.info(f"Loading active ML model version: {active_version}")
                # Load the model into the executor if available
                if self.runtime.executor.ml_trainer:
                    self.runtime.executor.ml_trainer.load_model(active_version)
            else:
                logger.info("No active ML model - using rules-based trading only")
        except Exception as e:
            logger.warning(f"Could not load active ML model: {e}")
    
    def _run_offline_ml_cycle(self, now: datetime) -> None:
        """
        Run offline ML training after market close (once per day).
        
        CRITICAL: Only runs in PAPER environment. FORBIDDEN in live.
        
        Phase 0: Idempotent training via MLStateManager
        - Compute dataset fingerprint
        - Skip training if data unchanged (idempotent)
        - Update state and promote model on success
        
        Raises:
            EnvironmentViolationError: If called from live environment
        """
        # CRITICAL SAFETY CHECK: Block ML training in live containers
        from runtime.environment_guard import get_environment_guard
        guard = get_environment_guard()
        guard.assert_paper_only("Offline ML training cycle")
        
        if not self._should_run_interval("offline_ml", now, 24*60):  # Once per day
            return
        
        try:
            ml = self._get_ml_orchestrator()
            if not ml:
                logger.debug("ML orchestrator not available")
                return
            
            # Get current dataset
            trades = self.runtime.trade_ledger.get_all_trades()
            if not trades:
                logger.info("No trades yet - skipping ML training")
                return
            
            # Check if we should train (idempotent via fingerprinting)
            from ml.ml_state import compute_dataset_fingerprint
            current_fingerprint = compute_dataset_fingerprint(trades)
            
            if not self._ml_state_manager.should_train(current_fingerprint):
                logger.info(f"Dataset unchanged (fingerprint: {current_fingerprint[:8]}...) - skipping training")
                return
            
            logger.info("Running offline ML training cycle...")
            model_version = ml.run_offline_ml_cycle()
            
            if model_version:
                # Update state with new training metadata
                run_id = f"run_{now.isoformat()}"
                self._ml_state_manager.update_dataset_fingerprint(current_fingerprint, run_id)
                self._ml_state_manager.promote_model(model_version)
                logger.info(f"Promoted model version: {model_version}")
                
                self.state.update("offline_ml", now)
            
            # Run phase readiness evaluation (recommend-only)
            self._evaluate_phase_readiness(now)
            
        except Exception as e:
            logger.warning(f"Offline ML cycle failed: {e}")
    
    def _evaluate_phase_readiness(self, now: datetime) -> None:
        """
        Evaluate ML phase promotion readiness (recommend-only).
        
        Runs after ML training to provide recommendations.
        NEVER auto-promotes phases.
        """
        try:
            from ml.phase_readiness import PhaseReadinessEvaluator
            
            # Only evaluate if we have live data (otherwise not relevant)
            if not hasattr(self.runtime, 'live_trade_ledger'):
                logger.debug("No live ledger - skipping phase readiness evaluation")
                return
            
            evaluator = PhaseReadinessEvaluator(
                paper_ledger=self.runtime.trade_ledger,
                live_ledger=getattr(self.runtime, 'live_trade_ledger', None)
            )
            
            recommendation = evaluator.evaluate()
            
            if recommendation.should_promote:
                logger.info("")
                logger.info("🔔 PHASE PROMOTION RECOMMENDATION AVAILABLE")
                logger.info(f"   Review: logs/{get_scope()}/state/phase_readiness.json")
                logger.info("")
        except Exception as e:
            logger.debug(f"Phase readiness evaluation skipped: {e}")

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def _to_market_time(self, ts) -> Optional[datetime]:
        if ts is None:
            return None
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc).astimezone(self.tz)
        return ts.astimezone(self.tz)

    def _get_clock(self) -> Dict[str, Optional[datetime]]:
        """Get market clock with retry logic and caching."""
        # Handle mock mode (no client)
        if not self.runtime.broker.client:
            logger.info("Mock mode: using default market clock")
            return {
                "is_open": False,  # Conservative - assume market is closed
                "timestamp": self._now(),
                "next_open": None,
                "next_close": None,
            }
        
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                clock = self.runtime.broker.client.get_clock()
                result = {
                    "is_open": bool(getattr(clock, "is_open", False)),
                    "timestamp": self._to_market_time(getattr(clock, "timestamp", None)),
                    "next_open": self._to_market_time(getattr(clock, "next_open", None)),
                    "next_close": self._to_market_time(getattr(clock, "next_close", None)),
                }
                # Success - cache and reset failure counter
                self._last_good_clock = result
                if self._clock_fetch_failures > 0:
                    logger.info(f"Market clock fetch recovered after {self._clock_fetch_failures} failures")
                self._clock_fetch_failures = 0
                return result
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    # All retries failed
                    self._clock_fetch_failures += 1
                    logger.warning(f"Failed to fetch market clock after {max_retries} attempts: {e}")
                    
                    # Use cached clock if available (but mark market as closed for safety)
                    if self._last_good_clock and self._clock_fetch_failures <= 5:
                        logger.info(f"Using cached clock data (failure #{self._clock_fetch_failures})")
                        # Return cached data but force is_open=False for safety
                        cached = self._last_good_clock.copy()
                        cached["is_open"] = False
                        return cached
                    else:
                        # No cache or too many failures - return safe defaults
                        now = self._now()
                        if self._clock_fetch_failures > 5:
                            logger.error(f"Market clock fetch has failed {self._clock_fetch_failures} times consecutively")
                        return {"is_open": False, "timestamp": now, "next_open": None, "next_close": None}

    def _should_run_interval(self, key: str, now: datetime, minutes: int) -> bool:
        last = self.state.last_run(key)
        return last is None or (now - last) >= timedelta(minutes=minutes)

    def _run_reconciliation(self, now: datetime, force: bool = False) -> None:
        if not force and not self._should_run_interval("reconciliation", now, RECONCILIATION_INTERVAL_MINUTES):
            return
        result = reconcile_runtime(self.runtime)
        logger.info(
            f"Reconciliation status={result.get('status')} safe_mode={result.get('safe_mode')} "
            f"positions={result.get('positions_count')} orders={result.get('open_orders', {}).get('total', 0)}"
        )
        self.state.update("reconciliation", now)

    def _run_monitoring_cycle(self, now: datetime) -> None:
        from main import run_paper_trading

        self.runtime = run_paper_trading(mode="monitor", runtime=self.runtime)
        self.state.update("monitor", now)

    def _run_entry_cycle(self, now: datetime) -> None:
        from main import run_paper_trading

        self.runtime = run_paper_trading(mode="trade", runtime=self.runtime)
        self.state.update("entry", now)

    def _run_swing_exit_cycle(self, now: datetime) -> None:
        # Swing exit evaluation already runs inside monitor cycle; reuse for clarity
        self._run_monitoring_cycle(now)
        self.state.update("swing_exit", now)
    
    def _run_exit_intent_execution(self, now: datetime, clock: Dict) -> None:
        """
        Execute pending exit intents during execution window.
        
        PRODUCTION: Two-phase swing exit system.
        Execution window: SWING_EXIT_EXECUTION_WINDOW_START_MIN to END_MIN after market open.
        """
        from config.settings import (
            SWING_EXIT_TWO_PHASE_ENABLED,
            SWING_EXIT_EXECUTION_WINDOW_START_MIN,
            SWING_EXIT_EXECUTION_WINDOW_END_MIN
        )
        
        if not SWING_EXIT_TWO_PHASE_ENABLED:
            return
        
        # Check if we've already run today
        if self.state.last_run_date("exit_intent_execution") == now.date():
            return
        
        # Check if we're in the execution window
        market_open = clock.get("timestamp")  # Current market time
        if not market_open:
            return
        
        # Calculate time since market open
        next_open = clock.get("next_open")
        if next_open and next_open.date() == now.date():
            # Market just opened today - check if we're in window
            time_since_open = (now - next_open).total_seconds() / 60  # minutes
            
            if SWING_EXIT_EXECUTION_WINDOW_START_MIN <= time_since_open <= SWING_EXIT_EXECUTION_WINDOW_END_MIN:
                logger.info("=" * 80)
                logger.info("EXIT INTENT EXECUTION WINDOW REACHED")
                logger.info(f"Time since open: {time_since_open:.1f} minutes")
                logger.info("=" * 80)
                
                executed_count = self.runtime.executor.execute_pending_exit_intents()
                
                logger.info(f"Executed {executed_count} pending exit intents")
                self.state.update("exit_intent_execution", now)

    def _run_health_check(self, now: datetime) -> None:
        if not self._should_run_interval("health_check", now, HEALTH_CHECK_INTERVAL_MINUTES):
            return
        try:
            status = self.runtime.executor.get_account_status()
            logger.info(
                "HEALTH CHECK | equity=$%.2f buying_power=$%.2f open_positions=%s pending_orders=%s"
                % (
                    status.get("equity", 0),
                    status.get("buying_power", 0),
                    status.get("open_positions", 0),
                    status.get("pending_orders", 0),
                )
            )
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
        self.state.update("health_check", now)

    def _has_pending_orders(self) -> bool:
        return bool(self.runtime.executor.pending_orders)

    def run_forever(self) -> None:
        if not RUN_PAPER_TRADING:
            logger.error("RUN_PAPER_TRADING is False. Scheduler will not start.")
            return

        logger.info("Starting trading scheduler loop")
        logger.info(f"Tick every {self.tick_seconds}s | TZ={MARKET_TIMEZONE}")
        logger.info(
            "Cadence: recon=%s min | emergency=%s min | poll=%s min | entry window <=%s min before close"
            % (
                RECONCILIATION_INTERVAL_MINUTES,
                EMERGENCY_EXIT_INTERVAL_MINUTES,
                ORDER_POLL_INTERVAL_MINUTES,
                ENTRY_WINDOW_MINUTES_BEFORE_CLOSE,
            )
        )

        while True:
            now = self._now()
            clock = self._get_clock()
            
            # Log scheduler heartbeat
            market_status = "OPEN" if clock["is_open"] else "CLOSED"
            next_close_str = clock.get("next_close").strftime("%H:%M") if clock.get("next_close") else "N/A"
            logger.info(f"Scheduler tick | Market: {market_status} | Time: {now.strftime('%H:%M:%S')} | Next close: {next_close_str}")

            self._run_reconciliation(now)

            if self.observation_only:
                self._run_health_check(now)
                time.sleep(self.tick_seconds)
                continue

            # Intraday monitoring/polling
            if clock["is_open"]:
                # PRODUCTION: Execute pending exit intents during execution window
                self._run_exit_intent_execution(now, clock)
                
                if self._should_run_interval("monitor", now, EMERGENCY_EXIT_INTERVAL_MINUTES):
                    self._run_monitoring_cycle(now)

                if self._has_pending_orders() and self._should_run_interval("poll", now, ORDER_POLL_INTERVAL_MINUTES):
                    self._run_monitoring_cycle(now)
                    self.state.update("poll", now)

                # Pre-close entry window
                next_close = clock.get("next_close")
                if next_close:
                    time_to_close = next_close - now
                    if (
                        timedelta(minutes=0) <= time_to_close <= timedelta(minutes=ENTRY_WINDOW_MINUTES_BEFORE_CLOSE)
                        and self.state.last_run_date("entry") != now.date()
                    ):
                        logger.info("Entry window reached. Running trade cycle once for today.")
                        self._run_entry_cycle(now)

            else:
                # After close: run swing exits once per session
                if self.state.last_run_date("swing_exit") != now.date():
                    next_open = clock.get("next_open")
                    if next_open and (next_open.date() != now.date()):
                        cutoff = next_open - timedelta(minutes=SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE)
                        if now < cutoff:
                            logger.info("Post-close swing exit cycle.")
                            self._run_swing_exit_cycle(now)
                
                # After close: run offline ML training once per day (paper only)
                from runtime.environment_guard import TradingEnvironment, get_environment_guard
                guard = get_environment_guard()
                if guard.environment == TradingEnvironment.PAPER:
                    if self.state.last_run_date("offline_ml") != now.date():
                        self._run_offline_ml_cycle(now)

            self._run_health_check(now)

            # Emit daily summary for observability
            try:
                from runtime.observability import get_observability
                get_observability().check_daily_summary()
            except Exception as e:
                logger.error(f"Daily summary check failed: {e}", exc_info=True)

            time.sleep(self.tick_seconds)


if __name__ == "__main__":
    import logging.config
    from pathlib import Path
    
    # Configure logging (stdout + persistent file)
    try:
        scope = get_scope()
        logs_dir = get_scope_path(scope, "logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        scheduler_log_path = logs_dir / "scheduler.log"
    except Exception:
        scheduler_log_path = None
    
    handlers = [logging.StreamHandler()]
    if scheduler_log_path:
        handlers.append(logging.FileHandler(scheduler_log_path))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )
    
    try:
        scheduler = TradingScheduler()
        scheduler.run_forever()
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
    except Exception as e:
        logger.error(f"Scheduler failed: {e}", exc_info=True)
        raise
