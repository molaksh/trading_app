"""
Read error logs from execution and system logs.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ErrorsReader:
    """Read errors from all scopes."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_errors(self, scope: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent errors for a scope."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return []

        errors = []

        # Try errors.jsonl
        errors_path = self.logs_root / scope_dir / "logs" / "errors.jsonl"
        if errors_path.exists():
            try:
                with open(errors_path) as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            errors.append(data)
                        except Exception as e:
                            logger.debug(f"Error parsing error log: {e}")
            except Exception as e:
                logger.debug(f"Error reading errors.jsonl: {e}")

        # Return most recent first
        return errors[-limit:] if errors else []

    def get_error_count(self, scope: str) -> int:
        """Get total number of errors."""
        return len(self.get_errors(scope, limit=10000))

    def get_error_summary(self, scope: str) -> Optional[str]:
        """Get summary of recent errors."""
        errors = self.get_errors(scope, limit=5)
        if not errors:
            return None

        lines = []
        for error in errors:
            timestamp = error.get("timestamp", "?")
            error_type = error.get("error_type", "ERROR")
            message = error.get("message", "Unknown error")[:80]
            lines.append(f"  [{error_type}] {timestamp}: {message}")

        return "\n".join(lines)

    def has_errors(self, scope: str) -> bool:
        """Check if scope has any errors."""
        return self.get_error_count(scope) > 0

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


def get_errors_reader(logs_root: str = "logs") -> ErrorsReader:
    """Convenience function."""
    return ErrorsReader(logs_root)
