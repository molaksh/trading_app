"""
Read observability snapshots (read-only, graceful fallback).
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from ops_agent.schemas import ObservabilitySnapshot

logger = logging.getLogger(__name__)


class ObservabilityReader:
    """Read latest observability snapshots for all scopes."""

    SCOPES = [
        "live_kraken_crypto_global",
        "paper_kraken_crypto_global",
        "live_alpaca_swing_us",
        "paper_alpaca_swing_us",
    ]

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_snapshot(self, scope: str) -> Optional[ObservabilitySnapshot]:
        """
        Get latest observability snapshot for a scope.

        Returns None if file missing or unreadable (graceful fallback).
        """
        # Convert scope format: live_kraken_crypto_global -> live_kraken_crypto_global
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return None

        snapshot_path = (
            self.logs_root / scope_dir / "observability" / "latest_snapshot.json"
        )

        try:
            if not snapshot_path.exists():
                logger.debug(f"Snapshot not found: {snapshot_path}")
                return None

            with open(snapshot_path) as f:
                data = json.load(f)

            # Convert to schema
            return ObservabilitySnapshot(
                scope=scope,
                timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                regime=data.get("regime", "UNKNOWN"),
                trading_active=data.get("trading_active", False),
                blocks=data.get("blocks", []),
                recent_trades=data.get("recent_trades", 0),
                daily_pnl=data.get("daily_pnl", 0.0),
                max_drawdown=data.get("max_drawdown", 0.0),
                scan_coverage=data.get("scan_coverage", 0),
                signals_skipped=data.get("signals_skipped", 0),
                trades_executed=data.get("trades_executed", 0),
                data_issues=data.get("data_issues", 0),
            )
        except Exception as e:
            logger.warning(f"Error reading snapshot {snapshot_path}: {e}")
            return None

    def get_all_snapshots(self) -> Dict[str, Optional[ObservabilitySnapshot]]:
        """Get snapshots for all scopes."""
        result = {}
        for scope in self.SCOPES:
            result[scope] = self.get_snapshot(scope)
        return result

    def _normalize_scope(self, scope: str) -> Optional[str]:
        """
        Normalize scope name and return directory name.

        live_crypto -> live_kraken_crypto_global
        paper_crypto -> paper_kraken_crypto_global
        etc.
        """
        scope_lower = scope.lower()

        # Direct match
        if scope_lower in self.SCOPES:
            return scope_lower

        # Abbreviated forms
        scope_map = {
            "live_crypto": "live_kraken_crypto_global",
            "paper_crypto": "paper_kraken_crypto_global",
            "live_us": "live_alpaca_swing_us",
            "paper_us": "paper_alpaca_swing_us",
            "crypto_live": "live_kraken_crypto_global",
            "crypto_paper": "paper_kraken_crypto_global",
            "us_live": "live_alpaca_swing_us",
            "us_paper": "paper_alpaca_swing_us",
        }

        return scope_map.get(scope_lower)

    def infer_scope(self, text: str) -> Optional[str]:
        """Infer scope from natural language."""
        text_lower = text.lower()

        if "live" in text_lower and "crypto" in text_lower:
            return "live_kraken_crypto_global"
        if "paper" in text_lower and "crypto" in text_lower:
            return "paper_kraken_crypto_global"
        if "live" in text_lower and "us" in text_lower:
            return "live_alpaca_swing_us"
        if "paper" in text_lower and "us" in text_lower:
            return "paper_alpaca_swing_us"

        # If only crypto or us mentioned, default to live
        if "crypto" in text_lower:
            return "live_kraken_crypto_global"
        if "us" in text_lower:
            return "live_alpaca_swing_us"

        return None


def get_observability_reader(logs_root: str = "logs") -> ObservabilityReader:
    """Convenience function."""
    return ObservabilityReader(logs_root)
