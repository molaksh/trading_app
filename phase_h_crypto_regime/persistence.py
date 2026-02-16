"""
Phase H Persistence: Append-only JSONL and state files for crypto regime autonomy.

Files:
- regime_autonomy.jsonl  -- Main cycle log (append-only)
- run_state.json         -- Mutable state (current regime, flip history, fail-safe state)
- asset_scores.jsonl     -- Per-asset scoring history (append-only)
- fail_safe_events.jsonl -- Fail-safe trigger log (append-only)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PhaseHPersistence:
    """Append-only persistence for Phase H crypto regime autonomy."""

    def __init__(self, scope: str):
        self.scope = scope
        self.root = Path(f"persist/phase_h/{scope}/crypto")
        self.root.mkdir(parents=True, exist_ok=True)

        self.regime_autonomy_path = self.root / "regime_autonomy.jsonl"
        self.run_state_path = self.root / "run_state.json"
        self.asset_scores_path = self.root / "asset_scores.jsonl"
        self.fail_safe_events_path = self.root / "fail_safe_events.jsonl"

        logger.info("PhaseHPersistence initialized: root=%s", self.root)

    def append_cycle_log(self, record: Dict[str, Any]) -> None:
        """Append a cycle record to regime_autonomy.jsonl (append-only)."""
        try:
            with open(self.regime_autonomy_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            logger.debug("Appended cycle log: timestamp=%s", record.get("timestamp"))
        except IOError as e:
            logger.error("Failed to append cycle log: %s", e, exc_info=True)
            raise

    def append_asset_scores(self, records: List[Dict[str, Any]]) -> None:
        """Append per-asset score records (append-only)."""
        try:
            with open(self.asset_scores_path, "a") as f:
                for rec in records:
                    f.write(json.dumps(rec, default=str) + "\n")
            logger.debug("Appended %d asset score records", len(records))
        except IOError as e:
            logger.error("Failed to append asset scores: %s", e, exc_info=True)
            raise

    def append_fail_safe_event(self, record: Dict[str, Any]) -> None:
        """Append a fail-safe event record (append-only)."""
        try:
            with open(self.fail_safe_events_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            logger.debug("Appended fail-safe event: %s", record.get("event"))
        except IOError as e:
            logger.error("Failed to append fail-safe event: %s", e, exc_info=True)
            raise

    def load_run_state(self) -> Dict[str, Any]:
        """Load mutable run state, or return default if not found."""
        if not self.run_state_path.exists():
            return self._default_run_state()
        try:
            with open(self.run_state_path, "r") as f:
                state = json.load(f)
            logger.debug("Loaded run state: regime=%s", state.get("current_regime"))
            return state
        except Exception as e:
            logger.error("Failed to load run state: %s", e, exc_info=True)
            return self._default_run_state()

    def save_run_state(self, state: Dict[str, Any]) -> None:
        """Save mutable run state (overwrites)."""
        try:
            tmp_path = self.run_state_path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
            tmp_path.replace(self.run_state_path)
            logger.debug("Saved run state: regime=%s", state.get("current_regime"))
        except IOError as e:
            logger.error("Failed to save run state: %s", e, exc_info=True)
            raise

    @staticmethod
    def _default_run_state() -> Dict[str, Any]:
        """Return default run state for fresh starts."""
        return {
            "current_regime": "NEUTRAL",
            "current_regime_since": None,
            "last_stable_regime": "NEUTRAL",
            "macro_confidence": 0.5,
            "last_cycle_timestamp": None,
            "flip_history": [],
            "fail_safe_state": {
                "circuit_breaker_active": False,
                "circuit_breaker_until": None,
                "shock_mode_active": False,
                "shock_mode_until": None,
                "revert_lock_active": False,
                "revert_lock_until": None,
            },
            "regime_transitions": [],
        }
