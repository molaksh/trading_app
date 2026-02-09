"""
Track regime duration across scopes using append-only regime history.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

from ops_agent.schemas import RegimeEvent

logger = logging.getLogger(__name__)


class DurationTracker:
    """Track regime changes and calculate durations per scope."""

    def __init__(self, history_file: str):
        """
        Initialize duration tracker.

        Args:
            history_file: Path to regime_history.jsonl (append-only)
        """
        self.history_file = Path(history_file)
        # current_regimes: {scope: (regime_name, start_timestamp)}
        self.current_regimes: Dict[str, Tuple[str, datetime]] = {}
        self._load_current_state()

    def _load_current_state(self) -> None:
        """Load most recent regime per scope from history file."""
        if not self.history_file.exists():
            return

        try:
            # Read entire file and track most recent event per scope
            scope_latest: Dict[str, RegimeEvent] = {}

            with open(self.history_file) as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        event = RegimeEvent(**data)
                        scope_latest[event.scope] = event
                    except Exception as e:
                        logger.warning(f"Error parsing regime event: {e}")
                        continue

            # Populate current_regimes from latest events
            for scope, event in scope_latest.items():
                self.current_regimes[scope] = (event.regime, event.timestamp)

            logger.debug(f"Loaded regime state for {len(self.current_regimes)} scopes")

        except Exception as e:
            logger.warning(f"Error loading regime history: {e}")

    def update(self, scope: str, current_regime: str) -> Optional[RegimeEvent]:
        """
        Update regime for a scope, logging change if detected.

        Args:
            scope: Scope name (e.g., "live_crypto")
            current_regime: Current regime (e.g., "RISK_ON")

        Returns:
            RegimeEvent if regime changed, None otherwise
        """
        last_regime, last_timestamp = self.current_regimes.get(
            scope, (None, datetime.utcnow())
        )

        # No change
        if current_regime == last_regime:
            return None

        # Regime changed
        duration_seconds = None
        if last_regime:
            duration_seconds = int((datetime.utcnow() - last_timestamp).total_seconds())

        event = RegimeEvent(
            timestamp=datetime.utcnow(),
            scope=scope,
            regime=current_regime,
            previous_regime=last_regime,
            duration_seconds=duration_seconds,
        )

        # Update in-memory state
        self.current_regimes[scope] = (current_regime, event.timestamp)

        # Persist to JSONL
        self._persist_event(event)

        logger.info(f"Regime change {scope}: {last_regime} → {current_regime} (lasted {duration_seconds}s)")

        return event

    def _persist_event(self, event: RegimeEvent) -> None:
        """Append event to history file."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "a") as f:
                f.write(event.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Error persisting regime event: {e}")

    def get_duration(self, scope: str) -> Optional[int]:
        """
        Get current regime duration in seconds.

        Args:
            scope: Scope name

        Returns:
            Duration in seconds, or None if scope unknown
        """
        if scope not in self.current_regimes:
            return None

        regime, start_time = self.current_regimes[scope]
        return int((datetime.utcnow() - start_time).total_seconds())

    def get_duration_formatted(self, scope: str) -> str:
        """
        Get human-readable duration string.

        Args:
            scope: Scope name

        Returns:
            Formatted duration (e.g., "4h 12m") or "unknown"
        """
        seconds = self.get_duration(scope)
        if seconds is None:
            return "unknown"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def get_current_regime(self, scope: str) -> Optional[str]:
        """Get current regime for a scope."""
        if scope not in self.current_regimes:
            return None
        return self.current_regimes[scope][0]

    def sync_with_snapshot(self, scope: str, current_regime: str) -> Optional[RegimeEvent]:
        """
        Sync duration tracker with observability snapshot.

        This is safe to call whenever we have current regime data.
        If regime matches, no change. If different, logs change.

        Args:
            scope: Scope name
            current_regime: Current regime from snapshot

        Returns:
            RegimeEvent if regime changed, None otherwise
        """
        return self.update(scope, current_regime)
