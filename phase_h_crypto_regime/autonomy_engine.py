"""
Phase H: Autonomy Engine — Core Orchestrator.

30-minute cycle:
  1. Kill switch check
  2. Load data (BTC, ETH, universe 4h bars)
  3. Compute composite macro score
  4. Compute per-asset scores
  5. Compute drift score
  6. Evaluate fail-safes
  7. Evaluate guardrails
  8. Adjust confidence
  9. Flip regime if eligible (paper: auto-apply; live: proposal only)
 10. Compute exposure cap
 11. Persist all state + log to JSONL
"""

import logging
import signal
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from phase_h_crypto_regime.config import (
    PHASE_H_CRYPTO_KILL_SWITCH,
    PHASE_H_CRYPTO_LIVE_AUTONOMY,
    MAX_CYCLE_SECONDS,
    AUTONOMY_INTERVAL_MINUTES,
    DATA_CONFIDENCE_FLOOR,
)
from phase_h_crypto_regime.composite_macro_engine import CompositeMacroEngine
from phase_h_crypto_regime.asset_regime_engine import AssetRegimeEngine
from phase_h_crypto_regime.exposure_ladder import ExposureLadder
from phase_h_crypto_regime.drift_scoring import DriftScorer
from phase_h_crypto_regime.flip_budget import FlipBudget
from phase_h_crypto_regime.fail_safe_engine import FailSafeEngine, FailSafeContext
from phase_h_crypto_regime.guardrails import PhaseHGuardrails
from phase_h_crypto_regime.persistence import PhaseHPersistence

logger = logging.getLogger(__name__)


class _CycleTimeout(Exception):
    """Raised when cycle exceeds MAX_CYCLE_SECONDS."""
    pass


def _timeout_handler(signum, frame):
    raise _CycleTimeout(f"Phase H cycle exceeded {MAX_CYCLE_SECONDS}s timeout")


@dataclass
class PhaseHCycleResult:
    """Result of a single autonomy cycle."""
    run_id: str = ""
    timestamp: str = ""
    macro_regime: str = "NEUTRAL"
    macro_score: float = 0.0
    macro_confidence: float = 0.5
    exposure_cap: float = 0.75
    drift_score: float = 0.0
    flip_performed: bool = False
    flip_from: str = ""
    flip_to: str = ""
    halt_new_entries: bool = False
    fail_safe_triggers: List[str] = field(default_factory=list)
    action_taken: str = "NO_CHANGE"
    reason_trace: List[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    duration_ms: float = 0.0
    asset_scores: Dict[str, Any] = field(default_factory=dict)


class PhaseHAutonomyEngine:
    """
    Core orchestrator for Phase H crypto regime autonomy.

    Runs 30-minute cycles to evaluate composite macro regime,
    per-asset scores, drift, fail-safes, and exposure caps.
    """

    def __init__(self, scope, runtime, verdict_reader=None):
        """
        Args:
            scope: Scope object (env, broker, mode, market)
            runtime: RuntimeEnv with portfolio, trade_ledger, etc.
            verdict_reader: Optional VerdictReader for Phase F verdicts
        """
        self.scope = scope
        self.runtime = runtime
        self.verdict_reader = verdict_reader
        self.scope_str = str(scope)

        self.macro_engine = CompositeMacroEngine()
        self.asset_engine = AssetRegimeEngine()
        self.exposure_ladder = ExposureLadder()
        self.drift_scorer = DriftScorer()
        self.flip_budget = FlipBudget()
        self.fail_safe_engine = FailSafeEngine()
        self.guardrails = PhaseHGuardrails()
        self.persistence = PhaseHPersistence(self.scope_str)

        # Initialize runtime attributes with safe defaults so pipeline
        # always has valid values, even if the first cycle fails.
        if not hasattr(runtime, "phase_h_exposure_cap"):
            runtime.phase_h_exposure_cap = 1.0
        if not hasattr(runtime, "phase_h_macro_regime"):
            runtime.phase_h_macro_regime = "NEUTRAL"
        if not hasattr(runtime, "phase_h_halt_new_entries"):
            runtime.phase_h_halt_new_entries = False
        if not hasattr(runtime, "phase_h_asset_scores"):
            runtime.phase_h_asset_scores = {}

    def run_cycle(self, trigger: str = "scheduled") -> PhaseHCycleResult:
        """
        Run one autonomy cycle.

        Args:
            trigger: What triggered this cycle (scheduled, startup, manual)

        Returns:
            PhaseHCycleResult
        """
        run_id = f"phase_h_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        start = datetime.now(timezone.utc)
        result = PhaseHCycleResult(run_id=run_id, timestamp=start.isoformat())

        # Set timeout
        old_handler = None
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(MAX_CYCLE_SECONDS)
        except (ValueError, OSError):
            pass  # Not on main thread or unsupported platform

        try:
            result = self._execute_cycle(run_id, trigger, start, result)
        except _CycleTimeout as e:
            result.action_taken = "TIMEOUT"
            result.reason_trace.append(str(e))
            logger.error("PHASE_H_TIMEOUT | run_id=%s | %s", run_id, e)
        except Exception as e:
            result.action_taken = "ERROR"
            result.reason_trace.append(f"cycle_error: {e}")
            logger.error("PHASE_H_ERROR | run_id=%s | %s", run_id, e, exc_info=True)
        finally:
            # Cancel alarm
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (ValueError, OSError):
                pass

            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result.duration_ms = round(elapsed, 1)

            # Always persist
            try:
                self._persist_cycle(result)
            except Exception as e:
                logger.error("PHASE_H_PERSIST_FAILED | %s", e)

        return result

    def _execute_cycle(
        self, run_id: str, trigger: str, start: datetime, result: PhaseHCycleResult,
    ) -> PhaseHCycleResult:
        """Execute the 11-step cycle."""

        # Step 1: Kill switch
        if PHASE_H_CRYPTO_KILL_SWITCH:
            result.skipped = True
            result.skip_reason = "KILL_SWITCH_ACTIVE"
            result.action_taken = "SKIPPED"
            logger.warning("PHASE_H_KILL_SWITCH | cycle skipped")
            return result

        # Step 1b: Idempotency check
        run_state = self.persistence.load_run_state()
        if self._should_skip(run_state, start):
            result.skipped = True
            result.skip_reason = "TOO_RECENT"
            result.action_taken = "SKIPPED"
            return result

        # Step 2: Load data
        bars_4h = self._load_universe_bars()
        if not bars_4h:
            result.action_taken = "NO_DATA"
            result.reason_trace.append("failed to load any 4h bars")
            return result

        btc_4h = bars_4h.get("BTC")
        eth_4h = bars_4h.get("ETH")

        if btc_4h is None or btc_4h.empty:
            result.action_taken = "NO_BTC_DATA"
            result.reason_trace.append("BTC 4h bars unavailable")
            return result

        # Step 3: Composite macro score
        macro_result = self.macro_engine.compute(btc_4h, eth_4h, bars_4h)
        result.macro_score = macro_result.macro_score
        result.macro_regime = macro_result.macro_regime
        result.macro_confidence = macro_result.macro_confidence

        # Step 4: Per-asset scores
        asset_results = self.asset_engine.score_universe(bars_4h, btc_4h)
        result.asset_scores = {
            sym: {"score": ar.asset_score, "regime": ar.asset_regime}
            for sym, ar in asset_results.items()
        }

        # Persist asset scores
        try:
            asset_records = [
                {
                    "timestamp": start.isoformat(),
                    "run_id": run_id,
                    "symbol": sym,
                    "score": ar.asset_score,
                    "regime": ar.asset_regime,
                    "components": ar.components,
                }
                for sym, ar in asset_results.items()
            ]
            self.persistence.append_asset_scores(asset_records)
        except Exception as e:
            logger.warning("Failed to persist asset scores: %s", e)

        # Step 5: Drift score
        phase_f_conf = self._get_phase_f_confidence()
        current_regime = run_state.get("current_regime", "NEUTRAL")

        drift_result = self.drift_scorer.compute_drift(
            current_regime=current_regime,
            new_macro_result=macro_result,
            run_state=run_state,
            phase_f_confidence=phase_f_conf,
        )
        result.drift_score = drift_result.drift_score

        # Step 6: Fail-safes
        fs_ctx = self._build_fail_safe_context(run_state, macro_result)
        fs_result = self.fail_safe_engine.evaluate(fs_ctx)
        result.halt_new_entries = fs_result.halt_new_entries
        result.fail_safe_triggers = list(fs_result.active_triggers)

        if fs_result.active_triggers:
            try:
                self.persistence.append_fail_safe_event({
                    "timestamp": start.isoformat(),
                    "run_id": run_id,
                    "triggers": fs_result.active_triggers,
                    "halt_new_entries": fs_result.halt_new_entries,
                    "exposure_override": fs_result.exposure_override,
                    "reason_trace": fs_result.reason_trace,
                })
            except Exception as e:
                logger.warning("Failed to persist fail-safe event: %s", e)

        # Step 7: Guardrails
        flip_budget_result = self.flip_budget.can_flip(run_state)
        guardrail_approved, guardrail_reason = self.guardrails.check_flip_eligibility(
            drift_result=drift_result,
            run_state=run_state,
            fail_safe_result=fs_result,
            flip_budget_result=flip_budget_result,
        )

        # Step 8: Confidence adjustment
        adjusted_confidence = macro_result.macro_confidence - fs_result.confidence_decay
        adjusted_confidence = max(DATA_CONFIDENCE_FLOOR, adjusted_confidence)

        # Step 9: Regime flip decision
        if fs_result.revert_regime:
            # Auto-revert takes priority; still consumes flip budget
            old_regime = current_regime
            new_regime = fs_result.revert_regime
            self._apply_regime_change(run_state, old_regime, new_regime, start)
            self.flip_budget.record_flip(run_state, old_regime, new_regime)
            result.flip_performed = True
            result.flip_from = old_regime
            result.flip_to = new_regime
            result.action_taken = "AUTO_REVERT"
            result.reason_trace.append(f"auto_revert: {old_regime} -> {new_regime}")

        elif guardrail_approved and macro_result.macro_regime != current_regime:
            is_live = self.scope.env.lower() == "live"

            if is_live and not PHASE_H_CRYPTO_LIVE_AUTONOMY:
                # Live without autonomy: proposal only
                result.action_taken = "PROPOSAL_ONLY"
                result.reason_trace.append(
                    f"live_proposal: {current_regime} -> {macro_result.macro_regime} "
                    f"(PHASE_H_CRYPTO_LIVE_AUTONOMY=false)"
                )
            else:
                # Paper mode or live with autonomy enabled: auto-apply
                old_regime = current_regime
                new_regime = macro_result.macro_regime
                self._apply_regime_change(run_state, old_regime, new_regime, start)
                self.flip_budget.record_flip(run_state, old_regime, new_regime)
                result.flip_performed = True
                result.flip_from = old_regime
                result.flip_to = new_regime
                result.action_taken = "REGIME_FLIP"
                result.reason_trace.append(f"flip: {old_regime} -> {new_regime}")
        else:
            result.action_taken = "NO_CHANGE"
            result.reason_trace.append(guardrail_reason)

        # Step 10: Exposure cap
        effective_regime = run_state.get("current_regime", macro_result.macro_regime)
        exposure_cap = self.exposure_ladder.compute_exposure_cap(effective_regime, adjusted_confidence)

        # Apply fail-safe exposure override
        if fs_result.exposure_override is not None:
            exposure_cap = min(exposure_cap, fs_result.exposure_override)

        result.exposure_cap = exposure_cap

        # Set runtime attributes for pipeline consumption
        self.runtime.phase_h_exposure_cap = exposure_cap
        self.runtime.phase_h_macro_regime = effective_regime
        self.runtime.phase_h_halt_new_entries = fs_result.halt_new_entries
        self.runtime.phase_h_asset_scores = result.asset_scores

        # Step 11: Update run state
        run_state["macro_confidence"] = adjusted_confidence
        run_state["last_cycle_timestamp"] = start.isoformat()
        self.persistence.save_run_state(run_state)

        logger.info(
            "PHASE_H_CYCLE | run_id=%s trigger=%s regime=%s score=%.3f "
            "conf=%.3f drift=%.3f cap=%.3f action=%s",
            run_id, trigger, effective_regime, macro_result.macro_score,
            adjusted_confidence, drift_result.drift_score,
            exposure_cap, result.action_taken,
        )

        return result

    def _should_skip(self, run_state: Dict[str, Any], now: datetime) -> bool:
        """Check if cycle should be skipped (idempotency)."""
        last_ts = run_state.get("last_cycle_timestamp")
        if not last_ts:
            return False

        try:
            last = datetime.fromisoformat(last_ts)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed_minutes = (now - last).total_seconds() / 60.0
            threshold = AUTONOMY_INTERVAL_MINUTES * 0.90
            if elapsed_minutes < threshold:
                logger.debug(
                    "PHASE_H_SKIP | elapsed=%.1fm < threshold=%.1fm",
                    elapsed_minutes, threshold,
                )
                return True
        except Exception:
            pass

        return False

    def _load_universe_bars(self) -> Dict[str, Any]:
        """Load 4h bars for all universe symbols."""
        from data.crypto_price_loader import load_crypto_price_data_interval
        from config.crypto.loader import load_crypto_config

        crypto_config = load_crypto_config(self.scope)
        symbols = crypto_config.get("CRYPTO_UNIVERSE", ["BTC", "ETH", "SOL"])
        regime_lookback = int(crypto_config.get("REGIME_LOOKBACK_BARS", 200))

        bars_4h = {}
        for symbol in symbols:
            try:
                df = load_crypto_price_data_interval(
                    symbol=symbol,
                    lookback_bars=regime_lookback,
                    interval="4h",
                )
                if df is not None and not df.empty:
                    bars_4h[symbol] = df
            except Exception as e:
                logger.warning("Failed to load 4h data for %s: %s", symbol, e)

        return bars_4h

    def _get_phase_f_confidence(self) -> Optional[float]:
        """Read Phase F verdict confidence (read-only)."""
        if self.verdict_reader is None:
            return None
        try:
            verdict = self.verdict_reader.read_latest_verdict(scope="crypto")
            if verdict and "verdict" in verdict:
                return verdict["verdict"].get("regime_confidence")
        except Exception as e:
            logger.warning("Failed to read Phase F verdict: %s", e)
        return None

    def _build_fail_safe_context(
        self, run_state: Dict[str, Any], macro_result,
    ) -> FailSafeContext:
        """Build fail-safe context from runtime (read-only)."""
        ctx = FailSafeContext(run_state=run_state)

        # Portfolio PnL (read-only)
        portfolio = getattr(self.runtime, "risk_manager", None)
        if portfolio:
            portfolio = getattr(portfolio, "portfolio", portfolio)
            ctx.daily_pnl_pct = getattr(portfolio, "daily_pnl", 0.0)
            equity = getattr(portfolio, "current_equity", 0.0)
            start_equity = getattr(portfolio, "daily_start_equity", equity)
            if start_equity > 0:
                ctx.intraday_drawdown_pct = (equity - start_equity) / start_equity
                ctx.daily_pnl_pct = ctx.intraday_drawdown_pct

        # Current drawdown from macro analysis
        ctx.current_drawdown_pct = 0.0
        btc_score = macro_result.component_scores.get("btc_regime", 0.5)
        if btc_score < 0.2:
            ctx.current_drawdown_pct = -0.30  # Estimate from very low BTC score

        # Volatility
        vol_score = macro_result.component_scores.get("volatility_expansion", 0.5)
        ctx.current_vol_percentile = 1.0 - vol_score
        ctx.baseline_vol = 1.0
        ctx.current_vol = 1.0 / max(0.1, vol_score) if vol_score < 0.3 else 1.0

        # Stop loss count from trade ledger
        trade_ledger = getattr(self.runtime, "trade_ledger", None)
        if trade_ledger:
            try:
                recent_trades = trade_ledger.get_recent_trades(hours=6)
                stops = [t for t in (recent_trades or []) if getattr(t, "exit_reason", "") == "stop_loss"]
                ctx.consecutive_stops = len(stops)
                ctx.stop_timestamps = [
                    getattr(t, "exit_timestamp", "").isoformat()
                    if hasattr(getattr(t, "exit_timestamp", ""), "isoformat")
                    else str(getattr(t, "exit_timestamp", ""))
                    for t in stops
                ]
            except Exception:
                pass

        # Phase F
        if self.verdict_reader:
            try:
                verdict = self.verdict_reader.read_latest_verdict(scope="crypto")
                if verdict and "verdict" in verdict:
                    ctx.phase_f_verdict = verdict["verdict"].get("verdict")
                    ctx.phase_f_confidence = verdict["verdict"].get("regime_confidence")
            except Exception:
                pass

        # Regime context
        ctx.current_regime = run_state.get("current_regime", "NEUTRAL")

        # Last flip info + PnL since flip
        flip_history = run_state.get("flip_history", [])
        if flip_history:
            ctx.last_flip_timestamp = flip_history[-1].get("timestamp")
            ctx.pnl_since_flip_pct = self._compute_pnl_since_flip(
                flip_history[-1].get("timestamp"),
            )

        # Data quality: mark degraded if we had to estimate core fields
        if ctx.daily_pnl_pct == 0.0 and ctx.intraday_drawdown_pct == 0.0:
            portfolio = getattr(self.runtime, "risk_manager", None)
            if portfolio is None:
                ctx.data_quality_ok = False

        return ctx

    def _compute_pnl_since_flip(self, flip_timestamp_str: Optional[str]) -> float:
        """Compute portfolio PnL % since the last regime flip."""
        if not flip_timestamp_str:
            return 0.0

        try:
            flip_ts = datetime.fromisoformat(flip_timestamp_str)
            if flip_ts.tzinfo is None:
                flip_ts = flip_ts.replace(tzinfo=timezone.utc)
        except Exception:
            return 0.0

        # Try to get equity at flip time from run_state transitions
        portfolio = getattr(self.runtime, "risk_manager", None)
        if portfolio:
            portfolio = getattr(portfolio, "portfolio", portfolio)
            current_equity = getattr(portfolio, "current_equity", 0.0)
            # Use daily_start_equity as a conservative proxy for flip-time equity
            # when we don't have exact flip-time snapshot
            flip_equity = getattr(portfolio, "daily_start_equity", current_equity)
            if flip_equity > 0:
                return (current_equity - flip_equity) / flip_equity

        return 0.0

    def _apply_regime_change(
        self,
        run_state: Dict[str, Any],
        old_regime: str,
        new_regime: str,
        timestamp: datetime,
    ) -> None:
        """Apply a regime change to run state."""
        # Record transition duration
        regime_since = run_state.get("current_regime_since")
        if regime_since:
            try:
                since = datetime.fromisoformat(regime_since)
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                duration_hours = (timestamp - since).total_seconds() / 3600.0
                transitions = run_state.setdefault("regime_transitions", [])
                transitions.append({
                    "from_regime": old_regime,
                    "to_regime": new_regime,
                    "timestamp": timestamp.isoformat(),
                    "duration_hours": round(duration_hours, 2),
                })
                # Keep last 50 transitions
                run_state["regime_transitions"] = transitions[-50:]
            except Exception:
                pass

        # Save old regime as last stable (for auto-revert)
        run_state["last_stable_regime"] = old_regime
        run_state["current_regime"] = new_regime
        run_state["current_regime_since"] = timestamp.isoformat()

    def _persist_cycle(self, result: PhaseHCycleResult) -> None:
        """Persist cycle result to JSONL."""
        record = {
            "timestamp": result.timestamp,
            "environment": self.scope.env,
            "run_id": result.run_id,
            "macro_score": result.macro_score,
            "macro_regime": result.macro_regime,
            "macro_confidence": result.macro_confidence,
            "asset_scores": result.asset_scores,
            "drift_score": result.drift_score,
            "exposure_cap": result.exposure_cap,
            "flip_budget_remaining": self.flip_budget.can_flip(
                self.persistence.load_run_state()
            )[1] if not result.skipped else None,
            "fail_safe_state": result.fail_safe_triggers,
            "halt_new_entries": result.halt_new_entries,
            "action_taken": result.action_taken,
            "reason_trace": result.reason_trace,
            "duration_ms": result.duration_ms,
        }
        self.persistence.append_cycle_log(record)
