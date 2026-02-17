"""
Phase I Persistence: Append-only JSONL and state files for strategy observatory.

Files:
- signals.jsonl             -- Every signal recorded (append-only)
- performance_snapshots.jsonl -- Hourly performance scores (append-only)
- anomalies.jsonl           -- Detected anomalies (append-only)
- run_state.json            -- Mutable state (last run timestamp, counters)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PhaseIPersistence:
    """Append-only persistence for Phase I strategy observatory."""

    def __init__(self, scope: str):
        self.scope = scope
        self.root = Path(f"persist/phase_i/{scope}/observatory")
        self.root.mkdir(parents=True, exist_ok=True)

        self.signals_path = self.root / "signals.jsonl"
        self.performance_path = self.root / "performance_snapshots.jsonl"
        self.anomalies_path = self.root / "anomalies.jsonl"
        self.run_state_path = self.root / "run_state.json"

        logger.info("PhaseIPersistence initialized: root=%s", self.root)

    def append_signals(self, records: List[Dict[str, Any]]) -> None:
        """Append signal records to signals.jsonl (append-only, buffered)."""
        if not records:
            return
        try:
            with open(self.signals_path, "a") as f:
                for rec in records:
                    f.write(json.dumps(rec, default=str) + "\n")
            logger.debug("Appended %d signal records", len(records))
        except IOError as e:
            logger.error("Failed to append signals: %s", e, exc_info=True)

    def append_performance_snapshot(self, record: Dict[str, Any]) -> None:
        """Append a performance snapshot (append-only)."""
        try:
            with open(self.performance_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            logger.debug("Appended performance snapshot")
        except IOError as e:
            logger.error("Failed to append performance snapshot: %s", e, exc_info=True)

    def append_anomaly(self, record: Dict[str, Any]) -> None:
        """Append an anomaly record (append-only)."""
        try:
            with open(self.anomalies_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            logger.debug("Appended anomaly: %s", record.get("anomaly_type"))
        except IOError as e:
            logger.error("Failed to append anomaly: %s", e, exc_info=True)

    def load_recent_signals(self, max_lines: int = 5000) -> List[Dict[str, Any]]:
        """Load recent signal records (tail of file)."""
        if not self.signals_path.exists():
            return []
        try:
            records = []
            with open(self.signals_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            # Return only the most recent records
            return records[-max_lines:]
        except Exception as e:
            logger.error("Failed to load signals: %s", e, exc_info=True)
            return []

    def load_recent_anomalies(self, max_lines: int = 500) -> List[Dict[str, Any]]:
        """Load recent anomaly records."""
        if not self.anomalies_path.exists():
            return []
        try:
            records = []
            with open(self.anomalies_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            return records[-max_lines:]
        except Exception as e:
            logger.error("Failed to load anomalies: %s", e, exc_info=True)
            return []

    def load_run_state(self) -> Dict[str, Any]:
        """Load mutable run state, or return default if not found."""
        if not self.run_state_path.exists():
            return self._default_run_state()
        try:
            with open(self.run_state_path, "r") as f:
                state = json.load(f)
            logger.debug("Loaded run state: last_run=%s", state.get("last_observatory_run"))
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
            logger.debug("Saved run state")
        except IOError as e:
            logger.error("Failed to save run state: %s", e, exc_info=True)

    def load_trades_from_ledger(self) -> List[Dict[str, Any]]:
        """
        Load completed trades from the main trade ledger.

        Tries scope-aware path first (persist/{scope}/ledger/trades.jsonl),
        falls back gracefully if PERSISTENCE_ROOT is not set.
        """
        trades_path = None
        try:
            from config.scope_paths import get_scope_path
            from config.scope import get_scope
            scope = get_scope()
            ledger_dir = get_scope_path(scope, "ledger")
            trades_path = ledger_dir / "trades.jsonl"
        except Exception:
            # Fallback: try common path pattern
            trades_path = Path(f"persist/{self.scope}/ledger/trades.jsonl")

        if trades_path is None or not trades_path.exists():
            return []
        try:
            records = []
            with open(trades_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            return records
        except Exception as e:
            logger.error("Failed to load trades from ledger: %s", e, exc_info=True)
            return []

    @staticmethod
    def _default_run_state() -> Dict[str, Any]:
        """Return default run state for fresh starts."""
        return {
            "last_observatory_run": None,
            "total_signals_recorded": 0,
            "total_anomalies_detected": 0,
            "strategy_flat_counters": {},
        }
