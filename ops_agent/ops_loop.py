"""
Main ops loop: continuously poll Telegram and handle intents.
"""

import logging
import time
from typing import List

from ops_agent.telegram_handler import TelegramHandler
from ops_agent.intent_parser import parse_telegram_message
from ops_agent.response_generator import ResponseGenerator
from ops_agent.schemas import TelegramMessage, OpsEvent
from ops_agent.persistence import OpsEventLogger

logger = logging.getLogger(__name__)


class OpsLoop:
    """Main operational loop for the ops agent."""

    def __init__(
        self,
        telegram_handler: TelegramHandler,
        response_generator: ResponseGenerator,
        event_logger: OpsEventLogger,
        poll_interval_seconds: int = 5,
    ):
        self.telegram = telegram_handler
        self.generator = response_generator
        self.event_logger = event_logger
        self.poll_interval = poll_interval_seconds

    def run(self) -> None:
        """Run the ops loop indefinitely."""
        logger.info("Starting ops loop")
        logger.info(
            f"Polling Telegram every {self.poll_interval} seconds..."
        )

        while True:
            try:
                self._tick()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Ops loop stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in ops loop: {e}", exc_info=True)
                time.sleep(self.poll_interval)

    def _tick(self) -> None:
        """Single tick of the ops loop."""
        # Poll Telegram
        messages = self.telegram.get_updates()
        if not messages:
            return

        # Process each message
        for msg in messages:
            self._handle_message(msg)

    def _handle_message(self, msg: TelegramMessage) -> None:
        """Handle a single Telegram message."""
        logger.debug(f"Handling message from {msg.chat_id}: {msg.text[:50]}")

        try:
            # 1. Parse intent
            intent = parse_telegram_message(msg.text)
            self.event_logger.log(
                OpsEvent(
                    timestamp=msg.timestamp,
                    event_type="INTENT_PARSED",
                    chat_id=msg.chat_id,
                    intent=intent.intent_type,
                    scope=intent.scope,
                    details={"text": msg.text, "confidence": intent.confidence},
                )
            )

            # 2. Generate response
            response = self.generator.generate_response(intent)
            logger.info(f"Generated response for {intent.intent_type}: {response[:100]}")

            # 3. Send response
            success = self.telegram.send_message(msg.chat_id, response)
            self.event_logger.log(
                OpsEvent(
                    timestamp=msg.timestamp,
                    event_type="INTENT_EXECUTED",
                    chat_id=msg.chat_id,
                    intent=intent.intent_type,
                    scope=intent.scope,
                    details={"success": success, "response_length": len(response)},
                )
            )

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            self.telegram.send_message(
                msg.chat_id,
                "❌ Error processing your request. Check logs.",
            )


def run_ops_loop(
    telegram_handler: TelegramHandler,
    response_generator: ResponseGenerator,
    event_logger: OpsEventLogger,
) -> None:
    """Convenience function to start the ops loop."""
    loop = OpsLoop(telegram_handler, response_generator, event_logger)
    loop.run()
