#!/usr/bin/env python3
"""
Phase E: Interactive Ops & Concierge Agent (Main Entry Point)

READ-ONLY, SAFE, BOUNDED agent for Telegram-based ops inquiries.

Usage:
  python ops_main.py

Environment variables:
  TELEGRAM_BOT_TOKEN: Telegram bot token from @BotFather
  TELEGRAM_ALLOWED_CHAT_IDS: Comma-separated list of allowed chat IDs
  PERSISTENCE_ROOT: Where to store logs (default: logs/)
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for Phase E ops agent."""
    logger.info("=" * 70)
    logger.info("Phase E: Interactive Ops & Concierge Agent")
    logger.info("=" * 70)

    # 1. Load environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_chat_ids_str = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    persistence_root = os.getenv("PERSISTENCE_ROOT", "persist")
    logs_root = os.getenv("LOGS_ROOT", "logs")  # Separate from persist

    if not bot_token:
        logger.error(
            "ERROR: TELEGRAM_BOT_TOKEN environment variable not set.\n"
            "Get a token from @BotFather on Telegram.\n"
            "Then: export TELEGRAM_BOT_TOKEN='your-token-here'"
        )
        sys.exit(1)

    if not allowed_chat_ids_str:
        logger.error(
            "ERROR: TELEGRAM_ALLOWED_CHAT_IDS environment variable not set.\n"
            "Set allowed chat IDs: export TELEGRAM_ALLOWED_CHAT_IDS='123456789,987654321'"
        )
        sys.exit(1)

    # 2. Parse allowed chat IDs
    from ops_agent.telegram_handler import parse_allowed_chat_ids

    allowed_chat_ids = parse_allowed_chat_ids(allowed_chat_ids_str)
    if not allowed_chat_ids:
        logger.error("ERROR: No valid chat IDs in TELEGRAM_ALLOWED_CHAT_IDS")
        sys.exit(1)

    logger.info(f"Allowed chat IDs: {allowed_chat_ids}")

    # 3. Initialize components
    from ops_agent.telegram_handler import TelegramHandler
    from ops_agent.response_generator import ResponseGenerator
    from ops_agent.persistence import OpsEventLogger
    from ops_agent.ops_loop import run_ops_loop

    telegram = TelegramHandler(bot_token, allowed_chat_ids)
    generator = ResponseGenerator(logs_root=logs_root)  # Use logs directory, not persist
    event_logger = OpsEventLogger(logs_root=persistence_root)

    logger.info("✓ Components initialized")
    logger.info("✓ Telegram connection configured")
    logger.info("✓ Event logging ready")
    logger.info("=" * 70)

    # 4. Start ops loop
    try:
        logger.info("Starting ops loop (polling Telegram every 5 seconds)...")
        run_ops_loop(telegram, generator, event_logger)
    except KeyboardInterrupt:
        logger.info("Ops agent stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
