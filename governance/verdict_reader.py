"""
Governance Verdict Reader: Consume Phase F epistemic verdicts.

Reads Phase F verdicts for governance consumption.
Used by governance/agents/proposer.py to adjust confidence and add context.

Layer 2 of Phase F three-layer logging (for Phase C integration).
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VerdictReader:
    """
    Reads Phase F verdicts for governance consumption.

    Phase F writes verdicts to: persist/phase_f/crypto/verdicts/verdicts.jsonl
    This reader provides the latest verdict for Phase C to:
    - Adjust proposal confidence
    - Add epistemic context to metadata
    - Apply penalties for REGIME_QUESTIONABLE or HIGH_NOISE
    """

    def __init__(self, phase_f_root: str = "persist/phase_f"):
        """
        Initialize verdict reader.

        Args:
            phase_f_root: Root directory for Phase F persistence
        """
        self.phase_f_root = Path(phase_f_root)

    def read_latest_verdict(self, scope: str = "crypto") -> Optional[Dict[str, Any]]:
        """
        Read most recent Phase F verdict.

        Args:
            scope: Scope name (default: "crypto")

        Returns:
            Latest verdict record or None if not available

        Verdict record structure:
        {
            "run_id": "phase_f_run_20260211_030000",
            "timestamp": "2026-02-11T03:00:00.123456",
            "verdict": {
                "verdict": "REGIME_VALIDATED" | "REGIME_QUESTIONABLE" | "HIGH_NOISE_NO_ACTION" | "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE",
                "regime_confidence": 0.85,
                "confidence_change_from_internal": 0.05,
                "narrative_consistency": "HIGH" | "MIXED" | "LOW",
                "reasoning_summary": "...",
                "num_sources_analyzed": 42,
                "num_contradictions": 3,
                "summary_for_governance": "..."
            }
        }
        """
        verdicts_file = self.phase_f_root / scope / "verdicts" / "verdicts.jsonl"

        if not verdicts_file.exists():
            logger.debug(f"No Phase F verdicts found at {verdicts_file}")
            return None

        try:
            # Read last line (most recent verdict)
            with open(verdicts_file) as f:
                lines = f.readlines()

            if not lines:
                logger.debug(f"Verdicts file is empty: {verdicts_file}")
                return None

            latest_line = lines[-1].strip()
            if not latest_line:
                logger.debug(f"Last line of verdicts file is empty")
                return None

            verdict_record = json.loads(latest_line)

            logger.info(f"Read latest Phase F verdict: {verdict_record['verdict']['verdict']}")
            return verdict_record

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Phase F verdict JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading Phase F verdict: {e}", exc_info=True)
            return None

    def get_governance_summary(self, scope: str = "crypto") -> Optional[str]:
        """
        Get Layer 2 governance summary from latest verdict.

        This is the text summary specifically prepared by Phase F for governance consumption.

        Args:
            scope: Scope name (default: "crypto")

        Returns:
            summary_for_governance field or None
        """
        verdict_record = self.read_latest_verdict(scope)

        if verdict_record and "verdict" in verdict_record:
            return verdict_record["verdict"].get("summary_for_governance")

        return None

    def should_apply_confidence_penalty(self, scope: str = "crypto") -> bool:
        """
        Check if Phase F recommends confidence penalty.

        Returns True for verdicts indicating regime uncertainty or high noise,
        meaning governance should apply a penalty to proposal confidence.

        Args:
            scope: Scope name (default: "crypto")

        Returns:
            True if REGIME_QUESTIONABLE or HIGH_NOISE verdict detected
        """
        verdict_record = self.read_latest_verdict(scope)

        if verdict_record and "verdict" in verdict_record:
            verdict_type = verdict_record["verdict"].get("verdict")
            return verdict_type in ["REGIME_QUESTIONABLE", "HIGH_NOISE_NO_ACTION"]

        return False

    def get_penalty_factor(self, scope: str = "crypto") -> float:
        """
        Get confidence penalty factor from latest verdict.

        Returns:
            Multiplier to apply to confidence (e.g., 0.8 = 20% penalty)
        """
        verdict_record = self.read_latest_verdict(scope)

        if not verdict_record or "verdict" not in verdict_record:
            return 1.0  # No penalty

        verdict_type = verdict_record["verdict"].get("verdict")

        # Penalty schedule (from epistemic_reviewer.py:288)
        if verdict_type == "REGIME_QUESTIONABLE":
            return 0.8  # 20% penalty
        elif verdict_type == "HIGH_NOISE_NO_ACTION":
            return 0.7  # 30% penalty
        elif verdict_type == "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE":
            return 0.9  # 10% penalty
        else:  # REGIME_VALIDATED
            return 1.0  # No penalty

    def get_verdict_metadata(self, scope: str = "crypto") -> Optional[Dict[str, Any]]:
        """
        Get full verdict metadata for governance proposal metadata.

        Args:
            scope: Scope name (default: "crypto")

        Returns:
            Dict with all verdict fields for metadata, or None if not available
        """
        verdict_record = self.read_latest_verdict(scope)

        if not verdict_record:
            return None

        return {
            "phase_f_run_id": verdict_record.get("run_id"),
            "phase_f_verdict_timestamp": verdict_record.get("timestamp"),
            "phase_f_verdict_type": verdict_record["verdict"].get("verdict"),
            "phase_f_regime_confidence": verdict_record["verdict"].get("regime_confidence"),
            "phase_f_narrative_consistency": verdict_record["verdict"].get("narrative_consistency"),
            "phase_f_num_sources": verdict_record["verdict"].get("num_sources_analyzed"),
            "phase_f_num_contradictions": verdict_record["verdict"].get("num_contradictions"),
        }
