"""
Eligibility checker: Evaluates 5 rules for Phase D eligibility.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from phase_d.schemas import BlockEvent, BlockEvidence, BlockType, PhaseEligibilityResult
from phase_d.persistence import PhaseDPersistence
from phase_d.historical_analyzer import HistoricalAnalyzer
from config.phase_d_settings import (
    ELIGIBILITY_MIN_BLOCKS,
    ELIGIBILITY_MIN_POSITIVE_CB,
    ELIGIBILITY_EXPIRY_HOURS,
)

logger = logging.getLogger(__name__)


class EligibilityChecker:
    """Evaluates 5-rule eligibility framework for Phase D."""

    def __init__(
        self,
        persistence: Optional[PhaseDPersistence] = None,
        historical_analyzer: Optional[HistoricalAnalyzer] = None,
    ):
        self.persistence = persistence or PhaseDPersistence()
        self.historical_analyzer = historical_analyzer or HistoricalAnalyzer()

    def check_eligibility(
        self,
        scope: str,
        current_block: Optional[BlockEvent],
        block_history: Optional[List[BlockEvent]] = None,
        evidence_map: Optional[Dict[str, BlockEvidence]] = None,
    ) -> PhaseEligibilityResult:
        """
        Evaluate all 5 eligibility rules.

        ALL 5 rules must pass for eligibility = True

        Rules:
        1. Evidence Sufficiency: >= 3 completed blocks with evidence
        2. Duration Anomaly: Current block > p90 (if active)
        3. Block Type: Recent blocks are COMPRESSION or STRUCTURAL (not SHOCK)
        4. Cost-Benefit: Missed upside > drawdown avoided in >= 2 blocks
        5. Regime Safety: Current regime not PANIC/SHOCK, vol normal

        Args:
            scope: Scope name
            current_block: Currently active block (if any)
            block_history: List of block events (reads from persistence if None)
            evidence_map: Dict of block_id -> BlockEvidence (reads from persistence if None)

        Returns:
            PhaseEligibilityResult with all rule evaluations
        """
        try:
            # Load from persistence if not provided
            if block_history is None:
                block_history = self.persistence.read_block_events(scope)

            if evidence_map is None:
                evidence_map = {}
                for block in block_history:
                    evidence = self.persistence.read_block_evidence(block.block_id)
                    if evidence:
                        evidence_map[block.block_id] = evidence

            # Rule 1: Evidence Sufficiency (>= 3 completed blocks)
            completed_with_evidence = [
                b for b in block_history
                if b.block_end_ts and b.block_id in evidence_map
            ]
            evidence_sufficiency = len(completed_with_evidence) >= ELIGIBILITY_MIN_BLOCKS

            # Rule 2: Duration Anomaly (current > p90)
            duration_anomaly = False
            current_duration = 0
            if current_block and current_block.block_start_ts:
                current_duration = int((datetime.utcnow() - current_block.block_start_ts).total_seconds())
                stats = self.historical_analyzer.get_regime_block_stats(scope, current_block.regime, 30)
                if stats and stats.p90_duration_seconds:
                    duration_anomaly = current_duration > stats.p90_duration_seconds

            # Rule 3: Block Type (COMPRESSION or STRUCTURAL, not SHOCK)
            block_type_passed = False
            recent_block_types = []
            if completed_with_evidence:
                recent_3 = sorted(completed_with_evidence, key=lambda b: b.timestamp)[-3:]
                for block in recent_3:
                    block_type = block.block_type
                    if block_type:
                        recent_block_types.append(block_type.value)
                        # Count eligible types
                        if block_type in [BlockType.COMPRESSION, BlockType.STRUCTURAL]:
                            block_type_passed = len(recent_block_types) >= 1

            # Rule 4: Cost-Benefit (missed upside > drawdown in >= 2 blocks)
            positive_cb_count = 0
            for block in completed_with_evidence:
                evidence = evidence_map[block.block_id]
                avg_upside = (evidence.btc_max_upside_pct + evidence.eth_max_upside_pct) / 2
                avg_drawdown = abs((evidence.btc_max_drawdown_pct + evidence.eth_max_drawdown_pct) / 2)
                if avg_upside > avg_drawdown:
                    positive_cb_count += 1

            cost_benefit_passed = positive_cb_count >= ELIGIBILITY_MIN_POSITIVE_CB

            # Rule 5: Regime Safety (no PANIC/SHOCK, no extreme vol expansion)
            regime_safety = False
            if current_block:
                regime_safe = current_block.regime not in ["PANIC", "SHOCK", "BTC_CRASH"]
                vol_safe = True
                if completed_with_evidence:
                    last_evidence = evidence_map[sorted(completed_with_evidence, key=lambda b: b.timestamp)[-1].block_id]
                    vol_safe = last_evidence.volatility_expansion_ratio < 1.5

                regime_safety = regime_safe and vol_safe

            # ALL rules must pass
            eligible = (
                evidence_sufficiency
                and duration_anomaly
                and block_type_passed
                and cost_benefit_passed
                and regime_safety
            )

            # Auto-expire after 24h
            expiry_timestamp = None
            if eligible:
                expiry_timestamp = datetime.utcnow() + timedelta(hours=ELIGIBILITY_EXPIRY_HOURS)

            result = PhaseEligibilityResult(
                timestamp=datetime.utcnow(),
                scope=scope,
                current_block_id=current_block.block_id if current_block else None,
                eligible=eligible,
                evidence_sufficiency_passed=evidence_sufficiency,
                duration_anomaly_passed=duration_anomaly,
                block_type_passed=block_type_passed,
                cost_benefit_passed=cost_benefit_passed,
                regime_safety_passed=regime_safety,
                rule_details={
                    "completed_blocks": len(completed_with_evidence),
                    "current_duration_seconds": current_duration,
                    "positive_cb_count": positive_cb_count,
                    "recent_block_types": recent_block_types,
                },
                expiry_timestamp=expiry_timestamp,
            )

            log_msg = f"PHASE_D_ELIGIBILITY | scope={scope} eligible={eligible} rule1={evidence_sufficiency} rule2={duration_anomaly} rule3={block_type_passed} rule4={cost_benefit_passed} rule5={regime_safety}"
            logger.info(log_msg)

            return result

        except Exception as e:
            logger.error(f"PHASE_D_ELIGIBILITY_CHECK_FAILED | scope={scope} error={e}")
            return PhaseEligibilityResult(
                timestamp=datetime.utcnow(),
                scope=scope,
                eligible=False,
                evidence_sufficiency_passed=False,
                duration_anomaly_passed=False,
                block_type_passed=False,
                cost_benefit_passed=False,
                regime_safety_passed=False,
            )
