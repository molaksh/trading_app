"""
Block detector: Detects regime-blocked periods from daily summaries.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from phase_d.schemas import BlockEvent
from ops_agent.summary_reader import SummaryReader
from config.phase_d_settings import REGIME_BLOCK_MIN_DURATION_SECONDS

logger = logging.getLogger(__name__)


class BlockDetector:
    """Detects regime blocks from daily summary regime_blocked_period field."""

    def __init__(self, summary_reader: Optional[SummaryReader] = None):
        self.summary_reader = summary_reader or SummaryReader(logs_root="logs")
        self._active_blocks: Dict[str, BlockEvent] = {}  # scope -> active BlockEvent

    def detect_blocks(self, scope: str) -> tuple[Optional[BlockEvent], Optional[BlockEvent]]:
        """
        Detect if a block has started or ended for a scope.

        Returns:
            (block_start_event, block_end_event) - one of them None
        """
        try:
            latest_summary = self.summary_reader.get_latest_summary(scope)
            if not latest_summary:
                return None, None

            # Parse regime_blocked_period from summary
            regime_block = latest_summary.regime_blocked_period if hasattr(latest_summary, 'regime_blocked_period') else None
            if not regime_block:
                # Try dict-style access
                regime_block = getattr(latest_summary, '__dict__', {}).get('regime_blocked_period', {})

            is_blocked = regime_block.get('is_blocked', False) if regime_block else False
            block_duration = regime_block.get('block_duration_seconds', 0) if regime_block else 0
            regime = regime_block.get('regime', 'UNKNOWN') if regime_block else 'UNKNOWN'

            # Check if active block needs to be ended
            if scope in self._active_blocks and not is_blocked:
                # Block ended
                active_block = self._active_blocks[scope]
                active_block.block_end_ts = datetime.utcnow()
                active_block.duration_seconds = int((active_block.block_end_ts - active_block.block_start_ts).total_seconds())
                active_block.event_type = "BLOCK_END"

                del self._active_blocks[scope]
                logger.info(f"PHASE_D_BLOCK_ENDED | scope={scope} block_id={active_block.block_id} duration={active_block.duration_seconds}s")
                return None, active_block

            # Check if new block started
            if is_blocked and scope not in self._active_blocks:
                # Block just started
                if block_duration < REGIME_BLOCK_MIN_DURATION_SECONDS:
                    # Too short to report
                    return None, None

                block_event = BlockEvent(
                    block_id=str(uuid.uuid4()),
                    scope=scope,
                    event_type="BLOCK_START",
                    timestamp=datetime.utcnow(),
                    regime=regime,
                    reason="BTC_UNSUITABLE",
                    block_start_ts=datetime.utcnow(),
                )
                self._active_blocks[scope] = block_event
                logger.info(f"PHASE_D_BLOCK_STARTED | scope={scope} block_id={block_event.block_id} regime={regime}")
                return block_event, None

            return None, None

        except Exception as e:
            logger.error(f"PHASE_D_BLOCK_DETECTION_FAILED | scope={scope} error={e}")
            return None, None

    def get_active_block(self, scope: str) -> Optional[BlockEvent]:
        """Get the currently active block for a scope, if any."""
        return self._active_blocks.get(scope)

    def get_all_active_blocks(self) -> Dict[str, BlockEvent]:
        """Get all active blocks across all scopes."""
        return dict(self._active_blocks)
