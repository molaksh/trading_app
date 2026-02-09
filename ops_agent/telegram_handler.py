"""
Telegram bot polling and chat validation.
"""

import logging
from typing import Optional, List
import requests
from datetime import datetime

from ops_agent.schemas import TelegramMessage

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Handle Telegram polling and message routing."""

    def __init__(
        self,
        bot_token: str,
        allowed_chat_ids: List[int],
        poll_interval_seconds: int = 5,
    ):
        """
        Initialize Telegram handler.

        Args:
            bot_token: Telegram bot token from @BotFather
            allowed_chat_ids: List of allowed chat IDs (single-user v1)
            poll_interval_seconds: How often to poll Telegram API
        """
        self.bot_token = bot_token
        self.allowed_chat_ids = set(allowed_chat_ids)
        self.poll_interval_seconds = poll_interval_seconds
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.last_update_id = 0

    def get_updates(self) -> List[TelegramMessage]:
        """
        Poll Telegram API for new messages.

        Returns:
            List of valid TelegramMessage objects (chat ID validated)
        """
        try:
            url = f"{self.api_url}/getUpdates"
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 5,
                "allowed_updates": ["message"],
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                logger.error(f"Telegram API error: {data.get('description')}")
                return []

            updates = data.get("result", [])
            messages = []

            for update in updates:
                self.last_update_id = max(self.last_update_id, update.get("update_id", 0))

                message = update.get("message")
                if not message:
                    continue

                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()

                # Validate chat ID (single-user in v1)
                if chat_id not in self.allowed_chat_ids:
                    logger.warning(
                        f"Message from unauthorized chat ID: {chat_id} (text: {text[:50]})"
                    )
                    self.send_message(
                        chat_id,
                        "❌ You are not authorized to use this bot.",
                    )
                    continue

                if not text:
                    continue

                tg_msg = TelegramMessage(
                    chat_id=chat_id,
                    message_id=message.get("message_id", 0),
                    text=text,
                    sender_id=message.get("from", {}).get("id", 0),
                    timestamp=datetime.utcnow(),
                )
                messages.append(tg_msg)

            return messages

        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram API request error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error processing Telegram updates: {e}")
            return []

    def send_message(self, chat_id: int, text: str, buttons: Optional[List[List[dict]]] = None) -> bool:
        """
        Send a message to a chat with optional keyboard buttons.

        Args:
            chat_id: Telegram chat ID
            text: Message text (plain text, no Markdown)
            buttons: Optional list of button rows. Each row is a list of {"text": "...", "callback_data": "..."} dicts

        Returns:
            True if successful
        """
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
            }

            # Add inline keyboard if buttons provided
            if buttons:
                payload["reply_markup"] = {
                    "inline_keyboard": buttons
                }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                logger.error(f"Send message error: {data.get('description')}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    def is_authorized(self, chat_id: int) -> bool:
        """Check if chat ID is authorized."""
        return chat_id in self.allowed_chat_ids


def parse_allowed_chat_ids(csv_string: str) -> List[int]:
    """
    Parse comma-separated chat IDs from environment variable.

    Example:
        "123456789,987654321" -> [123456789, 987654321]
    """
    if not csv_string:
        return []

    ids = []
    for item in csv_string.split(","):
        try:
            ids.append(int(item.strip()))
        except ValueError:
            logger.warning(f"Invalid chat ID: {item}")

    return ids
