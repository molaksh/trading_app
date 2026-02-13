"""
Phase G Persistence: Append-only JSONL and state files for universe governance.

Files:
- decisions.jsonl    — Full governance decision records (append-only)
- active_universe.json — Current active universe (overwritten each cycle)
- cooldowns.json     — Removal cooldown registry (overwritten each cycle)
- scoring_history.jsonl — Per-symbol scores each cycle (append-only)
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class UniverseGovernancePersistence:
    """Append-only persistence for Phase G universe governance."""

    def __init__(self, scope: str):
        self.scope = scope
        self.root = Path(f"persist/{scope}/universe")
        self.root.mkdir(parents=True, exist_ok=True)

        self.decisions_path = self.root / "decisions.jsonl"
        self.active_universe_path = self.root / "active_universe.json"
        self.cooldowns_path = self.root / "cooldowns.json"
        self.scoring_history_path = self.root / "scoring_history.jsonl"

        logger.info("UniverseGovernancePersistence initialized: root=%s", self.root)

    def append_decision(self, decision_dict: Dict[str, Any]) -> None:
        """Append a governance decision record (append-only)."""
        try:
            with open(self.decisions_path, "a") as f:
                f.write(json.dumps(decision_dict, default=str) + "\n")
            logger.debug("Appended governance decision: run_id=%s", decision_dict.get("run_id"))
        except IOError as e:
            logger.error("Failed to append governance decision: %s", e, exc_info=True)
            raise

    def write_active_universe(self, symbols: List[str]) -> None:
        """Write current active universe (overwrites)."""
        try:
            with open(self.active_universe_path, "w") as f:
                json.dump({"symbols": symbols}, f, indent=2)
            logger.info("Wrote active universe: %d symbols", len(symbols))
        except IOError as e:
            logger.error("Failed to write active universe: %s", e, exc_info=True)
            raise

    def load_active_universe(self) -> Optional[List[str]]:
        """Load current active universe, or None if not set."""
        if not self.active_universe_path.exists():
            return None
        try:
            with open(self.active_universe_path, "r") as f:
                data = json.load(f)
            symbols = data.get("symbols", [])
            if symbols:
                logger.debug("Loaded active universe: %d symbols", len(symbols))
            return symbols if symbols else None
        except Exception as e:
            logger.error("Failed to load active universe: %s", e, exc_info=True)
            return None

    def load_cooldowns(self) -> Dict[str, str]:
        """Load cooldown registry: symbol -> removal ISO date."""
        if not self.cooldowns_path.exists():
            return {}
        try:
            with open(self.cooldowns_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load cooldowns: %s", e, exc_info=True)
            return {}

    def save_cooldowns(self, cooldowns: Dict[str, str]) -> None:
        """Save cooldown registry (overwrites)."""
        try:
            with open(self.cooldowns_path, "w") as f:
                json.dump(cooldowns, f, indent=2)
        except IOError as e:
            logger.error("Failed to save cooldowns: %s", e, exc_info=True)
            raise

    def append_scores(self, scores: List[Dict[str, Any]]) -> None:
        """Append scored candidates to scoring history (append-only)."""
        try:
            with open(self.scoring_history_path, "a") as f:
                for score_dict in scores:
                    f.write(json.dumps(score_dict, default=str) + "\n")
            logger.debug("Appended %d score records", len(scores))
        except IOError as e:
            logger.error("Failed to append scores: %s", e, exc_info=True)
            raise
