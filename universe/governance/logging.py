"""
Phase G Logging: Three-layer transparency for universe governance.

Layer 1 (Pipeline): Structured JSON logs for monitoring (pipeline.jsonl)
Layer 2 (Scoring Detail): Per-symbol score breakdowns (scoring_detail.jsonl)
Layer 3 (Audit): Human-readable decision traces (audit_trail.jsonl)

All layers are append-only and immutable.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PhaseGLogger:
    """Three-layer transparency logging for Phase G universe governance."""

    def __init__(self, scope: str):
        self.scope = scope
        self.logs_dir = Path(f"persist/phase_g/{scope}/logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.pipeline_log = self.logs_dir / "pipeline.jsonl"
        self.audit_trail = self.logs_dir / "audit_trail.jsonl"
        self.scoring_detail = self.logs_dir / "scoring_detail.jsonl"

        logger.info("PhaseGLogger initialized: scope=%s, logs_dir=%s", scope, self.logs_dir)

    # ========================================================================
    # LAYER 1: Pipeline Structured Logs
    # ========================================================================

    def log_governance_cycle_start(self, run_id: str, trigger: str, candidate_count: int):
        self._write_pipeline({
            "event": "GOVERNANCE_CYCLE_START",
            "run_id": run_id,
            "trigger": trigger,
            "candidate_count": candidate_count,
        })

    def log_regime_signal_used(self, run_id: str, regime_label: str,
                               confidence: float, source: str):
        self._write_pipeline({
            "event": "REGIME_SIGNAL_USED",
            "run_id": run_id,
            "regime_label": regime_label,
            "confidence": confidence,
            "source": source,
        })

    def log_verdict_consumed(self, run_id: str, verdict_type: Optional[str],
                             confidence: Optional[float], num_sources: Optional[int]):
        self._write_pipeline({
            "event": "VERDICT_CONSUMED",
            "run_id": run_id,
            "verdict_type": verdict_type,
            "confidence": confidence,
            "num_sources": num_sources,
        })

    def log_governance_decision(self, run_id: str, decision_summary: Dict[str, Any]):
        self._write_pipeline({
            "event": "GOVERNANCE_DECISION",
            "run_id": run_id,
            **decision_summary,
        })
        self._write_audit({
            "event": "GOVERNANCE_DECISION",
            "run_id": run_id,
            **decision_summary,
        })

    def log_governance_cycle_complete(self, run_id: str, duration_ms: float,
                                      symbols_scored: int, adds: List[str],
                                      removes: List[str]):
        self._write_pipeline({
            "event": "GOVERNANCE_CYCLE_COMPLETE",
            "run_id": run_id,
            "duration_ms": round(duration_ms, 1),
            "symbols_scored": symbols_scored,
            "additions": adds,
            "removals": removes,
        })

    def log_dry_run_decision(self, run_id: str, decision_summary: Dict[str, Any]):
        self._write_audit({
            "event": "DRY_RUN_DECISION",
            "run_id": run_id,
            **decision_summary,
        })

    # ========================================================================
    # LAYER 2: Scoring Detail
    # ========================================================================

    def log_symbol_score_computed(self, run_id: str, symbol: str,
                                  total_score: float,
                                  dimension_scores: Dict[str, float],
                                  weighted_scores: Dict[str, float],
                                  raw_metrics: Dict[str, Any]):
        self._write_scoring({
            "event": "SYMBOL_SCORE_COMPUTED",
            "run_id": run_id,
            "symbol": symbol,
            "total_score": round(total_score, 2),
            "dimension_scores": {k: round(v, 2) for k, v in dimension_scores.items()},
            "weighted_scores": {k: round(v, 2) for k, v in weighted_scores.items()},
            "raw_metrics": raw_metrics,
        })

    # ========================================================================
    # LAYER 3: Audit Trail
    # ========================================================================

    def log_guardrail_check(self, run_id: str, check_type: str, symbol: str,
                            input_values: Dict[str, Any], decision: str,
                            reason: str):
        self._write_audit({
            "event": "GUARDRAIL_CHECK",
            "run_id": run_id,
            "check_type": check_type,
            "symbol": symbol,
            "input_values": input_values,
            "decision": decision,
            "reason": reason,
        })

    def log_addition_proposed(self, run_id: str, symbol: str, score: float,
                              reason: str, guardrail_result: str):
        self._write_audit({
            "event": "ADDITION_PROPOSED",
            "run_id": run_id,
            "symbol": symbol,
            "score": round(score, 2),
            "reason": reason,
            "guardrail_result": guardrail_result,
        })

    def log_removal_proposed(self, run_id: str, symbol: str, score: float,
                             reason: str, guardrail_result: str,
                             has_open_position: bool):
        self._write_audit({
            "event": "REMOVAL_PROPOSED",
            "run_id": run_id,
            "symbol": symbol,
            "score": round(score, 2),
            "reason": reason,
            "guardrail_result": guardrail_result,
            "has_open_position": has_open_position,
        })

    # ========================================================================
    # Internal Writers
    # ========================================================================

    def _write_pipeline(self, payload: Dict[str, Any]):
        payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        payload["scope"] = self.scope
        try:
            with open(self.pipeline_log, "a") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write pipeline log: %s", e, exc_info=True)

    def _write_audit(self, payload: Dict[str, Any]):
        payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        payload["scope"] = self.scope
        try:
            with open(self.audit_trail, "a") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write audit trail: %s", e, exc_info=True)

    def _write_scoring(self, payload: Dict[str, Any]):
        payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        payload["scope"] = self.scope
        try:
            with open(self.scoring_detail, "a") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write scoring detail: %s", e, exc_info=True)
