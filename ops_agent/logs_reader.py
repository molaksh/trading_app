"""
Read all persisted logs: Docker logs, AI calls, scheduler state, trades.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class LogsReader:
    """Read Docker logs, AI advisor calls, scheduler state, and more."""

    SCOPE_TO_DIR = {
        "live_kraken_crypto_global": "live_kraken_crypto_global",
        "paper_kraken_crypto_global": "paper_kraken_crypto_global",
        "live_alpaca_swing_us": "live_alpaca_swing_us",
        "paper_alpaca_swing_us": "paper_alpaca_swing_us",
        "governance": "governance_logs",
    }

    def __init__(self, logs_root: str = "logs"):
        self.logs_root = Path(logs_root)

    def get_latest_ai_ranking(self, scope: str) -> Optional[Dict[str, Any]]:
        """Get latest AI advisor ranking call."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return None

        ai_calls_path = self.logs_root / scope_dir / "logs" / "ai_advisor_calls.jsonl"
        if not ai_calls_path.exists():
            return None

        try:
            with open(ai_calls_path) as f:
                last_line = None
                for line in f:
                    if line.strip():
                        last_line = line

                if last_line:
                    data = json.loads(last_line)
                    return {
                        "timestamp": data.get("ts"),
                        "top_3": data.get("ranked_symbols", [])[:3],
                        "reasoning": data.get("reasoning", ""),
                    }
        except Exception as e:
            logger.debug(f"Error reading AI ranking: {e}")

        return None

    def get_scheduler_state(self, scope: str) -> Optional[Dict[str, Any]]:
        """Get scheduler state (when jobs last ran)."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return None

        state_path = self.logs_root / scope_dir / "state" / "crypto_scheduler_state.json"
        if not state_path.exists():
            return None

        try:
            with open(state_path) as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Error reading scheduler state: {e}")

        return None

    def get_recent_docker_logs(self, scope: str, lines: int = 50) -> List[str]:
        """Get recent Docker container logs (tail N lines)."""
        scope_dir = self._normalize_scope(scope)
        if not scope_dir:
            return []

        try:
            # Governance logs are in a different structure
            if scope_dir == "governance_logs":
                logs_dir = self.logs_root / scope_dir
                pattern = "governance_*.log"
            else:
                logs_dir = self.logs_root / scope_dir / "logs"
                pattern = "docker_*.log"

            if not logs_dir.exists():
                return []

            # Find the latest log file
            log_files = sorted(logs_dir.glob(pattern), reverse=True)
            if not log_files:
                return []

            latest_log = log_files[0]
            all_lines = []

            with open(latest_log) as f:
                for line in f:
                    if line.strip():
                        all_lines.append(line.strip())

            # Return last N lines
            return all_lines[-lines:] if all_lines else []

        except Exception as e:
            logger.debug(f"Error reading Docker logs: {e}")

        return []

    def get_recent_errors(self, scope: str, lines: int = 10) -> List[str]:
        """Get recent error/warning lines from Docker logs."""
        all_logs = self.get_recent_docker_logs(scope, lines=200)

        errors = []
        for line in all_logs:
            if any(keyword in line.lower() for keyword in ["error", "exception", "failed", "warning", "traceback"]):
                errors.append(line)

        return errors[-lines:] if errors else []

    def job_is_stale(self, scope: str, job_name: str, max_age_seconds: int = 3600) -> bool:
        """Check if a scheduler job is stale (hasn't run recently)."""
        state = self.get_scheduler_state(scope)
        if not state or job_name not in state:
            return True

        try:
            last_run = datetime.fromisoformat(state[job_name])
            age = (datetime.utcnow() - last_run).total_seconds()
            return age > max_age_seconds
        except Exception:
            return True

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


def get_logs_reader(logs_root: str = "logs") -> LogsReader:
    """Convenience function."""
    return LogsReader(logs_root)
