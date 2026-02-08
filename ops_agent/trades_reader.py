"""
Read actual trade fills from ledger.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class TradesReader:
    """Read actual trade fills from all scopes."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_trades(self, scope: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for a scope."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return []

        trades_path = self.logs_root / scope_dir / "ledger" / "trades.jsonl"

        if not trades_path.exists():
            return []

        try:
            trades = []
            with open(trades_path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        trades.append(data)
                    except Exception as e:
                        logger.debug(f"Error parsing trade: {e}")

            # Return most recent first
            return trades[-limit:] if trades else []
        except Exception as e:
            logger.debug(f"Error reading trades: {e}")
            return []

    def get_trade_count(self, scope: str) -> int:
        """Get total number of trades."""
        return len(self.get_trades(scope, limit=10000))

    def get_trade_summary(self, scope: str) -> Optional[str]:
        """Get summary of recent trades."""
        trades = self.get_trades(scope, limit=10)
        if not trades:
            return None

        lines = []
        for trade in trades:
            symbol = trade.get("symbol", "?")
            qty = trade.get("quantity", 0)
            price = trade.get("price", 0)
            side = trade.get("side", "?").upper()
            timestamp = trade.get("timestamp", "?")
            pnl = trade.get("pnl", 0)

            pnl_str = f"${pnl:+.2f}" if pnl else "N/A"
            lines.append(f"  {side} {qty} {symbol} @ ${price:.2f} - {timestamp} (P&L: {pnl_str})")

        return "\n".join(lines)

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


def get_trades_reader(logs_root: str = "logs") -> TradesReader:
    """Convenience function."""
    return TradesReader(logs_root)
