"""
Crypto scheduler: 24/7 daemon with daily ML downtime window.

Orchestrates:
- Continuous trading loop outside downtime (configurable cadence, e.g., 60s)
- ML training/validation during downtime (paper: train; live: validate/shadow-eval)
- Persistent state so daily tasks don't rerun after restart
- Graceful shutdown with final state write

CRITICAL: This is crypto-only. Zero contamination with swing scheduler.
State file must be under crypto root, never under swing paths.
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Callable, Tuple

from config.scope import get_scope
from config.scope_paths import get_scope_path
from crypto.scheduling import DowntimeScheduler, TradingState
from runtime.observability import get_observability
from crypto.scheduling.state import CryptoSchedulerState

logger = logging.getLogger(__name__)


class CryptoSchedulerTask:
    """Definition of a crypto scheduler task."""
    
    def __init__(
        self,
        name: str,
        func: Callable,
        interval_minutes: Optional[int] = None,
        daily: bool = False,
        run_at_utc: Optional[str] = None,
        run_window_minutes: int = 5,
        allowed_state: TradingState = TradingState.TRADING,
    ):
        """
        Define a task.
        
        Args:
            name: Task name (e.g., "trading_tick", "ml_training")
            func: Callable that executes the task
            interval_minutes: Run every N minutes (None = run always, if allowed)
            daily: If True, run once per day (overrides interval_minutes)
            run_at_utc: Optional HH:MM UTC time to run daily tasks within a window
            run_window_minutes: Allowed minutes after run_at_utc to execute
            allowed_state: TradingState.TRADING or DOWNTIME (or use allow_both)
        """
        self.name = name
        self.func = func
        self.interval_minutes = interval_minutes
        self.daily = daily
        self.run_at_utc = run_at_utc
        self.run_window_minutes = max(1, int(run_window_minutes))
        self.allowed_state = allowed_state
    
    def should_run(
        self,
        state_mgr: CryptoSchedulerState,
        now: datetime,
        current_trading_state: TradingState,
    ) -> Tuple[bool, str]:
        """
        Determine if task should run now.
        
        Returns:
            (should_run: bool, reason: str)
        """
        # Check trading state
        if self.allowed_state == TradingState.TRADING and current_trading_state == TradingState.DOWNTIME:
            return False, f"not_allowed_in_downtime"
        if self.allowed_state == TradingState.DOWNTIME and current_trading_state == TradingState.TRADING:
            return False, f"only_allowed_in_downtime"
        
        # Check if enough time has passed
        if self.daily:
            if not state_mgr.should_run_daily(self.name, now):
                return False, f"already_ran_today"
            if self.run_at_utc:
                try:
                    hour_str, minute_str = self.run_at_utc.split(":")
                    target = now.replace(
                        hour=int(hour_str),
                        minute=int(minute_str),
                        second=0,
                        microsecond=0,
                    )
                    window_end = target + timedelta(minutes=self.run_window_minutes)
                    if now < target:
                        return False, "before_run_window"
                    if now > window_end:
                        return False, "after_run_window"
                except Exception:
                    return False, "invalid_run_at_utc"
        elif self.interval_minutes is not None:
            if not state_mgr.should_run_interval(self.name, now, self.interval_minutes):
                return False, f"interval_not_met"
        
        return True, "due"
    
    def __repr__(self) -> str:
        return f"CryptoSchedulerTask({self.name})"


class CryptoScheduler:
    """24/7 crypto trading scheduler with daily ML downtime."""
    
    def __init__(
        self,
        downtime_start_utc: str = "03:00",
        downtime_end_utc: str = "05:00",
        loop_interval_seconds: int = 60,
    ):
        """
        Initialize crypto scheduler.
        
        Args:
            downtime_start_utc: UTC start time for downtime (HH:MM)
            downtime_end_utc: UTC end time for downtime (HH:MM)
            loop_interval_seconds: Sleep between scheduler ticks (seconds)
        """
        logger.info("=" * 80)
        logger.info("CRYPTO SCHEDULER STARTUP")
        logger.info("=" * 80)
        
        # Downtime window
        self.downtime = DowntimeScheduler(downtime_start_utc, downtime_end_utc)
        self.loop_interval_seconds = max(1, loop_interval_seconds)
        
        # Load crypto-only state
        scope = get_scope()
        state_dir = get_scope_path(scope, "state")
        state_path = state_dir / "crypto_scheduler_state.json"
        
        logger.info(f"Scope: {scope}")
        logger.info(f"State file: {state_path}")
        
        self.state = CryptoSchedulerState(state_path)
        
        # Task registry
        self.tasks: Dict[str, CryptoSchedulerTask] = {}
        
        # Shutdown flag
        self._shutdown_requested = False
        self._setup_signal_handlers()
        
        logger.info(f"Scheduler initialized with {len(self.tasks)} tasks")
        logger.info(f"Downtime: {downtime_start_utc}-{downtime_end_utc} UTC")
        logger.info(f"Loop tick: {self.loop_interval_seconds}s")
        logger.info("=" * 80)
    
    def _setup_signal_handlers(self) -> None:
        """Setup graceful shutdown on SIGTERM/SIGINT."""
        def handle_shutdown(signum, frame):
            logger.info(f"Signal {signum} received. Graceful shutdown...")
            self._shutdown_requested = True
        
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
    
    def register_task(self, task: CryptoSchedulerTask) -> None:
        """
        Register a task with the scheduler.
        
        Args:
            task: CryptoSchedulerTask instance
        """
        if task.name in self.tasks:
            logger.warning(f"Task '{task.name}' already registered. Overwriting.")
        self.tasks[task.name] = task
        logger.debug(f"Registered task: {task.name}")
    
    def run_forever(self) -> None:
        """
        Run scheduler loop forever (until shutdown signal).
        
        Loop:
        1. Check current trading state (trading vs downtime)
        2. For each task, check if it should run
        3. Execute due tasks
        4. Log status
        5. Sleep until next tick
        """
        logger.info("Starting scheduler loop...")
        
        loop_count = 0
        
        while not self._shutdown_requested:
            loop_count += 1
            now = datetime.now(timezone.utc)
            trading_state = self.downtime.get_current_state(now)
            
            # Log heartbeat
            state_label = "DOWNTIME (ML)" if trading_state == TradingState.DOWNTIME else "TRADING"
            logger.info(
                f"Tick {loop_count} | Time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC | "
                f"State: {state_label}"
            )

            # Daily summary check (once per UTC day)
            get_observability().check_daily_summary()
            
            # Execute due tasks
            executed_count = 0
            skipped_count = 0
            
            for task_name, task in self.tasks.items():
                should_run, reason = task.should_run(self.state, now, trading_state)
                
                if should_run:
                    try:
                        logger.info(f"  ▶ {task_name} (due: {reason})")
                        task.func()
                        self.state.update(task_name, now)
                        executed_count += 1
                        logger.info(f"  ✓ {task_name} completed")
                    except Exception as e:
                        logger.error(f"  ✗ {task_name} failed: {e}", exc_info=True)
                else:
                    logger.debug(f"  - {task_name} (skip: {reason})")
                    skipped_count += 1
            
            if executed_count > 0:
                logger.info(f"Executed: {executed_count} | Skipped: {skipped_count}")
            
            # Sleep until next tick
            if not self._shutdown_requested:
                time.sleep(self.loop_interval_seconds)
        
        # Graceful shutdown
        logger.info("Shutdown requested. Persisting final state...")
        self.state._persist()
        get_observability().emit_daily_summary(force=True)
        logger.info("Scheduler stopped gracefully")
        sys.exit(0)
    
    def __repr__(self) -> str:
        return (
            f"CryptoScheduler(downtime={self.downtime}, "
            f"tasks={len(self.tasks)}, tick={self.loop_interval_seconds}s)"
        )
