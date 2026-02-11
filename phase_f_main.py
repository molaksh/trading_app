#!/usr/bin/env python3
"""
Phase F: Epistemic Market Intelligence
Main entry point for scheduled runs.

Usage (ONE-TIME):
  python phase_f_main.py --run-once        # Run once and exit

Usage (DAEMON - Inside Container):
  python phase_f_main.py --daemon          # Run scheduler 24/7 (runs daily at 03:00 UTC)
  python phase_f_main.py --daemon --time 03:00  # Custom time

Deployment:
  - Container should run: python phase_f_main.py --daemon
  - Container runs 24/7 inside Docker
  - Scheduler handles the daily triggering (no cron needed)
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Configure logging (console + file)
def setup_logging(log_dir: str = None) -> logging.Logger:
    """Set up logging to console and file."""
    if log_dir is None:
        log_dir = os.getenv("PERSISTENCE_ROOT", "persist")

    log_path = Path(log_dir) / "phase_f" / "crypto" / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

    # Log file with timestamp
    log_file = log_path / f"phase_f_{datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')}.log"

    # Configure root logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Also configure other loggers
    logging.getLogger("phase_f").setLevel(logging.INFO)
    logging.getLogger("phase_f").addHandler(console_handler)
    logging.getLogger("phase_f").addHandler(file_handler)

    return logger


logger = setup_logging()


def run_phase_f_once():
    """Execute Phase F pipeline once."""
    logger.info("Starting Phase F (run-once mode)")

    from phase_f.phase_f_job import run_phase_f_job

    success = run_phase_f_job(scope="crypto")

    if success:
        logger.info("Phase F run completed successfully")
        return 0
    else:
        logger.error("Phase F run failed")
        return 1


def run_daemon(run_time: str = "03:00"):
    """Run Phase F scheduler daemon (infinite loop)."""
    logger.info("Starting Phase F scheduler daemon")

    from phase_f.scheduler import PhaseFScheduler
    from phase_f.phase_f_job import run_phase_f_job
    from config.phase_f_settings import PHASE_F_KILL_SWITCH, PHASE_F_ENABLED

    if PHASE_F_KILL_SWITCH:
        logger.error("PHASE_F_KILL_SWITCH enabled. Daemon aborted.")
        return 1

    if not PHASE_F_ENABLED:
        logger.warning("PHASE_F_ENABLED=false. Daemon will not schedule runs.")

    scheduler = PhaseFScheduler(
        job_func=run_phase_f_job,
        run_time_utc=run_time
    )

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Daemon interrupted")
        return 0

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phase F: Epistemic Market Intelligence"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Execute single run and exit (testing/manual mode)"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as daemon with scheduler (production mode, runs daily at configured time)"
    )
    parser.add_argument(
        "--time",
        default="03:00",
        help="Daemon run time in HH:MM format (UTC). Default: 03:00"
    )

    args = parser.parse_args()

    if args.run_once:
        return run_phase_f_once()
    elif args.daemon:
        return run_daemon(run_time=args.time)
    else:
        logger.error("Must specify --daemon or --run-once")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
