#!/usr/bin/env python3
"""
Phase F Scheduler: Daily epistemic intelligence runs.

Schedules Phase F job to run daily at 03:00 UTC (overnight).
Runs as a daemon inside the Phase F container.

Pattern: Mirrors governance/scheduler.py but for daily instead of weekly runs.
"""

import schedule
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Callable, Optional

from config.phase_f_settings import (
    PHASE_F_ENABLED,
    PHASE_F_RUN_SCHEDULE_UTC,
    PHASE_F_KILL_SWITCH
)

logger = logging.getLogger(__name__)


class PhaseFScheduler:
    """
    Daily scheduler for Phase F epistemic intelligence runs.

    Runs at 03:00 UTC (overnight) to avoid trading hours.
    Uses state persistence to prevent duplicate runs after container restarts.
    """

    def __init__(
        self,
        job_func: Callable,
        run_time_utc: str = PHASE_F_RUN_SCHEDULE_UTC,
        state_file: Optional[Path] = None
    ):
        """
        Initialize scheduler.

        Args:
            job_func: Callable that executes Phase F pipeline
            run_time_utc: Time in HH:MM format (UTC). Default from config: "03:00"
            state_file: Path to state persistence file. Default: persist/phase_f/crypto/scheduler_state.json
        """
        self.job_func = job_func
        self.run_time_utc = run_time_utc
        self.state_file = state_file or Path("persist/phase_f/crypto/scheduler_state.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._shutdown_requested = False

        logger.info(f"PhaseFScheduler initialized: run_time={run_time_utc}")

    def _load_state(self) -> dict:
        """Load scheduler state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load scheduler state: {e}")
                return {"last_run_date": None}
        return {"last_run_date": None}

    def _save_state(self, state: dict):
        """Save scheduler state to disk."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save scheduler state: {e}")

    def _already_run_today(self) -> bool:
        """Check if job already ran today."""
        state = self._load_state()
        last_run = state.get("last_run_date")
        today = datetime.now(timezone.utc).date().isoformat()
        return last_run == today

    def _run_job_with_state(self):
        """Run job and update state."""
        if self._already_run_today():
            logger.info("Phase F already ran today. Skipping.")
            return

        logger.info("Starting scheduled Phase F run...")
        try:
            self.job_func()

            # Update state
            today = datetime.now(timezone.utc).date().isoformat()
            self._save_state({"last_run_date": today})
            logger.info("Phase F scheduled run completed successfully")

        except Exception as e:
            logger.error(f"Phase F scheduled run failed: {e}", exc_info=True)

    def start(self):
        """Start scheduler daemon (infinite loop)."""
        if PHASE_F_KILL_SWITCH:
            logger.warning("PHASE_F_KILL_SWITCH enabled. Scheduler disabled.")
            return

        if not PHASE_F_ENABLED:
            logger.info("PHASE_F_ENABLED=false. Scheduler disabled.")
            return

        logger.info(f"Phase F Scheduler starting. Daily run at {self.run_time_utc} UTC")
        logger.info("Scheduler running as daemon. Press Ctrl+C to stop.")

        # Schedule daily run at specified time
        schedule.every().day.at(self.run_time_utc).do(self._run_job_with_state)

        # Setup signal handlers for graceful shutdown
        import signal
        signal.signal(signal.SIGTERM, lambda s, f: self._request_shutdown())
        signal.signal(signal.SIGINT, lambda s, f: self._request_shutdown())

        # Main loop: check every minute
        while not self._shutdown_requested:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                time.sleep(60)

        logger.info("Phase F Scheduler stopped")

    def _request_shutdown(self):
        """Request graceful shutdown."""
        logger.info("Shutdown signal received")
        self._shutdown_requested = True


def main():
    """CLI entry point for scheduler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Import job function
    from phase_f.phase_f_job import run_phase_f_job

    scheduler = PhaseFScheduler(job_func=run_phase_f_job)
    scheduler.start()


if __name__ == "__main__":
    main()
