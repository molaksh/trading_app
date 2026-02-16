"""
Strategy Signal Tracker (Phase I-A).

Records every signal (LONG, SHORT, FLAT) per strategy/symbol to JSONL.
Buffered writes to minimize I/O impact on the pipeline hot path.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from phase_i_strategy.config import SIGNAL_BUFFER_SIZE
from phase_i_strategy.persistence import PhaseIPersistence

logger = logging.getLogger(__name__)


class StrategySignalTracker:
    """
    Records every strategy signal for observatory analysis.

    Hooks into crypto_pipeline.py after generate_signal().
    Buffers records in memory, flushes to JSONL when buffer is full
    or when explicitly flushed (end of pipeline cycle).
    """

    def __init__(self, persistence: PhaseIPersistence):
        self.persistence = persistence
        self._buffer: List[Dict[str, Any]] = []
        self._buffer_size = SIGNAL_BUFFER_SIZE
        logger.info("StrategySignalTracker initialized (buffer_size=%d)", self._buffer_size)

    def record_signal(
        self,
        strategy_name: str,
        symbol: str,
        intent: str,
        confidence: float,
        reason: str,
        regime: str,
        features: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a single strategy signal.

        Args:
            strategy_name: Name of the strategy (e.g., 'mean_reversion')
            symbol: Trading symbol (e.g., 'BTC')
            intent: Signal intent ('LONG', 'SHORT', 'FLAT')
            confidence: Raw confidence value (0.0-1.0)
            reason: Strategy's reason string
            regime: Current regime state
            features: Optional dict of key feature values for context
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy_name": strategy_name,
            "symbol": symbol,
            "intent": intent,
            "confidence": confidence,
            "reason": reason,
            "regime": regime,
        }

        # Include a subset of features for debugging (keep records small)
        if features:
            record["features"] = {
                k: features[k]
                for k in ("close", "atr", "rsi_14", "sma_20", "volatility")
                if k in features
            }

        self._buffer.append(record)

        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def flush(self) -> int:
        """
        Flush buffered signals to disk.

        Returns:
            Number of records flushed.
        """
        if not self._buffer:
            return 0

        count = len(self._buffer)
        self.persistence.append_signals(self._buffer)
        self._buffer.clear()
        logger.debug("Flushed %d signal records to disk", count)
        return count
