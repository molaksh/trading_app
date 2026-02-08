#!/usr/bin/env python3
"""
Governance Job Scheduler (runs inside container 24/7)

Schedules governance job to run at specific time.
Runs as a daemon inside the governance container.
"""

import schedule
import time
import logging
from datetime import datetime
from governance.crypto_governance_job import run_governance_job

logger = logging.getLogger(__name__)


class GovernanceScheduler:
    """Schedule governance job inside container."""

    def __init__(self, run_time: str = "08:15"):
        """
        Args:
            run_time: Time to run in HH:MM format (UTC). Default: 08:15 (3:15 AM ET)
        """
        self.run_time = run_time
        schedule.every().sunday.at(self.run_time).do(self.run_job)

    def run_job(self):
        """Execute governance job."""
        logger.info(f"[{datetime.utcnow()}] Governance job triggered")
        try:
            result = run_governance_job(dry_run=False)
            logger.info(f"Governance job completed: {result}")
        except Exception as e:
            logger.error(f"Governance job failed: {e}", exc_info=True)

    def start(self):
        """Start scheduler daemon (runs until stopped)."""
        logger.info(f"Governance scheduler started")
        logger.info(f"Running job every Sunday at {self.run_time} UTC (3:15 AM ET)")
        logger.info("Scheduler will run indefinitely. Press Ctrl+C to stop.")

        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                logger.info("Scheduler stopped")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                time.sleep(60)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    scheduler = GovernanceScheduler(run_time="08:15")  # 8:15 AM UTC = 3:15 AM ET
    scheduler.start()


if __name__ == "__main__":
    main()
