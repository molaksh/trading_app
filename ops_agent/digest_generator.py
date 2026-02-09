"""
Generate optional scheduled digest summaries (EOD).
"""

import logging
from datetime import datetime
from typing import Optional

from ops_agent.response_generator import ResponseGenerator

logger = logging.getLogger(__name__)


class DigestGenerator:
    """Generate and send scheduled EOD digest summaries."""

    def __init__(
        self,
        response_generator: ResponseGenerator,
        enabled: bool = False,
        schedule_time_utc: str = "01:00",
        only_if_activity: bool = True,
    ):
        """
        Initialize digest generator.

        Args:
            response_generator: ResponseGenerator for querying state
            enabled: Whether digest generation is enabled
            schedule_time_utc: Schedule time (HH:MM UTC), default 01:00 (9 PM ET)
            only_if_activity: Only send if activity detected
        """
        self.generator = response_generator
        self.enabled = enabled
        self.schedule_time = schedule_time_utc
        self.only_if_activity = only_if_activity
        self.last_sent: Optional[datetime] = None

    def should_send(self) -> bool:
        """
        Check if digest should be sent.

        Returns:
            True if schedule time reached and not already sent today
        """
        if not self.enabled:
            return False

        now = datetime.utcnow()

        # Parse schedule time
        try:
            target_hour, target_minute = map(int, self.schedule_time.split(":"))
        except (ValueError, AttributeError):
            logger.warning(f"Invalid schedule time: {self.schedule_time}")
            return False

        # Check if within scheduled time window (within 5 minutes)
        if now.hour != target_hour or not (
            target_minute <= now.minute < target_minute + 5
        ):
            return False

        # Check if already sent today
        if self.last_sent and self.last_sent.date() == now.date():
            return False

        return True

    def generate_digest(self) -> str:
        """
        Generate EOD digest across all scopes.

        Returns:
            Formatted digest string
        """
        scopes = ["live_crypto", "paper_crypto", "live_us", "paper_us"]

        lines = ["📊 Daily Digest", "═" * 40]

        any_activity = False

        for scope in scopes:
            obs = self.generator.obs_reader.get_snapshot(scope)
            if not obs:
                continue

            regime = obs.get("regime", "UNKNOWN")
            trades = obs.get("recent_trades", 0)
            pnl = obs.get("daily_pnl", 0.0)
            active = obs.get("trading_active", False)

            if trades > 0 or pnl != 0:
                any_activity = True

            status = "🟢" if active else "🔴"
            lines.append(f"{status} {scope}")
            lines.append(f"   Regime: {regime} | Trades: {trades} | PnL: ${pnl:+.2f}")

        if not any_activity and self.only_if_activity:
            return "📊 Daily Digest: No activity today"

        return "\n".join(lines)

    def send_if_due(self, telegram_handler, chat_id: int) -> bool:
        """
        Send digest if scheduled time reached.

        Args:
            telegram_handler: TelegramHandler for sending messages
            chat_id: Telegram chat ID

        Returns:
            True if digest sent, False otherwise
        """
        if not self.should_send():
            return False

        digest = self.generate_digest()
        success = telegram_handler.send_message(chat_id, digest)

        if success:
            self.last_sent = datetime.utcnow()
            logger.info(f"Digest sent to {chat_id}")
            return True

        return False
