"""
Manage TTL-based watches with passive notifications.
"""

import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from ops_agent.schemas import Watch, Intent
from ops_agent.response_generator import ResponseGenerator

logger = logging.getLogger(__name__)


class WatchManager:
    """Manage active watches and send passive notifications."""

    def __init__(self, watches_file: str, logs_root: str):
        """
        Initialize watch manager.

        Args:
            watches_file: Path to active_watches.jsonl (append-only)
            logs_root: Root directory for observability logs
        """
        self.watches_file = Path(watches_file)
        self.logs_root = Path(logs_root)
        self.active_watches: List[Watch] = []
        self._load_watches()

    def _load_watches(self) -> None:
        """Load watches from JSONL, filter expired."""
        if not self.watches_file.exists():
            return

        try:
            now = datetime.utcnow()
            for line in open(self.watches_file):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    watch = Watch(**data)

                    # Keep only non-expired watches
                    if watch.expires_at > now:
                        self.active_watches.append(watch)
                except Exception as e:
                    logger.warning(f"Error parsing watch: {e}")
                    continue

            logger.debug(f"Loaded {len(self.active_watches)} active watches")

        except Exception as e:
            logger.warning(f"Error loading watches: {e}")

    def add_watch(
        self,
        chat_id: int,
        condition: str,
        scope: Optional[str] = None,
        ttl_hours: int = 24,
        one_shot: bool = False,
    ) -> Watch:
        """
        Create and add a new watch.

        Args:
            chat_id: Telegram chat ID
            condition: Watch condition (regime_change, governance_pending, etc.)
            scope: Scope to watch (optional, None = all scopes)
            ttl_hours: Time to live (hours)
            one_shot: Remove after first trigger

        Returns:
            Created Watch object
        """
        watch = Watch(
            watch_id=f"w_{uuid.uuid4().hex[:12]}",
            chat_id=chat_id,
            scope=scope,
            condition=condition,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
            last_state=None,
            one_shot=one_shot,
        )

        self._persist_watch(watch)
        self.active_watches.append(watch)

        logger.info(
            f"Watch created: {watch.watch_id} ({condition}, expires in {ttl_hours}h)"
        )

        return watch

    def _persist_watch(self, watch: Watch) -> None:
        """Append watch to JSONL."""
        try:
            self.watches_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.watches_file, "a") as f:
                f.write(watch.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Error persisting watch: {e}")

    def remove_watch(self, watch_id: str) -> bool:
        """
        Remove watch from active list (soft delete).

        Args:
            watch_id: Watch ID to remove

        Returns:
            True if removed, False if not found
        """
        for watch in list(self.active_watches):
            if watch.watch_id == watch_id:
                self.active_watches.remove(watch)
                logger.info(f"Watch removed: {watch_id}")
                return True
        return False

    def list_watches(self, chat_id: int) -> List[Watch]:
        """
        List all active watches for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            List of active watches for this chat
        """
        return [w for w in self.active_watches if w.chat_id == chat_id]

    def evaluate(self, telegram_handler, response_generator: ResponseGenerator) -> None:
        """
        Evaluate all active watches and send notifications if triggered.

        Args:
            telegram_handler: TelegramHandler for sending messages
            response_generator: ResponseGenerator for generating messages
        """
        now = datetime.utcnow()

        for watch in list(self.active_watches):
            # Check expiration
            if watch.expires_at < now:
                self.active_watches.remove(watch)
                telegram_handler.send_message(
                    watch.chat_id,
                    f"⏱️ Watch expired: {watch.condition}",
                )
                logger.info(f"Watch expired: {watch.watch_id}")
                continue

            # Evaluate condition
            triggered, message = self._evaluate_condition(watch, response_generator)

            if triggered and message:
                telegram_handler.send_message(watch.chat_id, message)
                logger.info(f"Watch triggered: {watch.watch_id} - {watch.condition}")

                if watch.one_shot:
                    self.active_watches.remove(watch)

    def _evaluate_condition(
        self, watch: Watch, response_generator: ResponseGenerator
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate watch condition.

        Args:
            watch: Watch to evaluate
            response_generator: ResponseGenerator for state queries

        Returns:
            (triggered, message) tuple
        """
        try:
            if watch.condition == "regime_change":
                return self._check_regime_change(watch, response_generator)
            elif watch.condition == "governance_pending":
                return self._check_governance_pending(watch)
            elif watch.condition == "no_trades":
                return self._check_no_trades(watch, response_generator)
            elif watch.condition == "pnl_threshold":
                return self._check_pnl_threshold(watch, response_generator)
            elif watch.condition == "any_change":
                return self._check_any_change(watch, response_generator)

        except Exception as e:
            logger.warning(f"Error evaluating watch {watch.watch_id}: {e}")

        return False, None

    def _check_regime_change(
        self, watch: Watch, response_generator: ResponseGenerator
    ) -> Tuple[bool, Optional[str]]:
        """Check for regime change."""
        scopes_to_check = [watch.scope] if watch.scope else [
            "live_crypto",
            "paper_crypto",
            "live_us",
            "paper_us",
        ]

        for scope in scopes_to_check:
            obs = response_generator.obs_reader.get_snapshot(scope)
            if not obs:
                continue

            current_regime = obs.get("regime", "UNKNOWN")
            last_regime = (
                watch.last_state.get("regime") if watch.last_state else None
            )

            if last_regime and current_regime != last_regime:
                # Update last_state for next check
                watch.last_state = {"regime": current_regime}
                return (
                    True,
                    f"🔔 {scope}: Regime change {last_regime} → {current_regime}",
                )

            # Initialize last_state on first check
            if not watch.last_state:
                watch.last_state = {"regime": current_regime}

        return False, None

    def _check_governance_pending(self, watch: Watch) -> Tuple[bool, Optional[str]]:
        """Check for pending governance proposals."""
        try:
            from governance.check_pending_proposals import get_pending_count

            pending = get_pending_count()
            if pending > 0:
                if not watch.last_state or watch.last_state.get("pending", 0) != pending:
                    watch.last_state = {"pending": pending}
                    return True, f"⚠️ {pending} governance proposal(s) pending approval"
        except Exception as e:
            logger.debug(f"Error checking governance: {e}")

        return False, None

    def _check_no_trades(
        self, watch: Watch, response_generator: ResponseGenerator
    ) -> Tuple[bool, Optional[str]]:
        """Check if trading is blocked."""
        scopes_to_check = [watch.scope] if watch.scope else [
            "live_crypto",
            "paper_crypto",
            "live_us",
            "paper_us",
        ]

        for scope in scopes_to_check:
            obs = response_generator.obs_reader.get_snapshot(scope)
            if not obs:
                continue

            if not obs.get("trading_active", True):
                reason = obs.get("blocks", ["unknown"])[0] if obs.get("blocks") else "unknown"
                if not watch.last_state or watch.last_state.get("blocked", False) != True:
                    watch.last_state = {"blocked": True}
                    return True, f"⛔ {scope}: Trading blocked ({reason})"

            # Clear block state if trading active
            if watch.last_state and watch.last_state.get("blocked", False):
                watch.last_state = {"blocked": False}

        return False, None

    def _check_pnl_threshold(
        self, watch: Watch, response_generator: ResponseGenerator
    ) -> Tuple[bool, Optional[str]]:
        """Check if PnL crossed threshold (not yet implemented)."""
        # Placeholder for PnL threshold checking
        return False, None

    def _check_any_change(
        self, watch: Watch, response_generator: ResponseGenerator
    ) -> Tuple[bool, Optional[str]]:
        """Check for any state change."""
        scopes_to_check = [watch.scope] if watch.scope else [
            "live_crypto",
            "paper_crypto",
            "live_us",
            "paper_us",
        ]

        for scope in scopes_to_check:
            obs = response_generator.obs_reader.get_snapshot(scope)
            if not obs:
                continue

            # Compute state hash
            state_hash = hash(
                frozenset(
                    (k, v) for k, v in obs.items() if k in ["regime", "trading_active"]
                )
            )

            if watch.last_state:
                last_hash = watch.last_state.get("state_hash", 0)
                if state_hash != last_hash:
                    watch.last_state = {"state_hash": state_hash}
                    return True, f"🔔 {scope}: State changed"

            if not watch.last_state:
                watch.last_state = {"state_hash": state_hash}

        return False, None
