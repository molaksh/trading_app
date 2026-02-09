"""
Phase D main orchestration loop.
"""

import logging
from datetime import datetime
from typing import List, Optional

from phase_d.block_detector import BlockDetector
from phase_d.evidence_collector import EvidenceCollector
from phase_d.block_classifier import BlockClassifier
from phase_d.eligibility_checker import EligibilityChecker
from phase_d.persistence import PhaseDPersistence
from phase_d.schemas import PhaseDEvent
from ops_agent.summary_reader import SummaryReader
from config.phase_d_settings import PHASE_D_V0_ENABLED, PHASE_D_V1_ENABLED, PHASE_D_KILL_SWITCH

logger = logging.getLogger(__name__)


class PhaseDLoop:
    """Main Phase D orchestration loop."""

    def __init__(self, scopes: Optional[List[str]] = None):
        self.scopes = scopes or [
            "live_kraken_crypto_global",
            "paper_kraken_crypto_global",
        ]

        self.block_detector = BlockDetector(summary_reader=SummaryReader())
        self.evidence_collector = EvidenceCollector()
        self.classifier = BlockClassifier()
        self.eligibility_checker = EligibilityChecker()
        self.persistence = PhaseDPersistence()

        logger.info(f"Phase D initialized | v0_enabled={PHASE_D_V0_ENABLED} v1_enabled={PHASE_D_V1_ENABLED} kill_switch={PHASE_D_KILL_SWITCH}")

    def tick(self) -> None:
        """
        Run one iteration of Phase D analysis.

        This method:
        1. Detects new blocks and block ends
        2. Collects evidence for completed blocks
        3. Classifies blocks
        4. Evaluates eligibility (v1)
        """
        if PHASE_D_KILL_SWITCH:
            return

        if not PHASE_D_V0_ENABLED:
            return

        try:
            for scope in self.scopes:
                self._process_scope(scope)
        except Exception as e:
            logger.error(f"PHASE_D_LOOP_FAILED | error={e}")

    def _process_scope(self, scope: str) -> None:
        """Process Phase D analysis for a single scope."""
        try:
            # Detect blocks (start/end)
            block_start, block_end = self.block_detector.detect_blocks(scope)

            # Handle block start
            if block_start:
                self.persistence.write_block_event(block_start)
                self.persistence.write_event(
                    PhaseDEvent(
                        timestamp=datetime.utcnow(),
                        event_type="BLOCK_START",
                        scope=scope,
                        block_id=block_start.block_id,
                        details={"regime": block_start.regime},
                    )
                )

            # Handle block end (collect evidence + classify)
            if block_end:
                self.persistence.write_block_event(block_end)

                # Collect evidence
                evidence = self.evidence_collector.collect_evidence(block_end)
                if evidence:
                    self.persistence.write_block_evidence(evidence)
                    self.persistence.write_event(
                        PhaseDEvent(
                            timestamp=datetime.utcnow(),
                            event_type="EVIDENCE_COLLECTED",
                            scope=scope,
                            block_id=block_end.block_id,
                            details={
                                "upside_btc": evidence.btc_max_upside_pct,
                                "upside_eth": evidence.eth_max_upside_pct,
                            },
                        )
                    )

                    # Classify block
                    block_type = self.classifier.classify_block(block_end, evidence)
                    block_end.block_type = block_type

                # Evaluate eligibility (v1)
                if PHASE_D_V1_ENABLED:
                    self._evaluate_eligibility(scope)

        except Exception as e:
            logger.error(f"PHASE_D_SCOPE_PROCESSING_FAILED | scope={scope} error={e}")

    def _evaluate_eligibility(self, scope: str) -> None:
        """Evaluate Phase D v1 eligibility for a scope."""
        try:
            current_block = self.block_detector.get_active_block(scope)
            result = self.eligibility_checker.check_eligibility(scope, current_block)

            if result:
                self.persistence.write_eligibility_result(result)
                self.persistence.write_event(
                    PhaseDEvent(
                        timestamp=datetime.utcnow(),
                        event_type="ELIGIBILITY_EVALUATED",
                        scope=scope,
                        details={
                            "eligible": result.eligible,
                            "rule_details": result.rule_details,
                        },
                    )
                )
        except Exception as e:
            logger.error(f"PHASE_D_ELIGIBILITY_EVAL_FAILED | scope={scope} error={e}")
