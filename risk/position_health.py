"""
Position health scoring for autonomous liquidation priority.

Scores each open position 0-100. Lower score = sell first (lowest regret to close).

Four weighted components:
- P&L (0.35): At/above profit target = 0 (lock gains), deep loss = 100 (avoid crystallizing)
- Staleness (0.25): Held max days = 0 (expired), just entered = 100 (fresh)
- Confidence (0.25): Low confidence = 0, high confidence = 100
- Size (0.15): Largest notional = 0 (frees most cash), smallest = 100
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from risk.portfolio_state import OpenPosition

logger = logging.getLogger(__name__)


@dataclass
class ScoredPosition:
    """A position with its liquidation priority score."""
    symbol: str
    score: float
    entry_date: pd.Timestamp
    entry_price: float
    current_price: float
    position_size: float
    notional_value: float
    unrealized_pnl_pct: float
    holding_days: int
    confidence: int
    score_breakdown: Dict[str, float] = field(default_factory=dict)


class PositionHealthScorer:
    """
    Scores positions for liquidation priority.

    Lower score = sell first (lowest regret to close).
    """

    # Component weights (sum to 1.0)
    WEIGHT_PNL = 0.35
    WEIGHT_STALENESS = 0.25
    WEIGHT_CONFIDENCE = 0.25
    WEIGHT_SIZE = 0.15

    # P&L anchors
    PNL_TARGET_PCT = 0.10   # +10% = at target, score 0
    PNL_LOSS_PCT = -0.10    # -10% = deep loss, score 100

    # Staleness anchor
    MAX_HOLDING_DAYS = 20   # 20+ days = expired, score 0

    def score_positions(
        self,
        positions: List[OpenPosition],
        today: Optional[pd.Timestamp] = None,
    ) -> List[ScoredPosition]:
        """
        Score all positions and return sorted ascending (sell first).

        Args:
            positions: List of OpenPosition objects
            today: Current date for staleness calculation

        Returns:
            List of ScoredPosition sorted by score ascending (lowest = sell first)
        """
        if not positions:
            return []

        if today is None:
            today = pd.Timestamp.now(tz="UTC")

        # Ensure today is tz-aware
        if today.tzinfo is None:
            today = today.tz_localize("UTC")

        # Pre-compute max notional for size normalization
        notional_values = []
        for pos in positions:
            notional_values.append(pos.current_price * pos.position_size)
        max_notional = max(notional_values) if notional_values else 1.0

        scored = []
        for pos, notional in zip(positions, notional_values):
            entry_date = pos.entry_date
            if entry_date.tzinfo is None:
                entry_date = entry_date.tz_localize("UTC")

            holding_days = (today - entry_date).days

            pnl_pct = (
                (pos.current_price - pos.entry_price) / pos.entry_price
                if pos.entry_price > 0
                else 0.0
            )

            # Score each component
            pnl_score = self._score_pnl(pnl_pct)
            staleness_score = self._score_staleness(holding_days)
            confidence_score = self._score_confidence(pos.confidence)
            size_score = self._score_size(notional, max_notional)

            # Weighted total
            total = (
                self.WEIGHT_PNL * pnl_score
                + self.WEIGHT_STALENESS * staleness_score
                + self.WEIGHT_CONFIDENCE * confidence_score
                + self.WEIGHT_SIZE * size_score
            )

            scored.append(ScoredPosition(
                symbol=pos.symbol,
                score=round(total, 1),
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                current_price=pos.current_price,
                position_size=pos.position_size,
                notional_value=round(notional, 2),
                unrealized_pnl_pct=round(pnl_pct * 100, 2),
                holding_days=holding_days,
                confidence=pos.confidence,
                score_breakdown={
                    "pnl": round(pnl_score, 1),
                    "staleness": round(staleness_score, 1),
                    "confidence": round(confidence_score, 1),
                    "size": round(size_score, 1),
                },
            ))

        # Sort ascending: lowest score = sell first
        scored.sort(key=lambda s: s.score)
        return scored

    def _score_pnl(self, pnl_pct: float) -> float:
        """
        Score P&L component.

        At/above +10% target -> 0 (sell first: lock gains)
        At 0% -> 50
        At/below -10% -> 100 (keep: avoid crystallizing big loss)
        Linear interpolation between anchors.
        """
        if pnl_pct >= self.PNL_TARGET_PCT:
            return 0.0
        if pnl_pct <= self.PNL_LOSS_PCT:
            return 100.0

        # Linear interpolation: -10% -> 100, +10% -> 0
        range_pct = self.PNL_TARGET_PCT - self.PNL_LOSS_PCT  # 0.20
        normalized = (self.PNL_TARGET_PCT - pnl_pct) / range_pct
        return max(0.0, min(100.0, normalized * 100.0))

    def _score_staleness(self, holding_days: int) -> float:
        """
        Score staleness component.

        20+ days -> 0 (sell first: expired)
        0 days -> 100 (keep: fresh)
        Linear interpolation.
        """
        if holding_days >= self.MAX_HOLDING_DAYS:
            return 0.0
        if holding_days <= 0:
            return 100.0

        return max(0.0, 100.0 * (1.0 - holding_days / self.MAX_HOLDING_DAYS))

    def _score_confidence(self, confidence: int) -> float:
        """
        Score confidence component.

        Confidence 1 -> 0 (sell first)
        Confidence 5 -> 100 (keep)
        Map: (conf - 1) * 25
        """
        return max(0.0, min(100.0, (confidence - 1) * 25.0))

    def _score_size(self, notional: float, max_notional: float) -> float:
        """
        Score size component.

        Largest notional -> 0 (sell first: frees most cash)
        Smallest notional -> 100 (keep)
        Normalized to max in batch.
        """
        if max_notional <= 0:
            return 50.0

        # Largest = 0, smallest = 100
        return max(0.0, min(100.0, 100.0 * (1.0 - notional / max_notional)))
