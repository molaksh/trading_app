"""
Phase G Guardrails: Constitutional constraints for universe governance.

Rules that cannot be overridden:
- Max additions/removals per cycle
- Universe size bounds
- Open position protection
- Cooldown after removal
- Score thresholds for add/remove
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

from universe.governance.config import (
    MAX_ADDITIONS_PER_CYCLE,
    MAX_REMOVALS_PER_CYCLE,
    MIN_UNIVERSE_SIZE,
    MAX_UNIVERSE_SIZE,
    MIN_SCORE_TO_ADD,
    MAX_SCORE_TO_REMOVE,
    COOLDOWN_DAYS_AFTER_REMOVE,
)

logger = logging.getLogger(__name__)


@dataclass
class GuardrailViolation:
    check_type: str
    symbol: str
    reason: str
    input_values: Dict


class UniverseGuardrails:
    """Constitutional constraints for universe governance decisions."""

    def check_addition(
        self,
        symbol: str,
        score: float,
        current_size: int,
        additions_this_cycle: int,
        cooldown_registry: Dict[str, str],
    ) -> Tuple[bool, str]:
        """
        Check if a symbol can be added to the universe.

        Returns:
            (allowed, reason)
        """
        # Max additions per cycle
        if additions_this_cycle >= MAX_ADDITIONS_PER_CYCLE:
            return False, f"max additions per cycle reached ({MAX_ADDITIONS_PER_CYCLE})"

        # Max universe size
        if current_size >= MAX_UNIVERSE_SIZE:
            return False, f"universe at max size ({MAX_UNIVERSE_SIZE})"

        # Score threshold
        if score < MIN_SCORE_TO_ADD:
            return False, f"score {score:.1f} below minimum {MIN_SCORE_TO_ADD}"

        # Cooldown check
        if symbol in cooldown_registry:
            removal_date_str = cooldown_registry[symbol]
            try:
                removal_date = datetime.fromisoformat(removal_date_str)
                if removal_date.tzinfo is None:
                    removal_date = removal_date.replace(tzinfo=timezone.utc)
                cooldown_end = removal_date + timedelta(days=COOLDOWN_DAYS_AFTER_REMOVE)
                now = datetime.now(timezone.utc)
                if now < cooldown_end:
                    days_left = (cooldown_end - now).days
                    return False, f"cooldown active ({days_left}d remaining, removed {removal_date_str})"
            except (ValueError, TypeError):
                logger.warning("Invalid cooldown date for %s: %s", symbol, removal_date_str)

        return True, "passed all checks"

    def check_removal(
        self,
        symbol: str,
        score: float,
        current_size: int,
        removals_this_cycle: int,
        open_symbols: List[str],
    ) -> Tuple[bool, str]:
        """
        Check if a symbol can be removed from the universe.

        Returns:
            (allowed, reason)
        """
        # Max removals per cycle
        if removals_this_cycle >= MAX_REMOVALS_PER_CYCLE:
            return False, f"max removals per cycle reached ({MAX_REMOVALS_PER_CYCLE})"

        # Min universe size
        if current_size <= MIN_UNIVERSE_SIZE:
            return False, f"universe at min size ({MIN_UNIVERSE_SIZE})"

        # Score threshold (must be below threshold to remove)
        if score > MAX_SCORE_TO_REMOVE:
            return False, f"score {score:.1f} above removal threshold {MAX_SCORE_TO_REMOVE}"

        # Open position protection
        if symbol in open_symbols:
            return False, f"symbol has open position"

        return True, "passed all checks"

    def validate_final_universe(
        self,
        universe: List[str],
        previous_universe: List[str],
    ) -> List[GuardrailViolation]:
        """Validate the final universe after all changes."""
        violations = []

        if len(universe) < MIN_UNIVERSE_SIZE:
            violations.append(GuardrailViolation(
                check_type="min_universe_size",
                symbol="*",
                reason=f"universe size {len(universe)} below minimum {MIN_UNIVERSE_SIZE}",
                input_values={"size": len(universe), "min": MIN_UNIVERSE_SIZE},
            ))

        if len(universe) > MAX_UNIVERSE_SIZE:
            violations.append(GuardrailViolation(
                check_type="max_universe_size",
                symbol="*",
                reason=f"universe size {len(universe)} above maximum {MAX_UNIVERSE_SIZE}",
                input_values={"size": len(universe), "max": MAX_UNIVERSE_SIZE},
            ))

        added = set(universe) - set(previous_universe)
        removed = set(previous_universe) - set(universe)

        if len(added) > MAX_ADDITIONS_PER_CYCLE:
            violations.append(GuardrailViolation(
                check_type="max_additions",
                symbol="*",
                reason=f"{len(added)} additions exceeds max {MAX_ADDITIONS_PER_CYCLE}",
                input_values={"added": list(added), "max": MAX_ADDITIONS_PER_CYCLE},
            ))

        if len(removed) > MAX_REMOVALS_PER_CYCLE:
            violations.append(GuardrailViolation(
                check_type="max_removals",
                symbol="*",
                reason=f"{len(removed)} removals exceeds max {MAX_REMOVALS_PER_CYCLE}",
                input_values={"removed": list(removed), "max": MAX_REMOVALS_PER_CYCLE},
            ))

        return violations
