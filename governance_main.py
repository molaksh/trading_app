#!/usr/bin/env python3
"""
Standalone governance job for Phase C.

Runs independently from trading containers.
Executes 4-agent pipeline and produces non-binding proposals.

Usage:
  python governance_main.py --run-once
  python governance_main.py --dry-run
  python governance_main.py --run-once --dry-run

Scheduled via cron (Sunday 3:15 AM ET / 8:15 AM UTC):
  15 8 * * 0 cd /app && python governance_main.py --run-once >> /var/log/governance.log 2>&1
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

    log_path = Path(log_dir) / "governance_logs"
    log_path.mkdir(parents=True, exist_ok=True)

    # Log file with timestamp
    log_file = log_path / f"governance_{datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')}.log"

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
    logging.getLogger("governance").setLevel(logging.INFO)
    logging.getLogger("governance").addHandler(console_handler)
    logging.getLogger("governance").addHandler(file_handler)

    return logger

logger = setup_logging()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phase C Multi-Agent Constitutional AI Governance Job"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run governance job once and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: read summaries but don't persist artifacts",
    )
    parser.add_argument(
        "--persist-path",
        default="persist",
        help="Base persistence directory (default: persist)",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Phase C: Multi-Agent Constitutional AI Governance")
    logger.info("=" * 70)
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Persist path: {args.persist_path}")

    try:
        # Import here to avoid issues if governance not available
        from governance.crypto_governance_job import run_governance_job

        result = run_governance_job(
            persist_path=args.persist_path,
            dry_run=args.dry_run,
        )

        logger.info("=" * 70)
        logger.info("Governance Job Results")
        logger.info("=" * 70)
        logger.info(f"Success: {result['success']}")
        logger.info(f"Proposal ID: {result['proposal_id']}")
        logger.info(f"Errors: {len(result['errors'])}")

        if result['synthesis']:
            synthesis = result['synthesis']
            logger.info(f"Final Recommendation: {synthesis.get('final_recommendation')}")
            logger.info(f"Confidence: {synthesis.get('confidence'):.1%}")

        if result['errors']:
            logger.warning(f"Errors encountered: {result['errors']}")
            sys.exit(1)

        logger.info("Governance job completed successfully")
        sys.exit(0)

    except ImportError as e:
        logger.error(f"Failed to import governance module: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Governance job failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
