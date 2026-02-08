"""
Read ML model state.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MLReader:
    """Read ML model state from all scopes."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_ml_state(self, scope: str) -> Optional[Dict[str, Any]]:
        """Get ML state for a scope."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return None

        ml_path = self.logs_root / scope_dir / "state" / "ml_state.json"

        if not ml_path.exists():
            return None

        try:
            with open(ml_path) as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Error reading ML state: {e}")
            return None

    def get_ml_status(self, scope: str) -> Optional[str]:
        """Get human-readable ML status."""
        state = self.get_ml_state(scope)
        if not state:
            return None

        # Format ML state
        current_version = state.get("current_model_version", "unknown")
        last_training = state.get("last_training_time")
        dataset_fp = state.get("current_dataset_fingerprint", "")[:8]

        lines = [
            f"  Model version: {current_version}",
            f"  Dataset: {dataset_fp}...",
        ]

        if last_training:
            lines.append(f"  Last training: {last_training}")

        promoted_version = state.get("promoted_model_version")
        if promoted_version:
            lines.append(f"  Promoted: {promoted_version}")

        return "\n".join(lines)

    def get_model_version(self, scope: str) -> Optional[str]:
        """Get current model version."""
        state = self.get_ml_state(scope)
        if not state:
            return None
        return state.get("current_model_version")

    def _normalize_scope(self, scope: str) -> Optional[str]:
        """Normalize scope name."""
        scope_lower = scope.lower()

        if scope_lower in self.SCOPE_TO_DIR:
            return self.SCOPE_TO_DIR[scope_lower]

        scope_map = {
            "live_crypto": "live_kraken_crypto_global",
            "paper_crypto": "paper_kraken_crypto_global",
            "live_us": "live_alpaca_swing_us",
            "paper_us": "paper_alpaca_swing_us",
        }

        return scope_map.get(scope_lower)


def get_ml_reader(logs_root: str = "logs") -> MLReader:
    """Convenience function."""
    return MLReader(logs_root)
