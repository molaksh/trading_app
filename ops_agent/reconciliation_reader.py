"""
Read reconciliation state.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ReconciliationReader:
    """Read reconciliation state from all scopes."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_reconciliation_state(self, scope: str) -> Optional[Dict[str, Any]]:
        """Get reconciliation state for a scope."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return None

        rec_path = self.logs_root / scope_dir / "state" / "reconciliation_cursor.json"

        if not rec_path.exists():
            return None

        try:
            with open(rec_path) as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Error reading reconciliation state: {e}")
            return None

    def get_reconciliation_status(self, scope: str) -> Optional[str]:
        """Get human-readable reconciliation status."""
        state = self.get_reconciliation_state(scope)
        if not state:
            return None

        # Format reconciliation state
        last_rec_time = state.get("last_reconciliation_time")
        status = state.get("status", "UNKNOWN")
        issues = state.get("issues", [])

        lines = [f"  Status: {status}"]
        if last_rec_time:
            lines.append(f"  Last rec: {last_rec_time}")

        if issues:
            lines.append(f"  Issues: {len(issues)}")
            for issue in issues[:3]:
                lines.append(f"    - {issue}")

        return "\n".join(lines)

    def is_healthy(self, scope: str) -> bool:
        """Check if reconciliation is healthy."""
        state = self.get_reconciliation_state(scope)
        if not state:
            return True  # No data means no issues

        status = state.get("status", "").upper()
        return status not in ["FAILED", "ERROR", "STALE"]

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


def get_reconciliation_reader(logs_root: str = "logs") -> ReconciliationReader:
    """Convenience function."""
    return ReconciliationReader(logs_root)
