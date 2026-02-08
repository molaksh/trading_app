"""
Read open positions and holdings from persisted state.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class PositionsReader:
    """Read open positions and holdings from all scopes."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_open_positions(self, scope: str) -> Optional[Dict[str, Any]]:
        """Get open positions for a scope."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return None

        # Try state directory first (most recent)
        positions_path = self.logs_root / scope_dir / "state" / "open_positions.json"

        if not positions_path.exists():
            # Fall back to ledger directory
            positions_path = self.logs_root / scope_dir / "ledger" / "open_positions.json"

        if not positions_path.exists():
            return None

        try:
            with open(positions_path) as f:
                data = json.load(f)
                return data if data else None
        except Exception as e:
            logger.debug(f"Error reading positions: {e}")
            return None

    def get_position_count(self, scope: str) -> int:
        """Get number of open positions."""
        positions = self.get_open_positions(scope)
        if not positions:
            return 0
        return len(positions)

    def get_position_summary(self, scope: str) -> Optional[str]:
        """Get human-readable position summary."""
        positions = self.get_open_positions(scope)
        if not positions:
            return None

        # Format positions for display
        lines = []
        total_value = 0.0
        total_cost = 0.0

        for symbol, position in positions.items():
            qty = position.get("quantity", 0)
            entry = position.get("entry_price", 0)
            current = position.get("current_price", 0)
            value = qty * current
            cost = qty * entry
            pnl = value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            lines.append(
                f"  {symbol}: {qty} shares @ ${entry:.2f} (now ${current:.2f}, "
                f"value: ${value:.2f}, P&L: ${pnl:.2f} ({pnl_pct:+.1f}%))"
            )

            total_value += value
            total_cost += cost

        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        summary = "\n".join(lines)
        summary += f"\n  Total: ${total_value:.2f} (Cost: ${total_cost:.2f}, P&L: ${total_pnl:.2f} ({total_pnl_pct:+.1f}%))"

        return summary

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get positions across all scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
        ]

        results = {}
        for scope in all_scopes:
            positions = self.get_open_positions(scope)
            if positions:
                results[scope] = positions

        return results

    def _normalize_scope(self, scope: str) -> Optional[str]:
        """Normalize scope name."""
        scope_lower = scope.lower()

        if scope_lower in self.SCOPE_TO_DIR:
            return self.SCOPE_TO_DIR[scope_lower]

        # Abbreviated forms
        scope_map = {
            "live_crypto": "live_kraken_crypto_global",
            "paper_crypto": "paper_kraken_crypto_global",
            "live_us": "live_alpaca_swing_us",
            "paper_us": "paper_alpaca_swing_us",
        }

        return scope_map.get(scope_lower)


def get_positions_reader(logs_root: str = "logs") -> PositionsReader:
    """Convenience function."""
    return PositionsReader(logs_root)
