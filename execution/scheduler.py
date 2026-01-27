"""
Long-running scheduler to orchestrate trading tasks for a continuous container.
- Intraday emergency exits and order polling
- Hourly reconciliation/health checks
- Daily entries near close and swing exits after close
- Offline ML training after market close
All tasks run with a shared runtime so pending orders and ledgers persist.
"""

import json
import logging
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
from execution.runtime import (
    PaperTradingRuntime,
    build_paper_trading_runtime,
    reconcile_runtime,
)

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
        self.tz = ZoneInfo(MARKET_TIMEZONE)
        self.runtime = runtime or build_paper_trading_runtime()
        self.state = SchedulerState(self.runtime.log_resolver.get_custom_log_path("scheduler_state.json"))
        self.tick_seconds = max(15, SCHEDULER_TICK_SECONDS)
        
        # Cache for market clock (fallback when API fails)
        self._last_good_clock: Optional[Dict[str, Optional[datetime]]] = None
        self._clock_fetch_failures = 0
        
        # Offline ML orchestrator (lazy-loaded)
        self._ml_orchestrator = None

        # Optional boot tasks
        now = self._now()
        if RUN_STARTUP_RECONCILIATION:
            self._run_reconciliation(now, force=True)
        if RUN_HEALTH_CHECK_ON_BOOT:
            self._run_health_check(now)
        
        # Load active ML model if available
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
                
                dataset_dir = self.runtime.log_resolver.get_base_directory() / "ml_datasets"
                model_dir = self.runtime.log_resolver.get_base_directory() / "ml_models"
                
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
        """Load active ML model at startup."""
        ml = self._get_ml_orchestrator()
        if ml:
            ml.maybe_load_active_model()
    
    def _run_offline_ml_cycle(self, now: datetime) -> None:
        """Run offline ML training after market close (once per day)."""
        if not self._should_run_interval("offline_ml", now, 24*60):  # Once per day
            return
        
        try:
            ml = self._get_ml_orchestrator()
            if ml:
                ml.run_offline_ml_cycle()
                self.state.update("offline_ml", now)
        except Exception as e:
            logger.warning(f"Offline ML cycle failed: {e}")

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

            self._run_reconciliation(now)

            # Intraday monitoring/polling
            if clock["is_open"]:
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
                
                # After close: run offline ML training once per day
                if self.state.last_run_date("offline_ml") != now.date():
                    self._run_offline_ml_cycle(now)

            self._run_health_check(now)

            time.sleep(self.tick_seconds)
