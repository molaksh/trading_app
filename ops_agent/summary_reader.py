"""
Read daily summaries from JSONL files (read-only, graceful fallback).
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from ops_agent.schemas import DailySummaryEntry

logger = logging.getLogger(__name__)


class SummaryReader:
    """Read daily summaries from JSONL files."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_latest_summary(self, scope: str) -> Optional[DailySummaryEntry]:
        """Get the most recent daily summary for a scope."""
        entries = self.get_summaries(scope, limit=1)
        return entries[0] if entries else None

    def get_summaries(
        self, scope: str, lookback_days: int = 7, limit: Optional[int] = None
    ) -> List[DailySummaryEntry]:
        """
        Get recent summaries for a scope.

        Args:
            scope: Scope name
            lookback_days: How many days back to look
            limit: Max number of entries to return

        Returns:
            List of DailySummaryEntry, newest first
        """
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return []

        summary_path = self.logs_root / scope_dir / "logs" / "daily_summary.jsonl"

        try:
            if not summary_path.exists():
                logger.debug(f"Summary file not found: {summary_path}")
                return []

            entries = []
            cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

            with open(summary_path) as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        ts = datetime.fromisoformat(
                            data.get("timestamp", datetime.utcnow().isoformat())
                        )

                        if ts < cutoff_date:
                            continue

                        entry = DailySummaryEntry(
                            timestamp=ts,
                            scope=scope,
                            regime=data.get("regime", "UNKNOWN"),
                            trades_executed=data.get("trades_executed", 0),
                            realized_pnl=data.get("realized_pnl", 0.0),
                            max_drawdown=data.get("max_drawdown", 0.0),
                            data_issues=data.get("data_issues", 0),
                        )
                        entries.append(entry)
                    except Exception as e:
                        logger.debug(f"Error parsing summary line: {e}")
                        continue

            # Reverse to get newest first
            entries.reverse()

            if limit:
                entries = entries[:limit]

            return entries

        except Exception as e:
            logger.warning(f"Error reading summaries {summary_path}: {e}")
            return []

    def get_today_stats(self, scope: str) -> Optional[Dict[str, Any]]:
        """Get today's trading statistics."""
        latest = self.get_latest_summary(scope)
        if not latest:
            return None

        return {
            "trades_executed": latest.trades_executed,
            "realized_pnl": latest.realized_pnl,
            "max_drawdown": latest.max_drawdown,
            "regime": latest.regime,
            "data_issues": latest.data_issues,
        }

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


def get_summary_reader(logs_root: str = "logs") -> SummaryReader:
    """Convenience function."""
    return SummaryReader(logs_root)
