"""
Phase F Logging: Three-layer transparency for epistemic intelligence.

Layer 1 (Pipeline): Structured JSON logs for monitoring and debugging
Layer 2 (Governance): Verdict summaries for Phase C consumption (handled by persistence.append_verdict)
Layer 3 (Audit): Human-readable reasoning traces for oversight

All layers are append-only and immutable.
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from phase_f.schemas import Verdict

logger = logging.getLogger(__name__)


class PhaseFLogger:
    """
    Three-layer transparency logging for Phase F.

    Layer 1: Structured pipeline logs (JSON, for monitoring)
    Layer 2: Governance summaries (written by persistence, for Phase C integration)
    Layer 3: Human audit trails (for human oversight and reasoning)
    """

    def __init__(self, scope: str = "crypto"):
        """
        Initialize logger.

        Args:
            scope: Scope name (default: "crypto")
        """
        self.scope = scope
        self.logs_dir = Path(f"persist/phase_f/{scope}/logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Log file paths
        self.pipeline_log_file = self.logs_dir / "pipeline.jsonl"
        self.audit_trail_file = self.logs_dir / "audit_trail.jsonl"

        logger.info(f"PhaseFLogger initialized: scope={scope}, logs_dir={self.logs_dir}")

    # ========================================================================
    # LAYER 1: Pipeline Structured Logs (JSON, for monitoring)
    # ========================================================================

    def log_run_start(self, run_id: str):
        """Log pipeline run start (Layer 1)."""
        payload = {
            "event": "RUN_START",
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": self.scope
        }
        self._write_pipeline_log(payload)
        logger.info(f"Run started: {run_id}")

    def log_stage_complete(self, stage: str, metrics: Dict[str, Any]):
        """Log pipeline stage completion (Layer 1)."""
        payload = {
            "event": "STAGE_COMPLETE",
            "stage": stage,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": self.scope,
            "metrics": metrics
        }
        self._write_pipeline_log(payload)
        logger.info(f"Stage complete: {stage}")

    def log_run_complete(self, run_id: str, success: bool, error: Optional[str] = None):
        """Log pipeline run completion (Layer 1)."""
        payload = {
            "event": "RUN_COMPLETE",
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": self.scope,
            "success": success,
            "error": error
        }
        self._write_pipeline_log(payload)
        status = "SUCCESS" if success else f"FAILED: {error}"
        logger.info(f"Run complete: {run_id} - {status}")

    def _write_pipeline_log(self, payload: Dict[str, Any]):
        """Write payload to pipeline log file (Layer 1)."""
        try:
            with open(self.pipeline_log_file, "a") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write pipeline log: {e}", exc_info=True)

    # ========================================================================
    # LAYER 3: Human Audit Trails (for oversight and transparency)
    # ========================================================================

    def log_verdict_reasoning(self, run_id: str, verdict: Verdict):
        """
        Log verdict reasoning for human audit (Layer 3).

        Records the complete verdict with reasoning for human review.
        """
        audit_entry = {
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "verdict_type": verdict.verdict.value,
            "regime_confidence": verdict.regime_confidence,
            "confidence_change_from_internal": verdict.confidence_change_from_internal,
            "narrative_consistency": verdict.narrative_consistency.value,
            "reasoning_summary": verdict.reasoning_summary,
            "num_sources_analyzed": verdict.num_sources_analyzed,
            "num_contradictions": verdict.num_contradictions,
            # Layer 2: Governance summary (for Phase C consumption)
            "summary_for_governance": verdict.summary_for_governance
        }

        try:
            with open(self.audit_trail_file, "a") as f:
                f.write(json.dumps(audit_entry, default=str) + "\n")
            logger.info(f"Audit trail logged for {run_id}: {verdict.verdict.value}")
        except Exception as e:
            logger.error(f"Failed to write audit trail: {e}", exc_info=True)

    # ========================================================================
    # Layer 2: Governance Summaries
    # ========================================================================
    # NOTE: Layer 2 is handled by phase_f/persistence.py:append_verdict()
    # which writes verdicts to verdicts.jsonl in a format readable by governance.verdict_reader.VerdictReader
