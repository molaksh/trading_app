"""
Append-only event logging for ops agent (minimal persistence).
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from ops_agent.schemas import OpsEvent

logger = logging.getLogger(__name__)


class OpsEventLogger:
    """Append-only event logger."""

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)
        self.events_dir = self.logs_root / "ops_agent"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.events_dir / "ops_events.jsonl"

    def log(self, event: OpsEvent) -> bool:
        """
        Append an event to the append-only log.

        Returns:
            True if successful
        """
        try:
            with open(self.events_file, "a") as f:
                line = event.model_dump_json() + "\n"
                f.write(line)
            return True
        except Exception as e:
            logger.error(f"Error logging event: {e}")
            return False

    def get_recent_events(self, limit: int = 100) -> list[OpsEvent]:
        """Get recent events (last N)."""
        if not self.events_file.exists():
            return []

        events = []
        try:
            with open(self.events_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        event = OpsEvent(**data)
                        events.append(event)
                    except Exception as e:
                        logger.warning(f"Error parsing event: {e}")

            return events[-limit:]
        except Exception as e:
            logger.error(f"Error reading events: {e}")
            return []

    def cleanup_old_watches(self, max_age_days: int = 30) -> int:
        """
        Clean up expired watch records (maintenance).

        Returns:
            Number of records deleted
        """
        # Placeholder for watch cleanup in Phase E v2
        return 0


def get_event_logger(logs_root: str = "logs") -> OpsEventLogger:
    """Convenience function."""
    return OpsEventLogger(logs_root)
