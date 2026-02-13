"""
Phase G Regime Orchestrator: Full periodic regime validation pipeline.

Pipeline: load data → validate → detect drift → propose (if needed) → guardrails → persist.

Constitutional rule: This system does NOT change regime directly.
It studies regime, detects drift, and proposes change through governance.

Scheduling:
  - Crypto: every 2 hours, min 4h dwell, emergency override at drawdown < -25%
  - Swing: once daily, min 3-day dwell, no intraday flips

All runs are idempotent. State persisted to run_state.json.
Timeout enforced at 90 seconds per cycle.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from phase_g_regime.regime_validator import (
    RegimeValidator,
    RegimeValidationContext,
    RegimeValidationResult,
)
from phase_g_regime.regime_drift_detector import RegimeDriftDetector, DriftDetectionResult
from phase_g_regime.regime_guardrails import RegimeGuardrails

logger = logging.getLogger(__name__)

# ============================================================================
# RESOURCE LIMITS
# ============================================================================
MAX_RUNTIME_SECONDS = 90
VALIDATION_INTERVAL_MINUTES_CRYPTO = 120  # 2 hours
VALIDATION_INTERVAL_MINUTES_SWING = 1440  # 24 hours


@dataclass
class RegimeProposal:
    """Non-binding regime change proposal for governance review."""
    proposal_id: str
    timestamp_utc: str
    proposal_type: str  # Always "REGIME_ADJUSTMENT"
    scope: str
    current_regime: str
    proposed_regime: str
    confidence: float
    supporting_factors: List[str]
    risk_analysis: List[str]
    dissent_signals: List[str]
    uncertainty_statement: str
    drift_statistics: Dict[str, Any]
    non_binding: bool  # Always True
    guardrail_result: str  # "APPROVED" or "DEFERRED"
    guardrail_reason: Optional[str]
    guardrail_checks: List[Dict[str, Any]]
    emergency_override: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegimeValidationCycleResult:
    """Complete result of a validation cycle."""
    run_id: str
    timestamp_utc: str
    scope: str
    trigger: str
    validation: Optional[Dict[str, Any]]
    drift: Optional[Dict[str, Any]]
    proposal: Optional[Dict[str, Any]]
    outcome: str  # VALIDATED, INSUFFICIENT_DATA, UNCERTAIN, DRIFT_DETECTED, DRIFT_DEFERRED, VALIDATION_FAILED, SKIPPED, TIMEOUT
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RegimeOrchestrator:
    """
    Full periodic regime validation pipeline.

    Orchestrates: validate → drift detect → propose → guardrails → persist → log.
    Never mutates regime directly.
    """

    def __init__(
        self,
        scope,
        runtime=None,
        verdict_reader=None,
    ):
        self.scope = scope
        self.scope_str = str(scope)
        self.runtime = runtime
        self.verdict_reader = verdict_reader

        self.validator = RegimeValidator()
        self.drift_detector = RegimeDriftDetector()
        self.guardrails = RegimeGuardrails()

        # Determine scope type
        scope_lower = self.scope_str.lower()
        self.scope_type = "crypto" if "crypto" in scope_lower else "swing"

        # Persistence paths
        self.persist_dir = Path(f"persist/phase_g/{self.scope_str}/regime")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.run_state_path = self.persist_dir / "run_state.json"
        self.validation_runs_path = self.persist_dir / "validation_runs.jsonl"
        self.proposals_path = self.persist_dir / "proposals.jsonl"
        self.drift_history_path = self.persist_dir / "drift_history.jsonl"
        self.audit_trail_path = self.persist_dir / "audit_trail.jsonl"

    def run_validation_cycle(
        self, trigger: str = "scheduled"
    ) -> RegimeValidationCycleResult:
        """
        Run a full regime validation cycle.

        Steps:
        1. Check idempotency (skip if ran too recently)
        2. Load all inputs
        3. Validate (Stage 1)
        4. Detect drift if needed (Stage 2)
        5. Create proposal if drift confirmed (Stage 3)
        6. Apply guardrails (Stage 4)
        7. Persist and log everything
        """
        start_time = time.time()
        run_id = f"regime_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        logger.info(
            "REGIME_VALIDATION_START | run_id=%s | scope=%s | trigger=%s",
            run_id, self.scope_str, trigger,
        )

        try:
            # Step 1: Idempotency check
            run_state = self._load_run_state()
            if self._should_skip(run_state, trigger):
                result = RegimeValidationCycleResult(
                    run_id=run_id,
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    scope=self.scope_str,
                    trigger=trigger,
                    validation=None,
                    drift=None,
                    proposal=None,
                    outcome="SKIPPED",
                    duration_ms=(time.time() - start_time) * 1000,
                )
                self._log_pipeline({
                    "event": "REGIME_VALIDATION_SKIPPED",
                    "run_id": run_id,
                    "reason": "too_recent",
                    "last_run_utc": run_state.get("last_run_utc"),
                })
                logger.info("REGIME_VALIDATION_SKIPPED | run_id=%s | reason=too_recent", run_id)
                return result

            # Step 2: Load context
            self._check_timeout(start_time)
            ctx = self._build_context(run_state)

            # Detect if live regime changed since last run
            self._detect_regime_transition(run_state, ctx.current_regime, ctx.volatility)

            # Log all raw inputs for traceability
            self._log_audit({
                "event": "REGIME_CONTEXT_BUILT",
                "run_id": run_id,
                "current_regime": ctx.current_regime,
                "current_regime_confidence": round(ctx.current_regime_confidence, 4),
                "recalculated_regime": ctx.recalculated_regime,
                "recalculated_confidence": round(ctx.recalculated_confidence, 4),
                "cross_asset_regime": ctx.cross_asset_regime,
                "volatility": round(ctx.volatility, 2),
                "volatility_percentile": round(ctx.volatility_percentile, 4),
                "drawdown": round(ctx.drawdown, 2),
                "entry_volatility": round(ctx.entry_volatility, 2),
                "duration_hours": round(ctx.current_regime_duration_hours, 1),
                "historical_durations_count": len(ctx.historical_regime_durations),
                "num_external_sources": ctx.num_external_sources,
                "phase_f_verdict_type": (
                    ctx.phase_f_verdict["verdict"].get("verdict")
                    if ctx.phase_f_verdict and "verdict" in ctx.phase_f_verdict
                    else None
                ),
            })

            # Step 3: Validate (Stage 1)
            self._check_timeout(start_time)
            validation_result = self.validator.validate(ctx, run_id)

            self._log_pipeline({
                "event": "REGIME_VALIDATION_COMPLETE",
                "run_id": run_id,
                "verdict": validation_result.verdict,
                "scores": validation_result.scores.to_dict(),
                "current_regime": ctx.current_regime,
                "recalculated_regime": ctx.recalculated_regime,
            })

            # Step 4: Drift detection (Stage 2) — only if drift was detected
            drift_result = None
            proposal = None

            if validation_result.verdict == "REGIME_DRIFT_DETECTED":
                self._check_timeout(start_time)
                drift_result = self.drift_detector.detect(
                    ctx, validation_result.scores, self.scope_type,
                )

                self._append_jsonl(self.drift_history_path, {
                    "run_id": run_id,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "drift_detected": drift_result.drift_detected,
                    "conditions": [c.to_dict() for c in drift_result.conditions],
                    "suggested_regime": drift_result.suggested_regime,
                })

                self._log_pipeline({
                    "event": "DRIFT_DETECTION_COMPLETE",
                    "run_id": run_id,
                    "drift_detected": drift_result.drift_detected,
                    "suggested_regime": drift_result.suggested_regime,
                    "conditions_met": sum(1 for c in drift_result.conditions if c.met),
                    "conditions_total": len(drift_result.conditions),
                })

                # Step 5: Create proposal (Stage 3) if drift confirmed
                if drift_result.drift_detected and drift_result.suggested_regime:
                    self._check_timeout(start_time)
                    proposal = self._create_proposal(
                        run_id, ctx, validation_result, drift_result, run_state,
                    )

            # Determine outcome
            if validation_result.verdict == "REGIME_INSUFFICIENT_DATA":
                outcome = "INSUFFICIENT_DATA"
            elif validation_result.verdict == "REGIME_VALIDATED":
                outcome = "VALIDATED"
            elif validation_result.verdict == "REGIME_UNCERTAIN":
                outcome = "UNCERTAIN"
            elif drift_result and drift_result.drift_detected and proposal:
                outcome = proposal.guardrail_result  # "APPROVED" or "DEFERRED"
            elif drift_result and not drift_result.drift_detected:
                outcome = "UNCERTAIN"  # Drift check failed strict conditions
            else:
                outcome = validation_result.verdict

            # Step 6: Persist everything
            duration_ms = (time.time() - start_time) * 1000

            cycle_result = RegimeValidationCycleResult(
                run_id=run_id,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                scope=self.scope_str,
                trigger=trigger,
                validation=validation_result.to_dict(),
                drift=drift_result.to_dict() if drift_result else None,
                proposal=proposal.to_dict() if proposal else None,
                outcome=outcome,
                duration_ms=round(duration_ms, 1),
            )

            self._append_jsonl(self.validation_runs_path, cycle_result.to_dict())

            # Update run state
            run_state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
            self._save_run_state(run_state)

            # Log completion
            self._log_pipeline({
                "event": "REGIME_VALIDATION_CYCLE_COMPLETE",
                "run_id": run_id,
                "outcome": outcome,
                "duration_ms": round(duration_ms, 1),
                "current_regime": ctx.current_regime,
                "recalculated_regime": ctx.recalculated_regime,
            })

            self._log_audit({
                "event": "REGIME_VALIDATION_AUDIT",
                "run_id": run_id,
                "validation_scores": validation_result.scores.to_dict(),
                "validation_verdict": validation_result.verdict,
                "validation_evidence": validation_result.evidence,
                "drift_conditions": (
                    [c.to_dict() for c in drift_result.conditions]
                    if drift_result else None
                ),
                "proposal_summary": (
                    {
                        "proposed_regime": proposal.proposed_regime,
                        "confidence": proposal.confidence,
                        "guardrail_result": proposal.guardrail_result,
                        "guardrail_reason": proposal.guardrail_reason,
                    }
                    if proposal else None
                ),
                "outcome": outcome,
            })

            logger.info(
                "REGIME_VALIDATION_COMPLETE | run_id=%s | outcome=%s | "
                "current=%s | recalculated=%s | duration_ms=%.1f",
                run_id, outcome, ctx.current_regime,
                ctx.recalculated_regime, duration_ms,
            )

            return cycle_result

        except _TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "REGIME_VALIDATION_TIMEOUT | run_id=%s | duration_ms=%.1f | "
                "limit=%ds",
                run_id, duration_ms, MAX_RUNTIME_SECONDS,
            )
            self._log_pipeline({
                "event": "REGIME_VALIDATION_TIMEOUT",
                "run_id": run_id,
                "duration_ms": round(duration_ms, 1),
            })
            return RegimeValidationCycleResult(
                run_id=run_id,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                scope=self.scope_str,
                trigger=trigger,
                validation=None, drift=None, proposal=None,
                outcome="TIMEOUT",
                duration_ms=round(duration_ms, 1),
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "REGIME_VALIDATION_FAILED | run_id=%s | error=%s | "
                "defaulting to current regime",
                run_id, e, exc_info=True,
            )
            self._log_pipeline({
                "event": "REGIME_VALIDATION_FAILED",
                "run_id": run_id,
                "error": str(e),
                "duration_ms": round(duration_ms, 1),
            })
            return RegimeValidationCycleResult(
                run_id=run_id,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                scope=self.scope_str,
                trigger=trigger,
                validation=None, drift=None, proposal=None,
                outcome="VALIDATION_FAILED",
                duration_ms=round(duration_ms, 1),
            )

    # ========================================================================
    # Context building
    # ========================================================================

    def _build_context(self, run_state: Dict) -> RegimeValidationContext:
        """Build validation context from all available inputs."""

        # Current regime from live engine
        current_regime = None
        current_confidence = 0.5
        regime_engine = getattr(self.runtime, "crypto_regime_engine", None) if self.runtime else None

        if regime_engine is not None:
            mr = regime_engine.get_current_regime()
            if mr is not None:
                current_regime = mr.value if hasattr(mr, "value") else str(mr)
        if current_regime is None:
            current_regime = run_state.get("current_regime")

        # Recalculate regime from fresh data
        recalculated_regime = None
        recalculated_confidence = 0.5
        volatility = 0.0
        volatility_percentile = 0.5
        drawdown = 0.0
        cross_asset_regime = None

        try:
            recalc = self._recalculate_regime()
            if recalc:
                recalculated_regime = recalc["regime"]
                recalculated_confidence = recalc["confidence"]
                volatility = recalc["volatility"]
                volatility_percentile = recalc.get("vol_percentile", 0.5)
                drawdown = recalc["drawdown"]
                cross_asset_regime = recalc.get("cross_asset_regime")
        except Exception as e:
            logger.warning("REGIME_RECALC_FAILED | error=%s", e)

        # Also update current_confidence from live engine's last signal
        if regime_engine is not None and hasattr(regime_engine, "current_regime"):
            current_confidence = recalculated_confidence  # Best available

        # Phase F verdict
        phase_f_verdict = None
        num_sources = 0
        if self.verdict_reader:
            try:
                phase_f_verdict = self.verdict_reader.read_latest_verdict(
                    scope="crypto" if self.scope_type == "crypto" else "swing"
                )
                if phase_f_verdict and "verdict" in phase_f_verdict:
                    num_sources = phase_f_verdict["verdict"].get("num_sources_analyzed", 0)
            except Exception as e:
                logger.warning("VERDICT_READ_FAILED | error=%s", e)

        # Duration and history from run state
        duration_hours = self._compute_duration_hours(run_state)
        history = run_state.get("regime_duration_history", [])
        entry_vol = run_state.get("entry_volatility", volatility)

        return RegimeValidationContext(
            scope=self.scope_str,
            current_regime=current_regime,
            current_regime_confidence=current_confidence,
            recalculated_regime=recalculated_regime,
            recalculated_confidence=recalculated_confidence,
            phase_f_verdict=phase_f_verdict,
            cross_asset_regime=cross_asset_regime,
            volatility=volatility,
            volatility_percentile=volatility_percentile,
            drawdown=drawdown,
            current_regime_duration_hours=duration_hours,
            historical_regime_durations=history,
            num_external_sources=num_sources,
            entry_volatility=entry_vol,
        )

    def _recalculate_regime(self) -> Optional[Dict[str, Any]]:
        """
        Recalculate regime from fresh OHLCV data using a temporary engine.
        Does NOT mutate the live engine's state.
        """
        if self.scope_type == "crypto":
            return self._recalculate_crypto_regime()
        else:
            return self._recalculate_swing_regime()

    def _recalculate_crypto_regime(self) -> Optional[Dict[str, Any]]:
        """Fetch BTC 4h candles → build features → classify with fresh engine."""
        from data.crypto_price_loader import load_crypto_price_data_interval
        from crypto.features.regime_features import build_regime_features
        from crypto.regime.crypto_regime_engine import (
            CryptoRegimeEngine,
            RegimeThresholds,
        )

        bars_4h = load_crypto_price_data_interval("BTC", 200, "4h")
        if bars_4h is None or len(bars_4h) < 20:
            logger.warning("REGIME_RECALC | insufficient BTC 4h data | rows=%s",
                           len(bars_4h) if bars_4h is not None else 0)
            return None

        features = build_regime_features(
            symbol="BTC",
            bars_4h=bars_4h,
            lookback_periods=min(100, len(bars_4h)),
        )

        # Fresh engine (no hysteresis state = raw classification)
        engine = CryptoRegimeEngine(thresholds=RegimeThresholds())
        signal = engine.analyze(features)

        # Cross-asset: try ETH
        cross_asset = None
        try:
            eth_bars = load_crypto_price_data_interval("ETH", 200, "4h")
            if eth_bars is not None and len(eth_bars) >= 20:
                eth_features = build_regime_features("ETH", eth_bars, min(100, len(eth_bars)))
                eth_engine = CryptoRegimeEngine(thresholds=RegimeThresholds())
                eth_signal = eth_engine.analyze(eth_features)
                cross_asset = eth_signal.regime.value
        except Exception as e:
            logger.debug("ETH cross-asset check failed: %s", e)

        return {
            "regime": signal.regime.value,
            "confidence": signal.confidence,
            "volatility": signal.volatility,
            "drawdown": signal.drawdown,
            "trend_slope": signal.trend_slope,
            "vol_percentile": features.vol_percentile_100,
            "cross_asset_regime": cross_asset,
        }

    def _recalculate_swing_regime(self) -> Optional[Dict[str, Any]]:
        """Use SPY proxy for swing scope."""
        from universe.governance.regime_proxy import SPYRegimeProxy
        proxy = SPYRegimeProxy()
        label = proxy.get_regime()
        if label:
            return {
                "regime": label,
                "confidence": 0.7,
                "volatility": 0.0,
                "drawdown": 0.0,
                "cross_asset_regime": None,
            }
        return None

    # ========================================================================
    # Proposal creation (Stage 3)
    # ========================================================================

    def _create_proposal(
        self,
        run_id: str,
        ctx: RegimeValidationContext,
        validation: RegimeValidationResult,
        drift: DriftDetectionResult,
        run_state: Dict,
    ) -> RegimeProposal:
        """Create non-binding regime change proposal and apply guardrails."""
        proposal_id = f"regime_prop_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Build supporting factors
        supporting = []
        for c in drift.conditions:
            if c.met:
                supporting.append(f"{c.name}: {c.reason}")

        # Build risk analysis
        risks = []
        if ctx.current_regime == "risk_on" and drift.suggested_regime in ("risk_off", "panic"):
            risks.append("Transition from risk_on to defensive regime may exit profitable positions")
        if ctx.current_regime in ("risk_off", "panic") and drift.suggested_regime == "risk_on":
            risks.append("Premature risk_on transition may increase exposure during uncertain conditions")
        if drift.emergency_override:
            risks.append("Emergency override active — heightened market stress")
        risks.append(f"Current drawdown: {ctx.drawdown:.1f}%")
        risks.append(f"Volatility: {ctx.volatility:.1f}% annualized")

        # Dissent signals
        dissent = []
        for c in drift.conditions:
            if not c.met:
                dissent.append(f"{c.name} NOT met: {c.reason}")
        if ctx.cross_asset_regime and ctx.cross_asset_regime != drift.suggested_regime:
            dissent.append(f"Cross-asset ({ctx.cross_asset_regime}) disagrees with suggestion ({drift.suggested_regime})")

        # Uncertainty statement
        uncertainty = (
            f"This proposal is based on {ctx.num_external_sources} external sources "
            f"and {len(ctx.historical_regime_durations)} historical regime durations. "
            f"Confidence: {drift.confidence:.1%}. "
            f"Phase F verdict: {self._extract_verdict_type(ctx.phase_f_verdict)}. "
            f"Cross-asset alignment: {'available' if ctx.cross_asset_regime else 'unavailable'}."
        )

        # Drift statistics
        drift_stats = {
            "validation_scores": validation.scores.to_dict(),
            "drift_conditions": [c.to_dict() for c in drift.conditions],
            "duration_hours": round(ctx.current_regime_duration_hours, 1),
            "volatility": round(ctx.volatility, 2),
            "drawdown": round(ctx.drawdown, 2),
        }

        # Build proposal metadata for guardrails
        proposal_meta = {
            "phase_f_verdict_type": self._extract_verdict_type(ctx.phase_f_verdict),
            "cross_asset_score": validation.scores.cross_asset_score,
        }

        # Apply guardrails (Stage 4)
        approved, reason, checks = self.guardrails.check_proposal(
            proposal=proposal_meta,
            run_state=run_state,
            current_drawdown=ctx.drawdown,
            scope_type=self.scope_type,
        )

        guardrail_result = "APPROVED" if approved else "DEFERRED"

        proposal = RegimeProposal(
            proposal_id=proposal_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            proposal_type="REGIME_ADJUSTMENT",
            scope=self.scope_str,
            current_regime=ctx.current_regime or "unknown",
            proposed_regime=drift.suggested_regime or "unknown",
            confidence=drift.confidence,
            supporting_factors=supporting,
            risk_analysis=risks,
            dissent_signals=dissent,
            uncertainty_statement=uncertainty,
            drift_statistics=drift_stats,
            non_binding=True,
            guardrail_result=guardrail_result,
            guardrail_reason=reason if not approved else None,
            guardrail_checks=checks,
            emergency_override=drift.emergency_override,
        )

        # Persist proposal (indefinite retention)
        self._append_jsonl(self.proposals_path, proposal.to_dict())

        # Log guardrail checks
        for check in checks:
            self._log_audit({
                "event": "REGIME_GUARDRAIL_CHECK",
                "run_id": run_id,
                "proposal_id": proposal_id,
                **check,
            })

        self._log_audit({
            "event": "REGIME_PROPOSAL_CREATED",
            "run_id": run_id,
            "proposal_id": proposal_id,
            "current_regime": proposal.current_regime,
            "proposed_regime": proposal.proposed_regime,
            "confidence": proposal.confidence,
            "guardrail_result": guardrail_result,
            "guardrail_reason": reason,
            "non_binding": True,
            "supporting_factors": supporting,
            "dissent_signals": dissent,
            "risk_analysis": risks,
        })

        logger.info(
            "REGIME_PROPOSAL | id=%s | %s→%s | confidence=%.3f | "
            "guardrails=%s | non_binding=True",
            proposal_id, proposal.current_regime, proposal.proposed_regime,
            proposal.confidence, guardrail_result,
        )

        return proposal

    # ========================================================================
    # Regime transition tracking
    # ========================================================================

    def _detect_regime_transition(
        self, run_state: Dict, current_regime: Optional[str],
        current_volatility: float = 0.0,
    ):
        """
        Detect if the live regime has changed since last run.
        If so, record the old duration, update entry timestamp,
        and snapshot entry volatility for future drift detection.
        """
        stored_regime = run_state.get("current_regime")
        if current_regime is None or stored_regime is None:
            # First run or unknown — initialize
            if current_regime:
                run_state["current_regime"] = current_regime
                run_state.setdefault("regime_entered_utc", datetime.now(timezone.utc).isoformat())
                if current_volatility > 0:
                    run_state["entry_volatility"] = round(current_volatility, 2)

                self._log_audit({
                    "event": "REGIME_STATE_INITIALIZED",
                    "regime": current_regime,
                    "entry_volatility": run_state.get("entry_volatility", 0.0),
                })
            return

        if current_regime != stored_regime:
            # Regime changed — record old duration
            old_duration = self._compute_duration_hours(run_state)
            history = run_state.get("regime_duration_history", [])
            history.append(round(old_duration, 1))
            # Keep last 100 entries
            run_state["regime_duration_history"] = history[-100:]

            # Record the change
            now_utc = datetime.now(timezone.utc).isoformat()
            changes = run_state.get("regime_changes_this_week", [])
            changes.append({
                "from": stored_regime,
                "to": current_regime,
                "timestamp": now_utc,
                "duration_hours": round(old_duration, 1),
            })
            # Prune old entries (> 7 days)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            run_state["regime_changes_this_week"] = [
                c for c in changes if c.get("timestamp", "") >= cutoff
            ]

            # Update current regime + snapshot entry volatility
            run_state["current_regime"] = current_regime
            run_state["regime_entered_utc"] = now_utc
            if current_volatility > 0:
                run_state["entry_volatility"] = round(current_volatility, 2)

            # Persist to JSONL audit trail (not just Python logger)
            self._log_audit({
                "event": "REGIME_TRANSITION_DETECTED",
                "from_regime": stored_regime,
                "to_regime": current_regime,
                "old_duration_hours": round(old_duration, 1),
                "entry_volatility": run_state.get("entry_volatility", 0.0),
            })

            logger.info(
                "REGIME_TRANSITION_DETECTED | %s → %s | old_duration=%.1fh",
                stored_regime, current_regime, old_duration,
            )

            self._save_run_state(run_state)

    # ========================================================================
    # Idempotency
    # ========================================================================

    def _should_skip(self, run_state: Dict, trigger: str) -> bool:
        """Check if we should skip this run (too recent)."""
        if trigger == "startup":
            return False  # Always run on startup

        last_run = run_state.get("last_run_utc")
        if not last_run:
            return False

        try:
            last_dt = datetime.fromisoformat(last_run)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)

            interval = (
                VALIDATION_INTERVAL_MINUTES_CRYPTO
                if self.scope_type == "crypto"
                else VALIDATION_INTERVAL_MINUTES_SWING
            )
            # Allow 10% tolerance
            min_gap = timedelta(minutes=interval * 0.9)
            elapsed = datetime.now(timezone.utc) - last_dt

            if elapsed < min_gap:
                logger.debug(
                    "REGIME_VALIDATION_SKIP | elapsed=%s < min_gap=%s",
                    elapsed, min_gap,
                )
                return True
        except (ValueError, TypeError):
            pass

        return False

    # ========================================================================
    # Duration computation
    # ========================================================================

    def _compute_duration_hours(self, run_state: Dict) -> float:
        """Compute hours since regime entry."""
        entered = run_state.get("regime_entered_utc")
        if not entered:
            return 0.0
        try:
            entered_dt = datetime.fromisoformat(entered)
            if entered_dt.tzinfo is None:
                entered_dt = entered_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - entered_dt
            return max(0.0, delta.total_seconds() / 3600)
        except (ValueError, TypeError):
            return 0.0

    # ========================================================================
    # Timeout enforcement
    # ========================================================================

    def _check_timeout(self, start_time: float):
        """Raise _TimeoutError if runtime exceeds limit."""
        elapsed = time.time() - start_time
        if elapsed > MAX_RUNTIME_SECONDS:
            raise _TimeoutError(
                f"Regime validation exceeded {MAX_RUNTIME_SECONDS}s limit "
                f"(elapsed={elapsed:.1f}s)"
            )

    # ========================================================================
    # Persistence
    # ========================================================================

    def _load_run_state(self) -> Dict[str, Any]:
        """Load run state, or initialize if missing."""
        if not self.run_state_path.exists():
            return {
                "current_regime": None,
                "regime_entered_utc": None,
                "entry_volatility": 0.0,
                "last_run_utc": None,
                "regime_changes_this_week": [],
                "regime_duration_history": [],
            }
        try:
            with open(self.run_state_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load run state: %s", e)
            return {
                "current_regime": None,
                "regime_entered_utc": None,
                "entry_volatility": 0.0,
                "last_run_utc": None,
                "regime_changes_this_week": [],
                "regime_duration_history": [],
            }

    def _save_run_state(self, state: Dict[str, Any]):
        """Atomically save run state."""
        try:
            tmp = self.run_state_path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2, default=str)
            tmp.rename(self.run_state_path)
        except Exception as e:
            logger.error("Failed to save run state: %s", e, exc_info=True)

    def _append_jsonl(self, path: Path, record: Dict[str, Any]):
        """Append a record to a JSONL file."""
        try:
            with open(path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to append to %s: %s", path.name, e, exc_info=True)

    # ========================================================================
    # Logging (3 layers)
    # ========================================================================

    def _log_pipeline(self, payload: Dict[str, Any]):
        """Layer 1: Pipeline structured log."""
        payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        payload["scope"] = self.scope_str
        self._append_jsonl(self.validation_runs_path, payload)

    def _log_audit(self, payload: Dict[str, Any]):
        """Layer 3: Full audit trail."""
        payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        payload["scope"] = self.scope_str
        self._append_jsonl(self.audit_trail_path, payload)

    # ========================================================================
    # Helpers
    # ========================================================================

    def _extract_verdict_type(self, verdict: Optional[Dict]) -> Optional[str]:
        if verdict and "verdict" in verdict:
            return verdict["verdict"].get("verdict")
        return None


class _TimeoutError(Exception):
    """Internal timeout signal — never propagated outside orchestrator."""
    pass
