"""
Block classifier: Classifies blocks as NOISE/COMPRESSION/SHOCK/STRUCTURAL.
"""

import logging

from phase_d.schemas import BlockEvent, BlockEvidence, BlockType
from config.phase_d_settings import (
    NOISE_DURATION_MULTIPLIER,
    NOISE_MAX_UPSIDE_PCT,
    NOISE_MAX_DRAWDOWN_PCT,
    COMPRESSION_VOL_EXPANSION_MAX,
    COMPRESSION_MAX_UPSIDE_PCT,
    SHOCK_VOL_EXPANSION_MIN,
    SHOCK_MAX_DRAWDOWN_PCT,
)

logger = logging.getLogger(__name__)


class BlockClassifier:
    """Classifies completed blocks based on evidence."""

    def classify_block(self, block_event: BlockEvent, evidence: BlockEvidence) -> BlockType:
        """
        Classify a block type based on evidence metrics.

        Classification rules (evaluated in order):
        1. SHOCK: Extreme volatility or drawdown
        2. NOISE: Short, insignificant
        3. COMPRESSION: Long, low vol, low upside
        4. STRUCTURAL: Long, high upside (default)

        Args:
            block_event: The block event
            evidence: Evidence metrics for the block

        Returns:
            BlockType classification
        """
        try:
            # Rule 1: SHOCK (extreme vol or drawdown)
            if evidence.volatility_expansion_ratio >= SHOCK_VOL_EXPANSION_MIN:
                logger.info(f"PHASE_D_BLOCK_SHOCK_VOL | block_id={block_event.block_id} vol_ratio={evidence.volatility_expansion_ratio:.2f}")
                return BlockType.SHOCK

            if abs(evidence.btc_max_drawdown_pct) >= SHOCK_MAX_DRAWDOWN_PCT:
                logger.info(f"PHASE_D_BLOCK_SHOCK_DRAWDOWN | block_id={block_event.block_id} drawdown={evidence.btc_max_drawdown_pct:.2f}%")
                return BlockType.SHOCK

            # Rule 2: NOISE (short, insignificant)
            if evidence.historical_median_duration:
                duration_vs_median = evidence.duration_seconds / evidence.historical_median_duration
                if duration_vs_median < NOISE_DURATION_MULTIPLIER:
                    avg_upside = (evidence.btc_max_upside_pct + evidence.eth_max_upside_pct) / 2
                    if avg_upside < NOISE_MAX_UPSIDE_PCT:
                        logger.info(f"PHASE_D_BLOCK_NOISE | block_id={block_event.block_id} duration_vs_median={duration_vs_median:.2f} upside={avg_upside:.2f}%")
                        return BlockType.NOISE

            # Rule 3: COMPRESSION (long, low vol, low upside)
            if evidence.historical_p90_duration:
                if evidence.duration_seconds >= evidence.historical_p90_duration:
                    if evidence.volatility_expansion_ratio < COMPRESSION_VOL_EXPANSION_MAX:
                        avg_upside = (evidence.btc_max_upside_pct + evidence.eth_max_upside_pct) / 2
                        if avg_upside < COMPRESSION_MAX_UPSIDE_PCT:
                            logger.info(f"PHASE_D_BLOCK_COMPRESSION | block_id={block_event.block_id}")
                            return BlockType.COMPRESSION

            # Rule 4: STRUCTURAL (default for long blocks with upside)
            logger.info(f"PHASE_D_BLOCK_STRUCTURAL | block_id={block_event.block_id}")
            return BlockType.STRUCTURAL

        except Exception as e:
            logger.error(f"PHASE_D_CLASSIFICATION_FAILED | block_id={block_event.block_id} error={e}")
            return BlockType.STRUCTURAL  # Default to structural on error
